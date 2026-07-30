"""GodMode V12.68 — AI Entry Auditor.

One structured LLM call per CANDIDATE ENTRY (not per tick). The deterministic engine
still finds and scores every setup; the auditor is a risk-first second opinion that can
only VETO or DOWNGRADE — it can never create a trade. It receives the same structured
facts the engine used PLUS (optionally) a rendered chart image, and returns:

    {verdict: APPROVE|DOWNGRADE|VETO, confidenceAdjust: -10..+10,
     invalidationPrice: float|null, reason: str, entryQualityNotes: [str]}

Design rules (why this is safe):
  * FAIL-OPEN by default: if the provider is unconfigured, slow, or errors, the audit is
    skipped and the engine's decision stands. AI downtime must never stop a validated bot.
    (failClosed=true flips this for users who want "no AI check, no trade".)
  * The auditor can tighten the stop toward the AI's invalidation level, but only within
    bounds (never below 50% of the engine's structural stop distance) so a hallucinated
    level cannot create a noise stop.
  * confidenceAdjust is clamped to ±maxConfidenceAdjust and is informational + journalled;
    a DOWNGRADE converts a full entry to SCOUT size, a VETO blocks it.
  * Cooldown: an identical setup signature is not re-audited within cooldownSeconds, so a
    retrying loop cannot burn API calls.
Every verdict is journalled so you can later compare AI verdicts vs realised outcomes.
"""
from __future__ import annotations

import time
import hashlib
import json
from typing import Any, Callable


def _f(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return d


_AUDIT_CACHE: dict[str, dict[str, Any]] = {}


def _setup_signature(
    decision: dict[str, Any],
    market: dict[str, Any],
    payload: dict[str, Any],
    plan: dict[str, Any],
    provider: str,
    model: str,
) -> str:
    """Bind a cached verdict to the complete risk-bearing setup.

    A verdict for one stop/target geometry must never be replayed onto another
    geometry merely because the side, strategy and rounded entry look similar.
    Provider/model are included because their risk judgements are not
    interchangeable. The API key is deliberately excluded.
    """
    selected = decision.get("selectedStrategy")
    selected = selected if isinstance(selected, dict) else {}
    material = {
        "symbol": str(payload.get("symbol") or market.get("symbol") or "XAUUSD").upper(),
        "side": str(payload.get("side") or decision.get("side") or "").upper(),
        "strategy": str(selected.get("name") or decision.get("strategy") or ""),
        "setupId": str(
            decision.get("decisionId")
            or decision.get("setupId")
            or decision.get("_generatedAt")
            or ""
        ),
        "timeframe": str(market.get("timeframe") or ""),
        "entry": round(_f(payload.get("price") or plan.get("entry")), 6),
        "sl": round(_f(payload.get("sl") or plan.get("sl")), 6),
        "tp": [
            round(_f(payload.get("tp") or plan.get("tp")), 6),
            round(_f(plan.get("tp1")), 6),
            round(_f(plan.get("tp2")), 6),
            round(_f(plan.get("tp3")), 6),
            round(_f(plan.get("tp4")), 6),
        ],
        "provider": str(provider or "").lower(),
        "model": str(model or ""),
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


SYSTEM_PROMPT = (
    "You are a senior XAUUSD execution auditor at a proprietary trading desk. A rules-based "
    "engine has ALREADY approved a scalp entry. Your only job is to catch context the rules "
    "miss: entering into obvious resistance/support, chasing an exhausted impulse, fighting a "
    "fresh higher-timeframe shift, poor retest quality, pre-news traps, or sloppy structure. "
    "You may NOT invent new trades. Judge only what the data (and chart image if provided) shows; "
    "if evidence is thin, APPROVE with confidenceAdjust 0 — do not veto on vague feelings. "
    "VETO only for a concrete, nameable defect. DOWNGRADE (scout size) when the setup is valid "
    "but the location or timing is second-rate. Return ONLY JSON: "
    '{"verdict":"APPROVE|DOWNGRADE|VETO","confidenceAdjust":-10..10,'
    '"invalidationPrice":number or null (the price that proves this entry wrong, between entry and stop),'
    '"reason":"one concrete sentence","entryQualityNotes":["short note", ...]}'
)


def build_audit_context(decision: dict[str, Any], market: dict[str, Any], payload: dict[str, Any],
                        plan: dict[str, Any], memory_stats: dict[str, Any] | None = None,
                        macro: dict[str, Any] | None = None, news: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the structured facts the auditor judges. Compact on purpose — recent candles
    only, no raw history dumps. The chart image carries the visual context."""
    feats = decision.get("features", {}) if isinstance(decision.get("features"), dict) else {}
    candles = market.get("candles") if isinstance(market.get("candles"), list) else []
    recent = [{"t": c.get("time"), "o": c.get("open"), "h": c.get("high"),
               "l": c.get("low"), "c": c.get("close")} for c in candles[-40:]]
    return {
        "symbol": payload.get("symbol") or market.get("symbol") or "XAUUSD",
        "side": payload.get("side") or decision.get("side"),
        "entry": payload.get("price") or plan.get("entry") or market.get("price"),
        "sl": payload.get("sl") or plan.get("sl"),
        "tp1": plan.get("tp1"), "tp2": plan.get("tp2"),
        "engineConfidence": decision.get("confidence"),
        "quality": decision.get("quality"),
        "strategy": (decision.get("selectedStrategy") or {}).get("name") or decision.get("strategy"),
        "timeframe": market.get("timeframe", "M15"),
        "session": market.get("session"),
        "spread": market.get("spread"),
        "atr14": market.get("atr14"),
        "engineReason": str(decision.get("reason") or "")[:300],
        "features": {k: feats.get(k) for k in (
            "rsi14", "macd", "htfDailyBias", "h1Aligned", "h4Aligned", "computedSide",
            "trendEfficiency", "confluenceCount", "orderBlock", "structure", "emaStack",
            "rangePosition", "volatilityRegime") if k in feats},
        "macro": macro or {},
        "newsWindow": news or {},
        "botTrackRecord": memory_stats or {},
        "recentCandles": recent,
    }


def audit_entry(llm_json_call: Callable[..., dict[str, Any]],
                cfg: dict[str, Any],
                decision: dict[str, Any], market: dict[str, Any], payload: dict[str, Any],
                plan: dict[str, Any], memory_stats: dict[str, Any] | None = None,
                macro: dict[str, Any] | None = None, news: dict[str, Any] | None = None,
                chart_png: bytes | None = None,
                provider: str = "claude", api_key: str = "", model: str = "") -> dict[str, Any]:
    """Run one pre-trade audit. Always returns a dict; never raises.

    Fail-open contract: any infrastructure problem yields verdict SKIPPED with ok=True
    (unless cfg.failClosed), so the engine decision stands.
    """
    started = time.time()
    cooldown = _f(cfg.get("cooldownSeconds"), 45.0)
    sig = _setup_signature(decision, market, payload, plan, provider, model)
    cached = _AUDIT_CACHE.get(sig)
    if cached and (started - _f(cached.get("_ts"))) < cooldown:
        out = dict(cached)
        out["cached"] = True
        return out

    if not api_key:
        return {"ok": True, "verdict": "SKIPPED", "reason": "AI provider not configured — engine decision stands.",
                "skipped": True}

    context = build_audit_context(decision, market, payload, plan, memory_stats, macro, news)
    import json as _json
    user_prompt = ("Audit this candidate entry. The rules engine already approved it — find the concrete "
                   "contextual defect if one exists, otherwise approve.\n" + _json.dumps(context, default=str))

    images = []
    if chart_png:
        try:
            import base64
            images = [base64.b64encode(chart_png).decode("ascii")]
        except Exception:
            images = []

    timeout = max(6.0, min(_f(cfg.get("timeoutSeconds"), 20.0), 60.0))
    res = llm_json_call(provider, api_key, model, SYSTEM_PROMPT, user_prompt,
                        timeout=timeout, images=images)
    latency_ms = int((time.time() - started) * 1000)

    if not res.get("ok") or not isinstance(res.get("json"), dict):
        fail_closed = bool(cfg.get("failClosed", False))
        out = {"ok": not fail_closed, "verdict": "VETO" if fail_closed else "SKIPPED",
               "reason": ("AI audit unavailable and failClosed is ON — blocking." if fail_closed
                          else f"AI audit unavailable ({str(res.get('message') or 'no response')[:120]}) — engine decision stands."),
               "skipped": not fail_closed, "latencyMs": latency_ms, "provider": provider}
        return out

    j = res["json"]
    verdict = str(j.get("verdict", "APPROVE")).upper()
    if verdict not in {"APPROVE", "DOWNGRADE", "VETO"}:
        verdict = "APPROVE"
    max_adj = abs(_f(cfg.get("maxConfidenceAdjust"), 10.0))
    adj = max(-max_adj, min(max_adj, _f(j.get("confidenceAdjust"), 0.0)))

    # Bounded invalidation level: must sit strictly between entry and the engine stop, and may
    # not tighten the stop below 50% of the structural stop distance.
    inv = j.get("invalidationPrice")
    inv_out: float | None = None
    try:
        entry = _f(context.get("entry")); sl = _f(context.get("sl"))
        side = str(context.get("side") or "").upper()
        if inv is not None and entry and sl:
            inv_f = _f(inv)
            dist = abs(entry - sl)
            if dist > 0:
                if side == "BUY" and sl < inv_f < entry and (entry - inv_f) >= 0.5 * dist:
                    inv_out = round(inv_f, 3)
                elif side == "SELL" and entry < inv_f < sl and (inv_f - entry) >= 0.5 * dist:
                    inv_out = round(inv_f, 3)
    except Exception:
        inv_out = None

    out = {"ok": verdict != "VETO", "verdict": verdict, "confidenceAdjust": round(adj, 1),
           "invalidationPrice": inv_out,
           "reason": str(j.get("reason") or "")[:300],
           "entryQualityNotes": [str(x)[:160] for x in (j.get("entryQualityNotes") or [])[:5]],
           "latencyMs": latency_ms, "provider": provider, "model": model,
           "usedChartImage": bool(images), "signature": sig}
    _AUDIT_CACHE[sig] = {**out, "_ts": time.time()}
    if len(_AUDIT_CACHE) > 200:
        oldest = sorted(_AUDIT_CACHE.items(), key=lambda kv: kv[1].get("_ts", 0))[:100]
        for k, _ in oldest:
            _AUDIT_CACHE.pop(k, None)
    return out
