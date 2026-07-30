from __future__ import annotations

from typing import Any

from .contracts import clamp


class BurstIntelligence:
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        checks = [
            # V15.0.8 — the old pair of gates was effectively unreachable in combination.
            # `base_protected` only became true once the ratchet had armed, and the old
            # ratchet armed at peak >= 0.60R; `minimum_profit` then separately demanded
            # CURRENT profit >= 0.60R. A trade that armed at 0.60R and pulled back even
            # slightly satisfied neither, so the burst window was a razor-thin band that
            # in practice almost never opened.
            # Requested behaviour: allow burst as the base trade APPROACHES protection,
            # provided the win evidence is strong. `approaching_protection` is supplied by
            # the caller from the exit engine's live arm_point, so the two engines cannot
            # drift apart.
            ("base_secured", bool(context.get("base_protected")) or bool(context.get("approaching_protection")),
             "Base trade must be protected, or within reach of its protection point."),
            ("minimum_profit", float(context.get("base_profit_r", 0)) >= float(context.get("min_base_profit_r", 0.35)),
             f"Base trade requires at least {float(context.get('min_base_profit_r', 0.35)):.2f}R profit."),
            ("continuation", clamp(context.get("continuation_probability", 0)) >= 0.65, "Continuation probability must be at least 65%."),
            ("burst_probability", clamp(context.get("burst_success_probability", 0)) >= 0.60, "Burst success probability must be at least 60%."),
            ("broker_quality", clamp(context.get("broker_quality", 0)) >= 0.55, "Broker quality is below the safe threshold."),
            ("bridge_ready", bool(context.get("bridge_ready")), "Tick Guard/bridge acknowledgement is unavailable."),
            ("exposure", float(context.get("exposure_r", 0)) < float(context.get("max_exposure_r", 0.8)), "Exposure cap reached."),
            ("cooldown", not bool(context.get("cooldown_active")), "Burst cooldown is active."),
            ("extension", float(context.get("extension", 1)) <= float(context.get("max_extension", 0.8)), "Move is too extended."),
            ("risk_reward", float(context.get("risk_reward", 0)) >= 1.2, "Expected reward-to-risk is too low."),
        ]
        gates = [{"name": name, "passed": passed, "reason": reason if not passed else "Passed"} for name, passed, reason in checks]
        allowed = all(x[1] for x in checks)
        p = clamp(context.get("burst_success_probability", 0)); rr = max(0.0, float(context.get("risk_reward", 0)))
        expected_value = p * rr - (1 - p)
        return {"allowed": allowed and expected_value > 0, "expected_value_r": expected_value, "gates": gates, "blocked_by": [g["name"] for g in gates if not g["passed"]], "risk_contribution_r": max(0.0, float(context.get("max_exposure_r", 0.8)) - float(context.get("exposure_r", 0)))}
