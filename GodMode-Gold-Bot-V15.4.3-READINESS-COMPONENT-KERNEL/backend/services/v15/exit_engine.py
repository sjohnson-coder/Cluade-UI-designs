from __future__ import annotations

from typing import Any

from .contracts import clamp


# ── V15.0.8 ADAPTIVE EXIT / BREATHING REWRITE ────────────────────────────────
# The previous ratchet was:
#       if peak >= 0.6: floor = max(floor, 0.02)
#       if peak >= 1.0: floor = max(floor, peak - max(0.35, atr_r * 1.2))
#       if peak >= 1.5: floor = max(floor, peak - max(0.28, atr_r))
#
# Two structural faults, both matching the reported symptom "it cuts a trade at
# break-even when it should have relaxed and let the trade breathe":
#
#   1. The 0.6R rung ignored volatility completely. The 1.0R and 1.5R rungs both
#      scale their trail distance by atr_r; the first and most consequential rung
#      did not. On XAUUSD M5, a 0.6R excursion followed by a routine pullback is
#      ordinary noise, not evidence of failure. Snapping the stop to +0.02R at
#      that point converts a large share of eventual winners into scratches — and
#      it does so hardest in exactly the high-volatility conditions where the
#      pullback is most expected.
#
#   2. The ratchet consulted no forward-looking evidence. continuation_probability,
#      recovery_probability and invalidation_probability were all computed, passed
#      in, and then ignored by every rung. A setup with strong continuation
#      evidence was protected on precisely the same schedule as one that was
#      falling apart.
#
# The rewrite keeps the ratchet monotonic (a protected floor is never lowered —
# that invariant is load-bearing and is preserved) but makes both the ARMING
# POINT and the TRAIL WIDTH functions of volatility and evidence.
#
# Sign convention: all *_r values are multiples of initial risk R. floor/stop
# values are the stop's position in R (negative = still at a loss, 0 = entry,
# positive = locked profit).

# Arming point for the first (break-even) rung, in R of peak favourable excursion.
BE_ARM_BASE_R = 0.60
# How much extra peak is required before arming BE when continuation evidence is
# strong. Strong evidence buys the trade room instead of costing it the trade.
BE_ARM_BREATHE_BONUS_R = 0.45
# How much sooner BE arms when invalidation evidence is strong.
BE_ARM_URGENCY_R = 0.25
# Volatility scaling: in a wider-ATR tape the first rung waits proportionally longer.
BE_ARM_ATR_COEFF = 0.55
# Where the break-even floor actually sits once armed. A naked +0.02R does not
# reliably clear spread on XAUUSD, so a "break-even" stop could still exit net
# negative after costs. Scaled off spread when it is known.
BE_FLOOR_MIN_R = 0.04
# Trail width as a multiple of ATR(R), interpolated by continuation evidence.
TRAIL_ATR_MULT_TIGHT = 0.90   # weak continuation -> protect harder
TRAIL_ATR_MULT_LOOSE = 1.70   # strong continuation -> let it run
TRAIL_MIN_WIDTH_R = 0.22
# Peak-retention backstop. Breathing must not become "give it all back".
# Without this, a large peak combined with a wide breathing band could leave the
# stop parked near break-even while 1.5R+ of open profit evaporated, because the
# trail rung had not armed yet. This rung guarantees that once a trade has made a
# genuine excursion, a fixed fraction of the best price seen is always retained.
# 0.62 is the project's long-standing audited profitLockFraction (see
# test_profitlock_fraction_not_regressed), reused here so the shadow engine and
# the live ratchet cannot disagree about how much profit may be surrendered.
PEAK_RETENTION_START_R = 1.00
PEAK_RETENTION_FRACTION = 0.62


class AdaptiveExitEngine:
    """Deterministic, monotonic stop ratchet with volatility- and evidence-aware breathing.

    Deterministic: identical state in -> identical decision out. No randomness, no
    hidden mutable history. The evidence terms are inputs, not internal state, so a
    decision can always be reproduced and audited from its recorded state payload.
    """

    def _breathing_arm_point(self, atr_r: float, continuation: float, invalidation: float, recovery: float) -> float:
        """Peak-R required before the break-even rung arms."""
        arm = BE_ARM_BASE_R
        # Volatility: a 0.6R excursion means far less in a wide tape than a tight one.
        arm += BE_ARM_ATR_COEFF * max(0.0, atr_r - 0.30)
        # Evidence: reward continuation/recovery with room; punish invalidation with speed.
        evidence = clamp(0.65 * continuation + 0.35 * recovery)
        arm += BE_ARM_BREATHE_BONUS_R * max(0.0, (evidence - 0.55) / 0.45)
        arm -= BE_ARM_URGENCY_R * max(0.0, (invalidation - 0.55) / 0.45)
        # Never arm before the trade is genuinely in profit, never wait past 1.25R.
        return max(0.30, min(1.25, arm))

    def _trail_width(self, atr_r: float, continuation: float) -> float:
        """Distance held below peak once trailing."""
        t = clamp(continuation)
        mult = TRAIL_ATR_MULT_TIGHT + (TRAIL_ATR_MULT_LOOSE - TRAIL_ATR_MULT_TIGHT) * t
        return max(TRAIL_MIN_WIDTH_R, atr_r * mult)

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        current = float(state.get("current_r", 0.0))
        peak = max(current, float(state.get("peak_r", current)))
        age = max(0.0, float(state.get("age_seconds", 0.0)))
        recovery = clamp(state.get("recovery_probability", 0.5))
        continuation = clamp(state.get("continuation_probability", 0.5))
        invalidation = clamp(state.get("invalidation_probability", 0.5))
        hard = bool(state.get("hard_invalidation", False))
        atr_r = max(0.05, float(state.get("atr_r", 0.30)))
        current_stop = float(state.get("current_stop_r", -1.0))
        spread_r = max(0.0, float(state.get("spread_r", 0.0)))

        arm_point = self._breathing_arm_point(atr_r, continuation, invalidation, recovery)
        trail_width = self._trail_width(atr_r, continuation)
        # Break-even must clear costs, or "break-even" is a small loss.
        be_floor = max(BE_FLOOR_MIN_R, spread_r * 1.5)

        floor = current_stop
        rungs: list[str] = []
        if peak >= arm_point:
            floor = max(floor, be_floor)
            rungs.append(f"be@{arm_point:.2f}R")
        # Trailing begins a full trail-width above the BE floor, so the trade is never
        # squeezed between two adjacent rungs.
        trail_start = arm_point + trail_width
        if peak >= trail_start:
            floor = max(floor, peak - trail_width)
            rungs.append(f"trail@{trail_start:.2f}R(w={trail_width:.2f})")
        # Retention backstop — independent of the trail rung, so a wide breathing
        # band can never leave a large peak effectively unprotected.
        if peak >= PEAK_RETENTION_START_R:
            retained = peak * PEAK_RETENTION_FRACTION
            if retained > floor:
                floor = retained
                rungs.append(f"retain{PEAK_RETENTION_FRACTION:.2f}x{peak:.2f}R")

        telemetry = {
            "arm_point_r": round(arm_point, 4),
            "trail_width_r": round(trail_width, 4),
            "be_floor_r": round(be_floor, 4),
            "trail_start_r": round(trail_start, 4),
            "rungs_active": rungs,
            "retention_floor_r": round(peak * PEAK_RETENTION_FRACTION, 4) if peak >= PEAK_RETENTION_START_R else None,
            "atr_r": round(atr_r, 4),
            "breathing": peak > 0 and peak < arm_point,
        }

        def out(action: str, priority: str, stop_r: float, reason: str) -> dict[str, Any]:
            return {"action": action, "priority": priority, "recommended_stop_r": stop_r,
                    "reason": reason, "deterministic": True, "breathing": telemetry}

        # 1. Hard invalidation always wins. Structure/policy break is not negotiable.
        if hard or invalidation >= 0.90:
            return out("close", "hard_invalidation", max(floor, current),
                       "Structure or policy hard-invalidated the trade.")

        # 2. Fast fail: adverse excursion WITH invalidation AND weak recovery.
        #    Unchanged in spirit; recovery evidence can now buy a little more time,
        #    because cutting a recoverable trade is the costlier of the two errors here.
        ff_floor = -0.45 - (0.15 if recovery >= 0.60 else 0.0)
        if current <= ff_floor and age >= 45 and invalidation >= 0.65 and recovery < 0.45:
            return out("fast_fail", "loss_asymmetry", current,
                       "Adverse excursion, invalidation and weak recovery align.")

        # 3. Surrendering protected profit without continuation evidence.
        if peak >= trail_start and current <= max(be_floor, floor + 0.05) and continuation < 0.45:
            return out("close", "profit_floor", max(floor, current),
                       "Protected profit is being surrendered without continuation evidence.")

        # 4. Advance the ratchet. Monotonic: only ever tightens.
        if floor > current_stop + 1e-9:
            action = "breakeven" if floor <= be_floor + 1e-9 else "trail"
            return out(action, "profit_protection", floor,
                       f"Ratchet from peak {peak:.2f}R (arm {arm_point:.2f}R, width {trail_width:.2f}R).")

        # 5. Explicit breathing state: in profit but below the arming point. Previously
        #    this window did not exist — 0.6R peak meant an immediate snap to +0.02R.
        if 0 < peak < arm_point and invalidation < 0.65:
            return out("hold", "breathing", current_stop,
                       f"Peak {peak:.2f}R is inside the {arm_point:.2f}R breathing band; "
                       f"protecting now would scratch a trade the evidence still supports.")

        # 6. Time decay.
        if age > 600 and continuation < 0.40 and recovery < 0.40:
            return out("tighten", "time_decay", max(current_stop, current - atr_r * 0.5),
                       "Time decay with weak continuation and recovery.")

        return out("hold", "evidence_hold", current_stop,
                   "No higher-priority deterministic exit condition is active.")
