from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .calibration import empirical_calibrate
from .contracts import clamp


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, x))))


class ProbabilityEngine:
    """Heuristic shadow scores with persistent empirical calibration.

    Scores remain explicitly labelled heuristic until sufficient labelled samples exist.
    """
    def __init__(self, calibration_path: Path | None = None):
        self.path = Path(calibration_path) if calibration_path else None
        self._lock = threading.RLock()
        self.calibration: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        if self.path and self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self.calibration = dict(payload.get("horizons") or {})
                self.events = list(payload.get("events") or [])[-2000:]
            except Exception:
                self.calibration = {}
                self.events = []

    def _persist_locked(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "updated_at": time.time(), "horizons": self.calibration, "events": self.events[-2000:]}
        temp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        temp.write_text(encoded, encoding="utf-8")
        os.replace(temp, self.path)

    def record(self, horizon: str, probability: float, outcome: bool, decision_id: str | None = None) -> None:
        horizon = str(horizon)
        probability = clamp(probability)
        with self._lock:
            bucket = self.calibration.setdefault(horizon, {"wins": 0, "samples": 0, "brier_sum": 0.0})
            bucket["samples"] = int(bucket.get("samples", 0)) + 1
            bucket["wins"] = int(bucket.get("wins", 0)) + int(bool(outcome))
            bucket["brier_sum"] = float(bucket.get("brier_sum", 0.0)) + (probability - int(bool(outcome))) ** 2
            bucket["brier"] = bucket["brier_sum"] / bucket["samples"]
            self.events.append({"decision_id": decision_id, "horizon": horizon, "probability": probability, "outcome": bool(outcome), "at": time.time()})
            self._persist_locked()

    def record_trade_outcome(self, report: dict[str, Any], won: bool) -> None:
        probs = ((report or {}).get("forecast") or {}).get("probabilities") or {}
        decision_id = (report or {}).get("decision_id")
        mappings = {
            "continuation": won,
            "tp_before_sl": won,
            "be_first": won,
            "fast_fail": not won,
            "invalidation": not won,
        }
        for horizon, outcome in mappings.items():
            if horizon in probs:
                self.record(horizon, float(probs[horizon]), outcome, decision_id=decision_id)

    def calibration_progress(self, target: int = 200) -> dict[str, Any]:
        """Return calibration maturity for the primary win-probability horizon."""
        with self._lock:
            horizons = {k: dict(v) for k, v in self.calibration.items()}
        primary = horizons.get("tp_before_sl") or {}
        samples = int(primary.get("samples", 0))
        brier = primary.get("brier")
        verdict = "insufficient data"
        if samples >= target and isinstance(brier, (int, float)):
            verdict = (
                "informative — probabilities beat a 50% baseline"
                if float(brier) < 0.25
                else "uninformative — no better than a 50% baseline"
            )
        return {
            "samples": samples,
            "target": target,
            "remaining": max(0, target - samples),
            "percent": round(min(100.0, (samples / target) * 100.0), 1) if target else 0.0,
            "brier": round(float(brier), 4) if isinstance(brier, (int, float)) else None,
            "brierBaseline": 0.25,
            "isCalibrated": samples >= target,
            "verdict": verdict,
            "horizons": {
                key: {
                    "samples": int(value.get("samples", 0)),
                    "brier": round(float(value["brier"]), 4)
                    if isinstance(value.get("brier"), (int, float)) else None,
                }
                for key, value in horizons.items()
            },
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps({"horizons": self.calibration, "events": self.events[-2000:]}))

    def forecast(self, features: dict[str, Any], regime: dict[str, Any], broker: dict[str, Any], external: dict[str, Any] | None = None) -> dict[str, Any]:
        external = external or {}
        trend = clamp(features.get("trend", 0.5)); momentum = clamp(features.get("momentum", 0.5))
        structure = clamp(features.get("structure", 0.5)); extension = clamp(features.get("extension", 0.5))
        spread = clamp(features.get("spread_quality", broker.get("quality", 0.5))); recovery_evidence = clamp(features.get("recovery_evidence", 0.5))
        regime_conf = clamp(regime.get("confidence", 0.5)); broker_q = clamp(broker.get("quality", 0.5))
        news_risk = clamp(external.get("risk_bias", features.get("news_risk", 0.0)))
        external_uncertainty = clamp(external.get("uncertainty", 1.0))
        regime_bonus = 0.25 if regime.get("primary") in {"strong_trend", "expansion"} else (-0.2 if regime.get("primary") in {"mean_reversion", "news_driven", "low_liquidity"} else 0.0)
        continuation = _sigmoid(-1.1 + 1.4 * trend + 1.15 * momentum + 1.1 * structure + 0.6 * spread + 0.5 * broker_q + regime_bonus - 1.0 * extension - 0.45 * news_risk)
        reversal = _sigmoid(-0.5 + 1.3 * extension + 0.7 * (1 - momentum) + 0.6 * (1 - structure) - 0.6 * trend + 0.35 * news_risk)
        recovery = _sigmoid(-1.0 + 1.5 * recovery_evidence + 0.75 * structure + 0.45 * trend + 0.3 * broker_q - 0.9 * extension - 0.25 * news_risk)
        invalidation = _sigmoid(-1.2 + 1.25 * (1 - structure) + 0.8 * reversal + 0.5 * (1 - broker_q) + 0.35 * news_risk)
        raw = {
            "continuation": continuation,
            "reversal": reversal,
            "recovery": recovery,
            "tp_before_sl": _sigmoid(-0.7 + 1.2 * continuation + 0.7 * spread + 0.5 * broker_q - 0.8 * invalidation - 0.25 * news_risk),
            "be_first": _sigmoid(-0.5 + 0.9 * continuation + 0.5 * momentum + 0.3 * broker_q - 0.15 * news_risk),
            "fast_fail": _sigmoid(-0.9 + 1.4 * invalidation + 0.9 * reversal + 0.4 * (1 - broker_q) + 0.25 * news_risk),
            "burst_success": _sigmoid(-1.0 + 1.25 * continuation + 0.7 * trend + 0.45 * broker_q - 1.0 * extension - 0.5 * news_risk),
            "invalidation": invalidation,
        }
        probabilities = {}
        with self._lock:
            for key, value in raw.items():
                cal = self.calibration.get(key, {})
                probabilities[key] = empirical_calibrate(value, int(cal.get("wins", 0)), int(cal.get("samples", 0)))
        broker_uncertainty = clamp(broker.get("uncertainty", 1.0))
        # V15.0.8 — WHY A "92% CONFIDENCE" TRADE COULD LOSE.
        # This quantity measures INPUT-DATA QUALITY (is the regime classifier sure? is the
        # broker feed clean? is the news feed reachable? is the score decisive?). It says
        # NOTHING about whether the trade will win. It was previously surfaced as
        # `confidence`, so the UI showed "92% confidence" on a setup whose actual modelled
        # win probability was near a coin flip. The number was never wrong — it was
        # answering a different question than the one the operator was asking.
        # It is now named for what it measures, and the win probability is surfaced
        # separately and explicitly below.
        # Ambiguous scores near 0.5 increase uncertainty; decisive scores reduce it.
        # The previous formula did the opposite and penalised strong evidence.
        model_ambiguity = 1.0 - abs(0.5 - continuation) * 2.0
        data_uncertainty = clamp(
            0.4 * (1 - regime_conf)
            + 0.25 * broker_uncertainty
            + 0.2 * external_uncertainty
            + 0.15 * model_ambiguity
        )
        uncertainty = data_uncertainty
        contributions = [
            {"feature": "trend", "value": trend, "impact": round((trend - 0.5) * 1.4, 4)},
            {"feature": "momentum", "value": momentum, "impact": round((momentum - 0.5) * 1.15, 4)},
            {"feature": "structure", "value": structure, "impact": round((structure - 0.5) * 1.1, 4)},
            {"feature": "extension", "value": extension, "impact": round(-(extension - 0.5), 4)},
            {"feature": "broker_quality", "value": broker_q, "impact": round((broker_q - 0.5) * 0.5, 4)},
            {"feature": "news_risk", "value": news_risk, "impact": round(-news_risk * 0.45, 4)},
        ]
        # Calibration status must be tied to the probability presented as the win
        # chance. Summing samples across correlated horizons made one trade count
        # up to five times and could label the model calibrated after ~40 trades.
        target_samples = int(self.calibration.get("tp_before_sl", {}).get("samples", 0))
        total_label_events = sum(int(v.get("samples", 0)) for v in self.calibration.values())
        is_calibrated = target_samples >= 200
        return {
            "probabilities": probabilities,
            "score_type": "empirically_calibrated_probability" if is_calibrated else "heuristic_shadow_score",
            "calibration_samples": target_samples,
            "calibration_label_events": total_label_events,
            "uncertainty": uncertainty,
            # ── The three numbers below answer three DIFFERENT questions. ──
            # data_confidence: "how trustworthy are my inputs?"  (NOT a win rate)
            "data_confidence": clamp(1 - data_uncertainty),
            # win_probability: "what fraction of setups like this actually reach TP
            # before SL?" This is the ONLY number that may be presented as a win chance.
            "win_probability": probabilities["tp_before_sl"],
            # is_calibrated: until enough labelled outcomes exist, every probability here
            # is a hand-tuned sigmoid, not a learned estimate. The UI must not present an
            # uncalibrated score as if it were a measured win rate.
            "is_calibrated": is_calibrated,
            # Back-compat: existing consumers read `confidence`. It now carries the
            # honest quantity (win probability) rather than the data-quality score.
            "confidence": probabilities["tp_before_sl"],
            "confidence_basis": "tp_before_sl" if is_calibrated else "tp_before_sl_uncalibrated_heuristic",
            "expected_mfe_r": max(0.0, 0.2 + 2.2 * probabilities["continuation"] - 0.7 * extension),
            "expected_mae_r": max(0.0, 0.15 + 1.5 * probabilities["invalidation"] + 0.35 * (1 - broker_q)),
            "expected_hold_seconds": int(60 + 900 * (1 - probabilities["fast_fail"]) + 360 * probabilities["continuation"]),
            "contributions": contributions,
        }
