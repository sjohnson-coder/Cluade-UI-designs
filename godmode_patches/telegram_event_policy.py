"""
Telegram event policy — stops the "Order NOT filled" storm.

Drop-in module for GodMode V15.10.4+. Import it in `backend/app.py` and route the
execution-failure notification through `classify_execution_outcome()` +
`BlockLatch` instead of calling `_telegram_send_text` on every failed dispatch.

WHY THE STORM HAPPENS
---------------------
`_telegram_minimal_category()` routes a message to the "rejection" class only when
the text contains one of:

    "trade rejected" | "order rejected" | "rejection summary" | "order not sent"

The alert that actually fires says **"Order NOT filled"**. It matches none of them,
so it falls through to the "other" class. That single word costs you the throttle:

    rejection ->  key = f"rejection:{bucket}"                  <- ONE alert per window,
                                                                  whatever the reason
    other     ->  key = f"other:{bucket}:{sha256(full_text)}"  <- a NEW alert for every
                                                                  distinct reason string

So every dispatch attempt whose reason text differs by even one character becomes a
separate Telegram message.

That is only half of it. The deeper problem is that a *policy block* (a known
economic-news window, a spread gate, a cooldown) is reported through the same
red "Order NOT filled" channel as a genuine *execution failure* (the broker
rejected a live order). They need opposite handling:

    policy block      -> expected, persistent, self-clearing. Alert ONCE on the
                         transition into the state, once on the way out. Never per attempt.
    execution failure -> unexpected. Alert every time; this is what R48 was protecting.

`classify_execution_outcome()` separates the two. `BlockLatch` makes the policy
class alert on state change instead of on every scan cycle.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Reasons that mean "the system decided not to trade", not "the broker said no".
# Matched against result["reason"] (preferred) or the message text (fallback).
POLICY_REASON_CODES = frozenset({
    "news_blackout", "news_window", "newsBlackout", "newsProtectionUnavailable",
    "spread_gate", "spread_spike", "cooldown", "post_loss_cooldown",
    "session_closed", "market_closed", "weekend", "flat_window",
    "daily_loss_limit", "risk_ceiling", "max_concurrent", "campaign_lock",
    "research_clock", "clock_policy", "validation_lock", "duplicate",
})

POLICY_TEXT_MARKERS = (
    "economic-news window", "economic news window", "news blackout",
    "calendar protection", "spread spike", "spread gate",
    "cooldown", "market is closed", "outside the trading session",
    "daily loss", "risk ceiling", "already at max", "duplicate",
    "research clock", "session weight",
)

# Broker/transport failures. These are the ones R48 was written for.
EXECUTION_FAILURE_MARKERS = (
    "rejected by broker", "requote", "no money", "invalid stops",
    "invalid volume", "market closed by broker", "trade disabled",
    "connection", "timeout", "not connected", "terminal", "retcode",
)


@dataclass(frozen=True)
class Outcome:
    """How a failed dispatch should be surfaced."""
    kind: str               # "policy_block" | "execution_failure" | "unknown"
    reason_code: str        # stable signature for latching
    telegram: bool          # send to Telegram at all?
    category: str           # forces the correct class in _telegram_minimal_category
    headline: str

    @property
    def is_policy(self) -> bool:
        return self.kind == "policy_block"


def classify_execution_outcome(result: dict[str, Any]) -> Outcome:
    """Decide whether a failed dispatch is a policy decision or a real failure."""
    reason = str(result.get("reason") or "").strip()
    message = str(result.get("message") or "")
    lowered = message.lower()

    explicit_policy = any(
        bool(result.get(flag))
        for flag in ("newsBlackout", "policyBlock", "newsProtectionUnavailable",
                     "duplicate", "cooldown")
    )

    if explicit_policy or reason in POLICY_REASON_CODES or any(
        marker in lowered for marker in POLICY_TEXT_MARKERS
    ):
        return Outcome(
            kind="policy_block",
            reason_code=reason or _signature(lowered),
            telegram=True,                      # once per episode, via BlockLatch
            category="rejection",               # collapsing key: rejection:{bucket}
            headline="⏸️ GodMode — entries paused",
        )

    if any(marker in lowered for marker in EXECUTION_FAILURE_MARKERS):
        return Outcome(
            kind="execution_failure",
            reason_code=reason or _signature(lowered),
            telegram=True,                      # always: this is a real problem
            category="rejection",
            headline="🔴 GodMode — order rejected by broker",
        )

    return Outcome(
        kind="unknown",
        reason_code=reason or _signature(lowered),
        telegram=True,
        category="rejection",
        headline="🔴 GodMode — order not filled",
    )


def _signature(lowered: str) -> str:
    """Stable signature from the first clause, so volatile numbers don't split keys."""
    head = lowered.split(".")[0][:60]
    return "".join(ch for ch in head if ch.isalnum() or ch == " ").strip().replace(" ", "_")


@dataclass
class BlockLatch:
    """Alert on the *transition* into a blocking state, not on every attempt.

    Suppressed attempts are counted so the all-clear can report what was skipped.
    """
    remind_after_seconds: float = 900.0
    _active: dict[str, dict[str, Any]] = field(default_factory=dict)

    def should_alert(self, reason_code: str, now: float | None = None) -> tuple[bool, dict[str, Any]]:
        now = time.time() if now is None else now
        state = self._active.get(reason_code)

        if state is None:
            self._active[reason_code] = {
                "since": now, "last_alert": now, "suppressed": 0, "attempts": 1,
            }
            return True, {"transition": "entered", "suppressed": 0, "attempts": 1}

        state["attempts"] += 1
        if now - state["last_alert"] >= self.remind_after_seconds:
            info = {
                "transition": "reminder",
                "suppressed": state["suppressed"],
                "attempts": state["attempts"],
                "blocked_for_seconds": round(now - state["since"], 1),
            }
            state["last_alert"] = now
            state["suppressed"] = 0
            return True, info

        state["suppressed"] += 1
        return False, {"transition": "suppressed", "suppressed": state["suppressed"],
                       "attempts": state["attempts"]}

    def clear(self, reason_code: str, now: float | None = None) -> dict[str, Any] | None:
        """Call when a dispatch succeeds, or the blocking condition lifts."""
        state = self._active.pop(reason_code, None)
        if state is None:
            return None
        now = time.time() if now is None else now
        return {
            "transition": "cleared",
            "blocked_for_seconds": round(now - state["since"], 1),
            "attempts": state["attempts"],
            "suppressed": state["suppressed"],
        }

    def clear_all(self, now: float | None = None) -> list[dict[str, Any]]:
        return [c for c in (self.clear(k, now) for k in list(self._active)) if c]

    @property
    def active_reasons(self) -> list[str]:
        return sorted(self._active)


def format_block_message(outcome: Outcome, result: dict[str, Any],
                         side: str, volume: Any, info: dict[str, Any]) -> str:
    """One clear message per episode instead of one per retry."""
    reason = str(result.get("message") or "Unknown reason")[:300]
    lines = [f"*{outcome.headline}*"]

    if outcome.is_policy:
        lines.append(f"{reason}")
        if info.get("transition") == "reminder":
            mins = info.get("blocked_for_seconds", 0) / 60.0
            lines.append(
                f"_Still active after {mins:.0f} min · "
                f"{info.get('attempts', 0)} setups skipped._"
            )
        else:
            lines.append("_No order was sent. Entries resume automatically._")
    else:
        lines.append(f"*{side} XAUUSD* · {volume} lots")
        lines.append(f"Reason: {reason}")
        lines.append("The dispatched order did not reach the broker or was rejected.")
    return "\n".join(lines)


def format_clear_message(reason_code: str, info: dict[str, Any]) -> str:
    mins = info.get("blocked_for_seconds", 0) / 60.0
    skipped = info.get("attempts", 0)
    return (
        "*🟢 GodMode — entries resumed*\n"
        f"`{reason_code}` cleared after {mins:.0f} min.\n"
        f"_{skipped} setup(s) were skipped while it was active._"
    )
