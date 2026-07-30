from __future__ import annotations

import math
from typing import Any


class MultiTargetTradeManager:
    """TP1-TP4 and live trade-management decision helper.

    The child-order builder is deliberately conservative: it never creates more
    child volume than the requested total and never creates zero-volume legs.
    Small accounts using 0.01 lots therefore receive a reduced TP plan instead
    of an unsafe over-allocation.
    """

    def _default_targets(self, side: str, entry: float, sl: float) -> list[float]:
        risk = abs(entry - sl) or 1.0
        rr = [1.0, 1.8, 2.7, 4.0]
        return [entry + risk * x if side == "BUY" else entry - risk * x for x in rr]

    def _split_volumes(self, total_volume: float, target_count: int, min_volume: float = 0.01, step: float = 0.01) -> tuple[list[float], list[str]]:
        warnings: list[str] = []
        total_volume = max(0.0, round(float(total_volume), 2))
        if total_volume < min_volume:
            return [], ["Requested volume is below broker minimum lot."]
        max_legs = max(1, int(math.floor(total_volume / min_volume + 1e-9)))
        leg_count = min(target_count, max_legs)
        if leg_count < target_count:
            warnings.append("Volume too small to split across all TP targets; child-order count reduced to avoid oversized exposure.")
        volumes: list[float] = []
        remaining = total_volume
        for idx in range(leg_count):
            if idx < leg_count - 1:
                vol = min_volume
            else:
                steps = math.floor((remaining - min_volume) / step + 1e-9)
                vol = round(min_volume + max(0, steps) * step, 2)
            remaining = round(max(0.0, remaining - vol), 2)
            if vol >= min_volume:
                volumes.append(vol)
        if round(sum(volumes), 2) > total_volume:
            return [], ["Safety block: split child volume exceeds requested volume."]
        return volumes, warnings

    def build_child_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        def blocked(message: str) -> dict[str, Any]:
            return {
                "ok": False,
                "mode": "split-child-positions",
                "childOrders": [],
                "warnings": [message],
            }

        if not isinstance(payload, dict):
            return blocked("Trade plan must be an object.")
        side = str(payload.get("side") or payload.get("direction") or "").upper()
        if side not in {"BUY", "SELL"}:
            return blocked("An explicit BUY or SELL side is required.")
        try:
            entry = float(payload.get("entry", payload.get("price")))
            sl = float(payload.get("sl"))
            volume = float(payload.get("volume"))
        except (TypeError, ValueError):
            return blocked("Entry, stop loss and volume must be finite numeric values.")
        if not all(math.isfinite(value) for value in (entry, sl, volume)):
            return blocked("Entry, stop loss and volume must be finite numeric values.")
        if entry <= 0 or sl <= 0 or volume <= 0:
            return blocked("Entry, stop loss and volume must be greater than zero.")
        if (side == "BUY" and sl >= entry) or (side == "SELL" and sl <= entry):
            return blocked(f"{side} stop loss must be on the loss side of entry.")

        raw_targets = [payload.get("tp1"), payload.get("tp2"), payload.get("tp3"), payload.get("tp4")]
        try:
            targets = [float(t) for t in raw_targets if t not in (None, "")]
        except (TypeError, ValueError):
            return blocked("Every take-profit target must be numeric.")
        if any(not math.isfinite(target) for target in targets):
            return blocked("Every take-profit target must be finite.")
        if not targets:
            targets = self._default_targets(side, entry, sl)
        if any(
            (side == "BUY" and target <= entry) or (side == "SELL" and target >= entry)
            for target in targets
        ):
            return blocked(f"Every {side} take-profit target must be on the profit side of entry.")
        if any(
            (side == "BUY" and later <= earlier) or (side == "SELL" and later >= earlier)
            for earlier, later in zip(targets, targets[1:])
        ):
            return blocked("TP1-TP4 targets must progress farther into profit.")
        volumes, warnings = self._split_volumes(volume, len(targets))
        if not volumes:
            return {"ok": False, "mode": "split-child-positions", "childOrders": [], "warnings": warnings}
        selected_targets = targets[: len(volumes)]
        child_orders = []
        for i, (tp, leg_volume) in enumerate(zip(selected_targets, volumes), start=1):
            child_orders.append({
                "leg": f"TP{i}",
                "symbol": payload.get("symbol", "XAUUSD"),
                "side": side,
                "volume": leg_volume,
                "entry": round(entry, 2),
                "sl": round(sl, 2),
                "tp": round(tp, 2),
                "management": self.management_rule(i),
                "source": "godmode_bot",
            })
        return {
            "ok": True,
            "mode": "split-child-positions",
            "childOrders": child_orders,
            "totalChildVolume": round(sum(float(o["volume"]) for o in child_orders), 2),
            "requestedVolume": round(volume, 2),
            "warnings": warnings,
            "note": "MT5 supports one TP per position; TP1-TP4 is handled by split positions or managed partial closes.",
        }

    def management_rule(self, leg: int) -> str:
        return {
            1: "Close partial, move remaining SL to break-even plus costs after TP1.",
            2: "Trail remaining behind M5 structure after TP2.",
            3: "Switch runner to ATR/liquidity trail after TP3.",
            4: "Final runner target at HTF liquidity/session extreme.",
        }.get(leg, "Manage by structure")

    def live_management_decision(self, position: dict[str, Any]) -> dict[str, Any]:
        profit_r = float(position.get("profitR", position.get("floatingR", 0)) or 0)
        dirty = bool(position.get("dirtyConditions", position.get("newsBlackout", False)))
        structure_valid = bool(position.get("structureValid", True))
        setup_invalidated = bool(position.get("setupInvalidated", False))
        be_moved = bool(position.get("beMoved", position.get("breakEvenProtected", False)))
        momentum = str(position.get("momentum", "normal")).lower()
        spread_spike = bool(position.get("spreadSpike", False))
        add_number = int(position.get("pyramidAddNumber", 0) or 0)
        no_progress_candles = int(position.get("noProgressCandles", 0) or 0)

        if dirty or spread_spike:
            return {"action": "STOP_TRADING_DIRTY_CONDITIONS", "reason": "Market/news/spread conditions are dirty; block new entries and protect open trades."}
        if setup_invalidated or not structure_valid:
            return {"action": "FAST_FAIL_CLOSE", "reason": "Setup or structure invalidated before full stop; cut exposure quickly."}
        if add_number and (profit_r <= -0.22 or no_progress_candles >= 3):
            return {"action": "CUT_NEWEST_PYRAMID_ADD", "reason": "Newest pyramid add failed fast-guard progress rules."}
        if profit_r >= 1.0 and not be_moved:
            return {"action": "MOVE_TO_BREAKEVEN", "reason": "Trade is above +1R; move SL to break-even plus costs before any pyramid add."}
        if profit_r >= 2.4 and momentum in {"expanding", "strong", "clean"}:
            return {"action": "PUSH_TP", "reason": "Winner is clean above TP2/TP3 zone; extend runner toward higher-timeframe liquidity."}
        if profit_r >= 1.8:
            return {"action": "TRAIL_STRUCTURE", "reason": "Winner is mature; trail behind M5/M15 structure."}
        if profit_r > 0.35:
            return {"action": "HOLD_WINNER", "reason": "Trade is working; hold while structure remains clean."}
        return {"action": "HOLD", "reason": "Trade is within planned management rules."}
