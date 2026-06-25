"""GodMode AI post-trade reviewer.

This is the layer that makes the bot feel like an *intelligent agent* on top of the
deterministic decision engine. After a bot trade closes, the reviewer reads the
full trade context (strategy, R-multiple, outcome, confidence, session, regime and
the confluence feature snapshot) and produces a concise, plain-English critique
plus a concrete, actionable adjustment.

It uses Claude (Anthropic Messages API) when ``ANTHROPIC_API_KEY`` is configured,
and otherwise falls back to a deterministic local review so the feature ALWAYS
works offline / without keys. No third-party SDK is required — the HTTP call uses
the standard library, so there is nothing new to ``pip install``.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

# Default to a fast, low-cost model for per-trade reviews; override via env.
# (Anthropic model ids: claude-haiku-4-5-20251001, claude-sonnet-4-6, claude-opus-4-8.)
DEFAULT_REVIEW_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AITradeReviewer:
    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.model = os.getenv("GODMODE_AI_REVIEW_MODEL", DEFAULT_REVIEW_MODEL).strip() or DEFAULT_REVIEW_MODEL
        self.enabled = os.getenv("GODMODE_AI_REVIEW_ENABLED", "true").lower() in {"1", "true", "yes"}

    # ── public API ────────────────────────────────────────────────────────────
    def review(self, trade: dict[str, Any]) -> dict[str, Any]:
        """Return {provider, aiScore, summary, lesson, improvement, adjustment}."""
        if self.enabled and self.api_key:
            try:
                out = self._review_with_claude(trade)
                if out:
                    return out
            except Exception as exc:  # never let the reviewer break the trade loop
                return {**self._local_review(trade), "provider": "local_fallback", "note": f"Claude review failed: {exc}"}
        return self._local_review(trade)

    # ── Claude path ───────────────────────────────────────────────────────────
    def _review_with_claude(self, trade: dict[str, Any]) -> dict[str, Any] | None:
        prompt = self._build_prompt(trade)
        body = json.dumps({
            "model": self.model,
            "max_tokens": 600,
            "system": (
                "You are a disciplined institutional XAUUSD (gold) trading coach reviewing a "
                "single closed trade taken by an automated bot. Be concise, specific and honest. "
                "Reward process, not just outcome: a losing trade with good process is fine; a "
                "winning trade with bad process is a warning. Respond ONLY with a JSON object with "
                "keys: aiScore (0-100 integer rating the QUALITY of the decision/process), summary "
                "(<=240 chars), lesson (<=160 chars), improvement (<=160 chars), adjustment (one "
                "concrete parameter or rule change, <=160 chars)."
            ),
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_URL, data=body, method="POST",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8", "ignore"))
        text = "".join(blk.get("text", "") for blk in payload.get("content", []) if blk.get("type") == "text").strip()
        parsed = self._extract_json(text)
        if not parsed:
            return None
        return {
            "provider": f"claude:{self.model}",
            "aiScore": int(float(parsed.get("aiScore", 60) or 60)),
            "summary": str(parsed.get("summary", ""))[:240],
            "lesson": str(parsed.get("lesson", ""))[:160],
            "improvement": str(parsed.get("improvement", ""))[:160],
            "adjustment": str(parsed.get("adjustment", ""))[:160],
            "reviewedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
        return None

    @staticmethod
    def _build_prompt(trade: dict[str, Any]) -> str:
        keep = {
            "strategy": trade.get("strategy"),
            "side": trade.get("direction") or trade.get("side"),
            "outcome": trade.get("outcome"),
            "pnlUsd": trade.get("pnlUsd"),
            "rMultiple": trade.get("rMultiple"),
            "confidence": trade.get("confidence"),
            "session": trade.get("session"),
            "regime": trade.get("marketRegime") or trade.get("regime"),
            "entryReason": trade.get("entryReason") or trade.get("reason"),
            "exitReason": trade.get("exitReason"),
            "holdTime": trade.get("holdTime"),
            "entryPrice": trade.get("entryPrice"),
            "exitPrice": trade.get("exitPrice"),
            "confluence": trade.get("confluenceCount"),
            "htfAligned": trade.get("htfAligned"),
            "h1Aligned": trade.get("h1Aligned"),
            "rsi14": trade.get("rsi14"),
        }
        return (
            "Review this closed XAUUSD bot trade and return the JSON object as instructed:\n"
            + json.dumps(keep, default=str, indent=2)
        )

    # ── deterministic local fallback ──────────────────────────────────────────
    def _local_review(self, trade: dict[str, Any]) -> dict[str, Any]:
        r = float(trade.get("rMultiple", 0) or 0)
        pnl = float(trade.get("pnlUsd", 0) or 0)
        conf = float(trade.get("confidence", 0) or 0)
        outcome = str(trade.get("outcome") or ("WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"))
        strategy = trade.get("strategy") or "GodMode Bot"
        session = trade.get("session") or "session"
        htf = trade.get("htfAligned")
        exit_reason = str(trade.get("exitReason") or "").lower()

        # Process quality score: confidence + R outcome + HTF alignment, lightly blended.
        score = 50 + min(25, max(-25, r * 8)) + (10 if htf else -5) + (conf - 70) * 0.2
        score = int(max(2, min(98, round(score))))

        if outcome == "WIN":
            summary = f"{strategy} {trade.get('direction') or trade.get('side','')} won {r:+.2f}R in {session}. Confidence {conf:.0f}%."
            lesson = "Process and outcome aligned — repeat this setup template."
            improvement = "Let runners breathe; trail behind structure rather than fixed TP." if r < 1.5 else "Bank discipline held; keep risk per trade constant."
            adjustment = "Keep current strictness; log this as a reference setup."
        elif outcome == "LOSS":
            if "sl" in exit_reason or "stop" in exit_reason:
                summary = f"{strategy} stopped out {r:+.2f}R. Confidence was {conf:.0f}%; HTF aligned={bool(htf)}."
                lesson = "A clean stop on a valid setup is acceptable cost of doing business." if htf else "Entry fought the higher timeframe — avoid counter-HTF trades."
                improvement = "Require HTF + H1 agreement before entry." if not htf else "Tighten entry to OTE/pullback to improve R on stop-outs."
                adjustment = "Raise minConfluence by 1 for this regime." if not htf else "Hold parameters; sample more before changing."
            else:
                summary = f"{strategy} closed {r:+.2f}R early ({exit_reason or 'manual/fast-fail'})."
                lesson = "Cutting a non-performing trade preserved capital."
                improvement = "Give valid setups room to ~ -0.7R before fast-fail to avoid premature cuts."
                adjustment = "Review fastFailNoProgressCandles (consider +1)."
        else:
            summary = f"{strategy} scratched near break-even ({r:+.2f}R)."
            lesson = "Break-even management protected the account."
            improvement = "Confirm momentum expansion before committing full risk."
            adjustment = "No change; monitor."
        return {
            "provider": "local_fallback",
            "aiScore": score,
            "summary": summary[:240],
            "lesson": lesson[:160],
            "improvement": improvement[:160],
            "adjustment": adjustment[:160],
            "reviewedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
