"""GodMode trade-context store — closes the strategy-attribution gap.

Problem this solves
-------------------
Before this module the bot computed a *selected strategy* (e.g. "Liquidity Sweep
+ Order Block Retest") but, at execution time, stamped the MT5 comment with the
*entry type* only ("GODMODE_auto_fire"). The real strategy name was discarded, so
Analytics / Journal / Top-Strategies grouped trades by the entry-type comment and
showed useless fragments like "GODMODE_auto_fir". The AI could never learn which
strategy actually worked.

This store fixes that with two complementary mechanisms:

1. A short, deterministic strategy CODE is stamped into the MT5 comment (which is
   capped at 31 chars), so the strategy survives even a process restart or a lost
   context file — it can always be parsed back from the broker deal.
2. A JSON-backed ``ticket -> full context`` map records the strategy NAME, entry
   reason, confidence, session, regime, planned R and the decision snapshot at
   order time, so closed trades can be enriched with rich, human-readable detail
   and fed into the performance-memory learning loop.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

# Short codes keep the MT5 comment within the 31-char broker limit while staying
# human-readable and reversible. Format used in comments: "GODMODE_<code>_<type>".
STRATEGY_CODE_BY_NAME: dict[str, str] = {
    "HTF Trend Continuation": "HTFTrend",
    "Liquidity Sweep + Order Block Retest": "LiqSweepOB",
    "London Open Breakout": "LondonBO",
    "New York Reversal / Continuation": "NYRevCont",
    "Asian Range Liquidity Raid": "AsianRaid",
    "VWAP Mean Reversion": "VWAPMR",
    "Volatility Compression Breakout": "VolBreak",
    "Post-News Repricing Strategy": "PostNews",
    "FVG Fill Continuation": "FVGFill",
    "HTF Support/Resistance Rejection": "HTFSR",
    "No-Trade / Standby Strategy": "Standby",
}
NAME_BY_STRATEGY_CODE: dict[str, str] = {v: k for k, v in STRATEGY_CODE_BY_NAME.items()}

ENTRY_TYPE_CODES = {"auto": "A", "scout": "S", "pyramid": "P", "manual": "M", "signal": "G", "execute": "X", "scalp": "K"}
ENTRY_TYPE_LABELS = {"A": "Auto entry", "S": "Scout entry", "P": "Pyramid add", "M": "Manual entry", "G": "Signal entry", "X": "Manual execute", "K": "Scalp (hedge)"}


def strategy_code(name: str | None) -> str:
    if not name:
        return "GodMode"
    return STRATEGY_CODE_BY_NAME.get(name, "".join(w[:1] for w in str(name).split())[:10] or "GodMode")


def comment_for(strategy_name: str | None, entry_type: str = "auto", prefix: str = "GODMODE_") -> str:
    """Build an MT5 comment that encodes the real strategy + entry type, <=31 chars."""
    code = strategy_code(strategy_name)
    tcode = ENTRY_TYPE_CODES.get(str(entry_type).lower(), "A")
    return f"{prefix}{code}_{tcode}"[:31]


def strategy_from_comment(comment: str | None, prefix: str = "GODMODE_") -> str | None:
    """Reverse a stamped comment back to a readable strategy name (best effort)."""
    if not comment:
        return None
    body = str(comment)
    if body.startswith(prefix):
        body = body[len(prefix):]
    # Drop a trailing _<entryTypeCode> if present
    parts = body.split("_")
    if len(parts) >= 2 and parts[-1] in ENTRY_TYPE_LABELS:
        code = "_".join(parts[:-1])
    else:
        code = body
    if code in NAME_BY_STRATEGY_CODE:
        return NAME_BY_STRATEGY_CODE[code]
    # Legacy entry-type comments ("auto_fire", "scout_entry") are NOT strategies.
    legacy = {"auto", "scout", "pyramid", "manual", "signal", "execute", "fire", "add", "entry", "close", "modify", "trigger", "recent", "demo", "record", "seed"}
    tokens = [t for t in code.replace("-", " ").replace("_", " ").split() if t.lower() not in legacy]
    if not tokens:
        return None
    return " ".join(t.capitalize() for t in tokens)


def entry_type_label(comment: str | None) -> str | None:
    if not comment:
        return None
    parts = str(comment).split("_")
    if parts and parts[-1] in ENTRY_TYPE_LABELS:
        return ENTRY_TYPE_LABELS[parts[-1]]
    low = str(comment).lower()
    for key, label in (("auto", "Auto entry"), ("scout", "Scout entry"), ("pyramid", "Pyramid add"), ("manual", "Manual entry"), ("signal", "Signal entry"), ("execute", "Manual execute")):
        if key in low:
            return label
    return None


class TradeContextStore:
    """Persistent ticket -> entry-context map (JSON file, thread-safe)."""

    def __init__(self, path: str | Path = "data/trade_context.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self._recent: list[dict[str, Any]] = []  # fallback matching by symbol/side/price
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = {str(k): v for k, v in raw.get("byTicket", {}).items()}
                    self._recent = list(raw.get("recent", []))[-50:]
            except Exception:
                self._data, self._recent = {}, []

    def _save(self) -> None:
        try:
            # Prune entries older than 120 days to keep the file small.
            cutoff = time.time() - 120 * 86400
            self._data = {k: v for k, v in self._data.items() if float(v.get("ts", time.time())) > cutoff}
            self.path.write_text(json.dumps({"byTicket": self._data, "recent": self._recent[-50:]}, indent=2, default=str), encoding="utf-8")
        except Exception:
            pass

    def record_entry(self, tickets: list[Any], context: dict[str, Any]) -> None:
        """Store entry context under every plausible identifier (order/deal/position)."""
        ctx = {**context, "ts": time.time()}
        with self._lock:
            for t in tickets:
                if t is None:
                    continue
                self._data[str(t)] = ctx
            self._recent.insert(0, ctx)
            del self._recent[50:]
            self._save()

    def get(self, *tickets: Any) -> dict[str, Any] | None:
        with self._lock:
            for t in tickets:
                if t is None:
                    continue
                hit = self._data.get(str(t))
                if hit:
                    return hit
        return None

    def match(self, ticket: Any, position_id: Any, symbol: str | None, side: str | None, entry_price: float | None, open_ts: float | None) -> dict[str, Any] | None:
        """Best-effort attribution: exact ticket first, then a fuzzy recent match."""
        direct = self.get(ticket, position_id)
        if direct:
            return direct
        if not self._recent:
            return None
        best, best_score = None, 0.0
        for ctx in self._recent:
            score = 0.0
            if symbol and str(ctx.get("symbol", "")).upper() == str(symbol).upper():
                score += 1
            if side and str(ctx.get("side", "")).upper() == str(side).upper():
                score += 1
            if entry_price and ctx.get("entry"):
                try:
                    if abs(float(ctx["entry"]) - float(entry_price)) <= max(0.5, float(entry_price) * 0.0008):
                        score += 2
                except Exception:
                    pass
            if open_ts and ctx.get("ts"):
                try:
                    if abs(float(ctx["ts"]) - float(open_ts)) <= 900:  # within 15 min
                        score += 1
                except Exception:
                    pass
            if score > best_score:
                best, best_score = ctx, score
        # Require a reasonably strong fuzzy match (symbol+side+price) before trusting it.
        return best if best_score >= 4 else None
