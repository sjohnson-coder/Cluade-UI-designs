from __future__ import annotations
import logging

import math
import os

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover
    mt5 = None

SUCCESS_RETCODES = {10008, 10009, 10010}


class BrokerSpecificLotSizer:
    def symbol_specs(self, symbol):
        if mt5:
            try:
                mt5.initialize()
                info = mt5.symbol_info(symbol)
                if info:
                    return {
                        "symbol": symbol,
                        "point": float(info.point or 0.01),
                        "digits": int(info.digits or 2),
                        "tradeTickSize": float(info.trade_tick_size or 0.01),
                        "tradeTickValue": float(info.trade_tick_value or 1),
                        "contractSize": float(info.trade_contract_size or 100),
                        "volumeMin": float(info.volume_min or 0.01),
                        "volumeStep": float(info.volume_step or 0.01),
                        "volumeMax": float(info.volume_max or 100),
                        "source": "mt5",
                    }
            except Exception as _suppressed_exc:
                logging.getLogger(__name__).warning("Recoverable failure in live_execution.py:33: %s", _suppressed_exc)
        return {"symbol": symbol, "point": 0.01, "digits": 2, "tradeTickSize": 0.01, "tradeTickValue": 1.0, "contractSize": 100.0, "volumeMin": 0.01, "volumeStep": 0.01, "volumeMax": 100.0, "source": "fallback_xauusd_specs"}

    def calculate(self, payload):
        symbol = str(payload.get("symbol", "XAUUSD"))
        equity = float(payload.get("equity", 10000))
        risk = float(payload.get("riskPct", 1))
        entry = float(payload.get("entry", 2385))
        sl = float(payload.get("sl", 2375))
        specs = self.symbol_specs(symbol)
        risk_money = equity * risk / 100
        dist = abs(entry - sl)
        val = (dist / (specs["tradeTickSize"] or 0.01)) * (specs["tradeTickValue"] or 1)
        raw = risk_money / val if val > 0 else specs["volumeMin"]
        lot = self.norm(raw, specs["volumeMin"], specs["volumeStep"], specs["volumeMax"])
        return {"symbol": symbol, "equity": equity, "riskPct": risk, "riskMoney": round(risk_money, 2), "entry": entry, "sl": sl, "stopDistance": round(dist, 5), "specs": specs, "rawLot": round(raw, 4), "lot": lot, "formula": "lot = riskMoney / ((abs(entry-sl)/tickSize) * tickValue), normalised to broker min/step/max", "status": "broker_specific" if specs["source"] == "mt5" else "fallback_specs"}

    def norm(self, raw, minv, step, maxv):
        raw = max(minv, min(raw, maxv))
        return round(max(minv, min(minv + math.floor((raw - minv) / step + 1e-9) * step, maxv)), 2)


class LiveExecutionManager:
    def __init__(self, lot_sizer):
        self.lot_sizer = lot_sizer
        self.live_enabled = os.getenv("GODMODE_ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.magic = int(os.getenv("GODMODE_MAGIC_NUMBER", "20250525"))
        self.comment_prefix = os.getenv("GODMODE_COMMENT_PREFIX", "GODMODE_")

    def partial_close(self, payload):
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Partial-close request validated. Live trading disabled.", "request": payload}
        if not mt5:
            return {"ok": False, "message": "MetaTrader5 unavailable"}
        ticket = int(payload["ticket"])
        explicit_volume = payload.get("volume")
        percent = float(payload.get("percent", payload.get("percentage", 0)) or 0)
        deviation = int(payload.get("deviation", 30))
        mt5.initialize()
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return {"ok": False, "message": f"Position {ticket} not found"}
        p = pos[0]
        specs = self.lot_sizer.symbol_specs(p.symbol)
        volume = float(explicit_volume) if explicit_volume is not None else float(p.volume) * max(0.0, min(percent, 100.0)) / 100.0
        volume = self.lot_sizer.norm(volume, specs["volumeMin"], specs["volumeStep"], specs["volumeMax"])
        if volume <= 0 or volume > float(p.volume):
            return {"ok": False, "message": "Invalid partial-close volume", "requestedVolume": volume, "positionVolume": float(p.volume)}
        tick = mt5.symbol_info_tick(p.symbol)
        typ = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if typ == mt5.ORDER_TYPE_SELL else tick.ask
        req = {"action": mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": p.symbol, "volume": volume, "type": typ, "price": price, "deviation": deviation, "magic": self.magic, "comment": f"{self.comment_prefix}TP partial", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req)
        return {"ok": bool(res and res.retcode in SUCCESS_RETCODES), "result": res._asdict() if res else str(mt5.last_error())}

    def modify_trailing_stop(self, payload):
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Trailing-stop modify request validated. Live trading disabled.", "request": payload}
        if not mt5:
            return {"ok": False, "message": "MetaTrader5 unavailable"}
        ticket = int(payload["ticket"])
        mt5.initialize()
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return {"ok": False, "message": f"Position {ticket} not found"}
        p = pos[0]
        req = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol, "sl": float(payload["newSl"]), "tp": float(payload.get("newTp", 0) or p.tp), "magic": self.magic, "comment": f"{self.comment_prefix}trail update"}
        res = mt5.order_send(req)
        return {"ok": bool(res and res.retcode in SUCCESS_RETCODES), "result": res._asdict() if res else str(mt5.last_error())}

    def pyramid_execute(self, payload, validation):
        if not validation.get("allowed"):
            return {"ok": False, "blocked": True, "validation": validation, "message": "AI exposure validation blocked pyramid add."}
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Pyramid order validated. Live trading disabled.", "validation": validation, "request": payload}
        # Kept as a second-stage safety boundary: live pyramid orders should use MT5Bridge.execute
        # from app.py after both the AI plan and exposure validator have passed.
        return {"ok": False, "message": "Live pyramid execution must be routed through MT5Bridge.execute after demo verification.", "validation": validation}


class ExposureValidator:
    """Second safety wall after the AI pyramiding engine."""

    def validate_pyramid(self, payload):
        plan = payload.get("plan") or payload.get("pyramidingPlan") or {}
        risk_governor = plan.get("riskGovernor") or payload.get("riskGovernor") or {}
        stage = plan.get("currentStage") or payload.get("stage") or {}
        stage_role = str(stage.get("role", payload.get("stageRole", "")))
        current_exposure = float(payload.get("currentExposurePct", risk_governor.get("projectedTotalExposurePct", 0.0)) or 0)
        add_risk = float(payload.get("addRiskPct", payload.get("riskPct", 0.35)) or 0.35)
        current_stack = float(payload.get("currentStackRiskPct", payload.get("openRiskPct", 0.0)) or 0)
        max_stack = float(payload.get("maxStackRiskPct", risk_governor.get("maxStackRiskPct", 1.25)) or 1.25)
        max_total = float(payload.get("maxTotalExposurePct", risk_governor.get("maxTotalExposurePct", 3.0)) or 3.0)
        max_total_lots = float(payload.get("maxTotalLots", risk_governor.get("maxTotalLots", 0.11)) or 0.11)
        base_lot = float(payload.get("baseLot", plan.get("baseLot", 0.01)) or 0.01)
        add_lot = float(payload.get("addLot", payload.get("volume", plan.get("nextLot", 0.02))) or 0.02)
        current_lots = float(payload.get("currentLots", base_lot) or base_lot)
        projected_total_lots = round(current_lots + add_lot, 2)
        add_number = int(payload.get("addNumber", payload.get("pyramidAdds", plan.get("currentAdds", 0)) or 0)) + 1
        floating_r = float(payload.get("floatingR", payload.get("profitR", 0.0)) or 0)
        min_floating_r = float(payload.get("minFloatingR", plan.get("nextAdd", {}).get("min_profit_r", 0.85)) or 0.85)
        locked_profit_r = float(payload.get("lockedProfitR", plan.get("signals", {}).get("lockedProfitR", 0.0)) or 0.0)
        margin_level = float(payload.get("marginLevelPct", payload.get("marginLevel", 0)) or 0)
        min_margin_level = float(payload.get("minMarginLevelPct", 400) or 400)
        spread = float(payload.get("spread", 0.12) or 0.12)
        max_spread = float(payload.get("maxSpread", 0.24) or 0.24)
        win_streak = int(payload.get("winStreak", payload.get("winsSinceLastLoss", 0)) or 0)
        trend_alignment = float(payload.get("trendAlignmentScore", payload.get("htfAlignmentScore", plan.get("signals", {}).get("trendAlignmentScore", 0))) or 0)
        liquidity_room = float(payload.get("liquidityRoomScore", payload.get("roomToTargetScore", plan.get("signals", {}).get("liquidityRoomScore", 0))) or 0)
        extension_atr = float(payload.get("extensionAtr", plan.get("signals", {}).get("extensionAtr", 99.0)) or 0)
        blocks: list[str] = []
        if plan and plan.get("allowed") is False:
            blocks.append("AI pyramiding plan is not allowed")
        if current_stack + add_risk > max_stack:
            blocks.append("Pyramid stack risk exceeds max stack cap")
        if current_exposure + add_risk > max_total:
            blocks.append("Total exposure cap exceeded")
        if projected_total_lots > max_total_lots:
            blocks.append("Total lot cap exceeded")
        if not payload.get("breakEvenProtected", payload.get("beMoved", False)):
            blocks.append("Initial position is not break-even protected")
        if payload.get("allPriorAddsProtected", payload.get("previousAddsProtected", False)) is not True:
            blocks.append("All previous pyramid legs must be protected before a new add")
        if floating_r < min_floating_r:
            blocks.append("Trade has not proved itself enough for pyramid add")
        if margin_level < min_margin_level:
            blocks.append("Margin level below safe floor")
        if spread > max_spread:
            blocks.append("Spread too high for pyramid execution")
        if win_streak < 2:
            blocks.append("Protected aggressive scaling requires at least two recent wins")
        if payload.get("newsBlackout", False):
            blocks.append("News blackout blocks pyramid execution")
        if payload.get("dirtyConditions", False):
            blocks.append("Dirty conditions block pyramid execution")
        if payload.get("structureValid", False) is not True:
            blocks.append("Structure invalidation blocks pyramid execution")
        if payload.get("momentumDivergence", False):
            blocks.append("Momentum divergence blocks pyramid execution")
        if payload.get("previousPyramidAddFailed", False):
            blocks.append("Previous pyramid add failed; new adds blocked for this session")
        if add_number >= 2 and trend_alignment < 91:
            blocks.append("Third trade/add requires clean HTF trend alignment")
        if add_number >= 2 and liquidity_room < 75:
            blocks.append("Third trade/add requires enough remaining target room")
        if add_number >= 2 and extension_atr > 0.90:
            blocks.append("Third trade/add would chase an extended move")
        if add_number >= 3:
            if trend_alignment < 96:
                blocks.append("Final rare add requires exceptional HTF trend alignment")
            if liquidity_room < 88:
                blocks.append("Final rare add requires exceptional remaining liquidity/target room")
            if extension_atr > 0.65:
                blocks.append("Final rare add blocked because the move is too extended")
            if locked_profit_r < 1.20:
                blocks.append("Final rare add requires at least 1.20R locked profit buffer")
            if spread > max_spread * 0.65:
                blocks.append("Final rare add requires premium-low spread")
        decision = "ALLOW_PROVE_CONFIRM_PRESS_PYRAMID_ADD" if not blocks else "BLOCK_PROVE_CONFIRM_PRESS_PYRAMID_ADD"
        return {"allowed": not blocks, "blocks": blocks, "stageRole": stage_role, "addNumber": add_number, "currentExposurePct": round(current_exposure, 3), "addRiskPct": round(add_risk, 3), "newStackRiskPct": round(current_stack + add_risk, 3), "projectedTotalExposurePct": round(current_exposure + add_risk, 3), "maxStackRiskPct": max_stack, "maxTotalExposurePct": max_total, "baseLot": round(base_lot, 2), "addLot": round(add_lot, 2), "currentLots": round(current_lots, 2), "projectedTotalLots": projected_total_lots, "maxTotalLots": max_total_lots, "marginLevelPct": margin_level, "minMarginLevelPct": min_margin_level, "fastGuard": plan.get("fastGuard") or {"cutNewestAddAtNegativeR": -0.22, "moveAddToBreakEvenAtR": 0.35, "exitOrder": "newest_and_largest_add_first"}, "decision": decision}
