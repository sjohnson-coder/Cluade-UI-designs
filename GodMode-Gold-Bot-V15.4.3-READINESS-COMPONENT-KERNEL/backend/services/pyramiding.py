from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PyramidSettings:
    """Protected anti-martingale pyramid settings.

    Pyramid philosophy implemented here:
    - First trade = prove direction.
    - Second trade/add 1 = reward confirmation.
    - Third trade/add 2 = press only if the trend remains clean.
    - Final add/add 3 = rare, only on exceptional conditions.

    This is not martingale recovery logic. The engine never adds to a losing or
    unprotected position, and it should never allow a pyramid basket to turn a
    protected winner back into account-damaging risk.
    """

    enabled: bool = True
    mode: str = "PROVE_CONFIRM_PRESS_EXCEPTIONAL"
    base_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 0.05
    max_adds: int = 3
    final_add_max_lot: bool = True   # True: final add jumps to max_lot ("max-lot pressure" leg).
                                     # False: every add climbs by lot_step, capped at max_lot (no jump).

    # Global gates.
    min_win_streak_for_aggressive: int = 1   # require 1 recent bot win (was 2 — never met live)
    min_broker_score: float = 60.0  # Reduced from 90 — broker scorer returns 0 until calibrated
    max_spread: float = 0.30
    max_slippage_points: float = 35.0
    max_total_lots: float = 0.11
    max_stack_risk_pct: float = 2.25
    max_total_exposure_pct: float = 3.00
    min_margin_level_pct: float = 300.0
    profit_buffer_safety_pct: float = 0.55
    final_add_profit_buffer_multiplier: float = 1.60
    second_add_profit_buffer_multiplier: float = 1.15

    # Stage thresholds. Lowered so STANDARD-quality continuation adds can actually fire;
    # adds still require the base trade in profit AND protected at break-even.
    min_confidence_first_add: float = 78.0   # second trade: reward confirmation (was 92)
    min_confidence_second_add: float = 85.0  # third trade: press clean trend (was 95)
    min_confidence_final_add: float = 92.0   # final add: exceptional only (was 98)
    min_profit_r_first_add: float = 0.80
    min_profit_r_second_add: float = 1.50
    min_profit_r_final_add: float = 2.60
    min_cleanliness_first_add: float = 86.0
    min_cleanliness_second_add: float = 90.0
    min_cleanliness_final_add: float = 94.0
    min_trend_alignment_first_add: float = 86.0
    min_trend_alignment_second_add: float = 91.0
    min_trend_alignment_final_add: float = 96.0
    min_liquidity_room_first_add: float = 65.0
    min_liquidity_room_second_add: float = 75.0
    min_liquidity_room_final_add: float = 88.0
    max_extension_atr_first_add: float = 1.10
    max_extension_atr_second_add: float = 0.90
    max_extension_atr_final_add: float = 0.65
    min_locked_profit_r_final_add: float = 1.20

    # Fast guard / basket defence.
    fast_guard_loss_r: float = 0.22
    fast_guard_no_progress_candles: int = 3
    add_break_even_trigger_r: float = 0.35
    basket_trail_after_r: float = 1.25
    daily_profit_giveback_pct: float = 35.0
    daily_loss_limit_pct: float = 3.0

    # Mandatory confirmation requirements.
    require_pullback_retest: bool = True
    require_break_even_plus_costs: bool = True
    require_news_clear: bool = True
    require_structure_valid: bool = True
    require_not_late: bool = True
    require_prior_adds_protected: bool = True
    require_final_exceptional_conditions: bool = True


@dataclass
class PyramidLegPlan:
    add_number: int
    role: str
    lot: float
    trigger: str
    min_profit_r: float
    min_confidence: float
    min_cleanliness: float
    min_trend_alignment: float
    min_liquidity_room: float
    max_extension_atr: float
    required_state: list[str] = field(default_factory=list)
    stop_rule: str = ""
    fast_guard: dict[str, Any] = field(default_factory=dict)
    cancel_if: list[str] = field(default_factory=list)


class AIPyramidingEngine:
    """AI-gated protected lot-scaling pyramid engine.

    The engine uses anti-martingale logic: add only after the trade has proved
    itself. The final/max-lot add is intentionally rare and needs exceptional
    agreement between profit, trend, structure, liquidity room, volatility and
    broker execution quality.
    """

    def __init__(self, settings: PyramidSettings | None = None):
        self.settings = settings or PyramidSettings()

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.settings_dict()
        aliases = {
            "baseLot": "base_lot",
            "lotStep": "lot_step",
            "maxLot": "max_lot",
            "maxAdds": "max_adds",
            "finalAddMaxLot": "final_add_max_lot",
            "maxSpread": "max_spread",
            "enabled": "enabled",
            "minWinStreakForAggressive": "min_win_streak_for_aggressive",
            "maxTotalLots": "max_total_lots",
            "maxStackRiskPct": "max_stack_risk_pct",
            "maxTotalExposurePct": "max_total_exposure_pct",
            "profitBufferSafetyPct": "profit_buffer_safety_pct",
            "finalAddProfitBufferMultiplier": "final_add_profit_buffer_multiplier",
            "secondAddProfitBufferMultiplier": "second_add_profit_buffer_multiplier",
            "fastGuardLossR": "fast_guard_loss_r",
            "fastGuardNoProgressCandles": "fast_guard_no_progress_candles",
            "dailyLossLimitPct": "daily_loss_limit_pct",
            "dailyProfitGivebackPct": "daily_profit_giveback_pct",
            "minConfidenceFirstAdd": "min_confidence_first_add",
            "minConfidenceSecondAdd": "min_confidence_second_add",
            "minConfidenceFinalAdd": "min_confidence_final_add",
            "minProfitRFirstAdd": "min_profit_r_first_add",
            "minProfitRSecondAdd": "min_profit_r_second_add",
            "minProfitRFinalAdd": "min_profit_r_final_add",
            "minCleanlinessFirstAdd": "min_cleanliness_first_add",
            "minCleanlinessSecondAdd": "min_cleanliness_second_add",
            "minCleanlinessFinalAdd": "min_cleanliness_final_add",
            "minTrendAlignmentFirstAdd": "min_trend_alignment_first_add",
            "minTrendAlignmentSecondAdd": "min_trend_alignment_second_add",
            "minTrendAlignmentFinalAdd": "min_trend_alignment_final_add",
            "minLiquidityRoomFirstAdd": "min_liquidity_room_first_add",
            "minLiquidityRoomSecondAdd": "min_liquidity_room_second_add",
            "minLiquidityRoomFinalAdd": "min_liquidity_room_final_add",
            "maxExtensionAtrFirstAdd": "max_extension_atr_first_add",
            "maxExtensionAtrSecondAdd": "max_extension_atr_second_add",
            "maxExtensionAtrFinalAdd": "max_extension_atr_final_add",
            "minLockedProfitRFinalAdd": "min_locked_profit_r_final_add",
            "requirePriorAddsProtected": "require_prior_adds_protected",
            "requireFinalExceptionalConditions": "require_final_exceptional_conditions",
        }
        for key, value in payload.items():
            normalized = aliases.get(key, key)
            if normalized in data:
                current = data[normalized]
                try:
                    if isinstance(current, bool):
                        if isinstance(value, bool):
                            clean = value
                        elif str(value).strip().lower() in {"true", "1", "yes", "on"}:
                            clean = True
                        elif str(value).strip().lower() in {"false", "0", "no", "off"}:
                            clean = False
                        else:
                            raise ValueError
                    elif isinstance(current, int) and not isinstance(current, bool):
                        clean = int(float(value))
                    elif isinstance(current, float):
                        clean = float(value)
                    else:
                        clean = str(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid pyramiding setting {key!r}: expected {type(current).__name__}.") from exc
                data[normalized] = clean

        float_bounds = {
            "base_lot": (0.01, 100.0),
            "lot_step": (0.01, 100.0),
            "max_lot": (0.01, 100.0),
            "max_spread": (0.01, 10.0),
            "max_slippage_points": (0.0, 1000.0),
            "max_total_lots": (0.01, 500.0),
            "max_stack_risk_pct": (0.0, 10.0),
            "max_total_exposure_pct": (0.0, 20.0),
            "min_margin_level_pct": (100.0, 10000.0),
            "profit_buffer_safety_pct": (0.0, 1.0),
            "final_add_profit_buffer_multiplier": (1.0, 5.0),
            "second_add_profit_buffer_multiplier": (1.0, 5.0),
            "daily_profit_giveback_pct": (0.0, 100.0),
            "daily_loss_limit_pct": (0.0, 20.0),
        }
        for name, (low, high) in float_bounds.items():
            data[name] = max(low, min(high, float(data[name])))
        for name in (
            "min_confidence_first_add",
            "min_confidence_second_add",
            "min_confidence_final_add",
            "min_cleanliness_first_add",
            "min_cleanliness_second_add",
            "min_cleanliness_final_add",
            "min_trend_alignment_first_add",
            "min_trend_alignment_second_add",
            "min_trend_alignment_final_add",
            "min_liquidity_room_first_add",
            "min_liquidity_room_second_add",
            "min_liquidity_room_final_add",
        ):
            data[name] = max(0.0, min(100.0, float(data[name])))
        for name in (
            "min_profit_r_first_add",
            "min_profit_r_second_add",
            "min_profit_r_final_add",
            "min_locked_profit_r_final_add",
            "max_extension_atr_first_add",
            "max_extension_atr_second_add",
            "max_extension_atr_final_add",
            "fast_guard_loss_r",
            "add_break_even_trigger_r",
            "basket_trail_after_r",
        ):
            data[name] = max(0.0, min(20.0, float(data[name])))
        data["max_adds"] = max(0, min(5, int(data["max_adds"])))
        data["min_win_streak_for_aggressive"] = max(0, min(20, int(data["min_win_streak_for_aggressive"])))
        data["fast_guard_no_progress_candles"] = max(1, min(100, int(data["fast_guard_no_progress_candles"])))
        data["max_lot"] = max(data["base_lot"], data["max_lot"])
        candidate = PyramidSettings(**data)
        # Auto-fit the basket lot cap to the ladder so raising maxLot / maxAdds / lotStep actually
        # lets the final add through — UNLESS the user set maxTotalLots explicitly in THIS update
        # (then we respect their number). The risk-% / exposure caps remain the real governors.
        explicit_total = any(k in payload for k in ("maxTotalLots", "max_total_lots"))
        if not explicit_total:
            prior = self.settings
            self.settings = candidate
            natural = self.natural_basket_lots()
            self.settings = prior
            if candidate.max_total_lots < natural:
                candidate.max_total_lots = natural
        self.settings = candidate
        return self.settings_dict(camel=True)

    def natural_basket_lots(self) -> float:
        """Sum of the full ladder (base + every add) at current settings — the lot count a
        complete, fully-pressed pyramid would reach. Used to keep maxTotalLots consistent."""
        s = self.settings
        total = s.base_lot
        for i in range(1, s.max_adds + 1):
            total += self._lot_for_add(i, s.base_lot)
        return round(total, 2)

    def settings_dict(self, camel: bool = False) -> dict[str, Any]:
        data = asdict(self.settings)
        if not camel:
            return data
        out = {self._camel(k): v for k, v in data.items()}
        out["naturalBasketLots"] = self.natural_basket_lots()  # read-only hint for the UI
        return out

    def evaluate(
        self,
        decision: dict[str, Any] | None = None,
        position: dict[str, Any] | None = None,
        market: dict[str, Any] | None = None,
        broker_quality: dict[str, Any] | None = None,
        kill_switch: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        s = self.settings
        decision = decision or {}
        market = market or {}
        if not position:
            return {
                "allowed": False,
                "stage": "NO_ACTIVE_BOT_TRADE",
                "mode": s.mode,
                "message": "No active GodMode bot trade is available to pyramid. The engine will not generate a fake/demo pyramid plan.",
                "blockedReasons": ["no_active_bot_trade"],
                "settings": self.settings_dict(camel=True),
            }
        broker_quality = broker_quality or {"score": 0, "grade": "Unknown"}
        kill_switch = kill_switch or {"active": False}

        current_adds = int(position.get("pyramidAdds", position.get("currentAdds", 0)) or 0)
        next_add_number = current_adds + 1
        stage = self._stage(next_add_number)
        confidence = float(decision.get("confidence", market.get("confidence", 0)) or 0)
        quality = str(decision.get("quality", "WAIT")).upper()
        action = str(decision.get("action", "WAIT")).upper()
        profit_r = float(position.get("profitR", position.get("floatingR", 0.0)) or 0)
        win_streak = int(position.get("winStreak", position.get("winsSinceLastLoss", 0)) or 0)
        base_lot = float(position.get("baseLot", s.base_lot) or s.base_lot)
        current_lots = float(position.get("currentLots", base_lot + current_adds * s.lot_step) or 0)
        total_exposure_pct = float(position.get("totalExposurePct", 99.0) or 0)
        raw_stack_risk_pct = float(position.get("currentStackRiskPct", position.get("openRiskPct", 99.0)) or 0)
        margin_level = float(position.get("marginLevelPct", position.get("marginLevel", 0)) or 0)
        locked_profit_r = float(position.get("lockedProfitR", 0.0) or 0)
        floating_profit_money = float(position.get("floatingProfitMoney", 0.0) or 0.0)
        prospective_risk_money = float(position.get("prospectiveAddRiskMoney", 0.0) or 0.0)
        be_moved = bool(position.get("beMoved", position.get("breakEvenProtected", False)))
        all_prior_adds_protected = bool(position.get("allPriorAddsProtected", position.get("previousAddsProtected", False)))
        previous_add_failed = bool(position.get("previousPyramidAddFailed", market.get("previousPyramidAddFailed", False)))

        structure_valid = bool(position.get("structureValid", market.get("structureValid", False)))
        retest_confirmed = bool(position.get("pullbackRetestConfirmed", market.get("pullbackRetestConfirmed", False)))
        momentum_confirmed = bool(position.get("momentumConfirmed", market.get("momentumConfirmed", False)))
        volatility_expansion_clean = bool(market.get("volatilityExpansionClean", position.get("volatilityExpansionClean", False)))
        momentum_divergence = bool(market.get("momentumDivergence", position.get("momentumDivergence", False)))
        late_entry = bool(position.get("lateEntry", market.get("lateEntry", False)))
        spread = float(market.get("spread", 999.0) or 999.0)
        slippage_points = float(market.get("slippagePoints", position.get("slippagePoints", 999.0)) or 0)
        cleanliness = float(market.get("cleanlinessScore", market.get("marketCleanliness", 0)) or 0)
        trend_alignment = float(market.get("trendAlignmentScore", market.get("htfAlignmentScore", position.get("trendAlignmentScore", 0))) or 0)
        liquidity_room = float(market.get("liquidityRoomScore", market.get("roomToTargetScore", position.get("liquidityRoomScore", 0))) or 0)
        extension_atr = float(market.get("extensionAtr", market.get("distanceFromMeanAtr", position.get("extensionAtr", 99.0))) or 0)
        news_blackout = bool(decision.get("economicCalendar", {}).get("isBlackout", market.get("newsBlackout", False)))
        dirty_conditions = bool(market.get("dirtyConditions", False))
        daily_loss_pct = float(position.get("dailyLossPct", market.get("dailyLossPct", 0)) or 0)
        daily_profit_giveback_pct = float(position.get("dailyProfitGivebackPct", market.get("dailyProfitGivebackPct", 0)) or 0)
        broker_score = float(broker_quality.get("score", 0) or 0)

        min_conf = self._confidence_threshold(next_add_number)
        min_profit_r = self._profit_r_threshold(next_add_number)
        min_cleanliness = self._cleanliness_threshold(next_add_number)
        min_trend_alignment = self._trend_alignment_threshold(next_add_number)
        min_liquidity_room = self._liquidity_room_threshold(next_add_number)
        max_extension_atr = self._max_extension_atr(next_add_number)
        next_lot = self._lot_for_add(next_add_number, base_lot)
        projected_total_lots = round(current_lots + next_lot, 2)
        add_risk_pct = self._estimate_add_risk_pct(position, next_lot, base_lot)
        current_stack_risk_pct = 0.0 if (be_moved and all_prior_adds_protected) else raw_stack_risk_pct
        projected_stack_risk_pct = round(current_stack_risk_pct + add_risk_pct, 3)
        projected_exposure_pct = round(total_exposure_pct + add_risk_pct, 3)
        profit_buffer_status = self._profit_buffer_check(
            add_number=next_add_number,
            locked_profit_r=locked_profit_r,
            profit_r=profit_r,
            add_risk_pct=add_risk_pct,
            floating_profit_money=floating_profit_money,
            prospective_risk_money=prospective_risk_money,
        )

        final_exceptional = self._final_exceptional_ok(
            confidence=confidence,
            quality=quality,
            profit_r=profit_r,
            locked_profit_r=locked_profit_r,
            cleanliness=cleanliness,
            trend_alignment=trend_alignment,
            liquidity_room=liquidity_room,
            extension_atr=extension_atr,
            volatility_expansion_clean=volatility_expansion_clean,
            momentum_divergence=momentum_divergence,
        )

        blocks: list[str] = []
        warnings: list[str] = []
        if not s.enabled:
            blocks.append("Pyramiding module disabled in settings")
        if kill_switch.get("active"):
            blocks.append("Emergency kill switch is active")
        if action != "TAKE_TRADE":
            blocks.append("Base AI decision is not TAKE_TRADE")
        if quality not in {"SNIPER", "HIGH", "STANDARD"}:
            blocks.append("Signal quality must be at least STANDARD to pyramid")
        if next_add_number >= 3 and quality != "SNIPER":
            blocks.append("Final add is rare and requires SNIPER quality")
        if confidence < min_conf:
            blocks.append(f"AI confidence {confidence:.1f}% below {stage['short']} threshold {min_conf:.1f}%")
        if current_adds >= s.max_adds:
            blocks.append("Maximum pyramid adds already reached")
        if win_streak < s.min_win_streak_for_aggressive:
            blocks.append(f"Aggressive lot scaling requires at least {s.min_win_streak_for_aggressive} recent bot wins")
        if profit_r < min_profit_r:
            blocks.append(f"Trade has not proved itself: {profit_r:.2f}R below {stage['short']} trigger {min_profit_r:.2f}R")
        if s.require_break_even_plus_costs and not be_moved:
            blocks.append("Base trade is not protected at break-even plus costs")
        if s.require_prior_adds_protected and current_adds >= 1 and not all_prior_adds_protected:
            blocks.append("All earlier pyramid legs must be protected before adding again")
        if previous_add_failed:
            blocks.append("A previous pyramid add failed this session; further adds are disabled until reset")
        if s.require_structure_valid and not structure_valid:
            blocks.append("Market structure is no longer valid")
        if s.require_pullback_retest and not retest_confirmed:
            blocks.append("No clean pullback/retest confirmation; do not chase price")
        if not momentum_confirmed:
            blocks.append("Momentum/follow-through confirmation is missing")
        if s.require_not_late and late_entry:
            blocks.append("Move is late/extended; pyramid add would be chasing")
        if extension_atr > max_extension_atr:
            blocks.append(f"Move is overextended: {extension_atr:.2f} ATR above {stage['short']} max {max_extension_atr:.2f} ATR")
        if s.require_news_clear and news_blackout:
            blocks.append("News blackout blocks pyramiding")
        if dirty_conditions:
            blocks.append("Dirty market conditions block pyramid adds")
        if cleanliness < min_cleanliness:
            blocks.append(f"Market cleanliness {cleanliness:.1f}% below {stage['short']} threshold {min_cleanliness:.1f}%")
        if trend_alignment < min_trend_alignment:
            blocks.append(f"HTF trend alignment {trend_alignment:.1f}% below {stage['short']} threshold {min_trend_alignment:.1f}%")
        if liquidity_room < min_liquidity_room:
            blocks.append(f"Remaining liquidity/target room {liquidity_room:.1f}% below {stage['short']} threshold {min_liquidity_room:.1f}%")
        if not volatility_expansion_clean:
            blocks.append("Volatility expansion is not clean; do not press the basket")
        if momentum_divergence:
            blocks.append("Momentum divergence detected; pyramid add blocked")
        if s.require_final_exceptional_conditions and next_add_number >= 3 and not final_exceptional:
            blocks.append("Final add blocked: conditions are not exceptional enough for max-lot pressure")
        if spread > s.max_spread:
            blocks.append(f"Spread {spread:.2f} above pyramiding max {s.max_spread:.2f}")
        if next_add_number >= 3 and spread > s.max_spread * 0.65:
            blocks.append(f"Final add requires premium spread: {spread:.2f} must be below {s.max_spread * 0.65:.2f}")
        if slippage_points > s.max_slippage_points:
            blocks.append(f"Slippage {slippage_points:.1f} points above pyramiding max {s.max_slippage_points:.1f}")
        if broker_score < s.min_broker_score:
            blocks.append(f"Broker execution score {broker_score:.1f} below {s.min_broker_score:.1f}")
        if margin_level < s.min_margin_level_pct:
            blocks.append(f"Margin level {margin_level:.1f}% below {s.min_margin_level_pct:.1f}%")
        if projected_total_lots > s.max_total_lots:
            blocks.append(f"Projected total lots {projected_total_lots:.2f} exceeds cap {s.max_total_lots:.2f}")
        if next_lot > s.max_lot:
            blocks.append(f"Next add lot {next_lot:.2f} exceeds max add lot {s.max_lot:.2f}")
        if projected_stack_risk_pct > s.max_stack_risk_pct:
            blocks.append(f"Projected stack risk {projected_stack_risk_pct:.2f}% exceeds cap {s.max_stack_risk_pct:.2f}%")
        if projected_exposure_pct > s.max_total_exposure_pct:
            blocks.append(f"Projected total exposure {projected_exposure_pct:.2f}% exceeds cap {s.max_total_exposure_pct:.2f}%")
        if not profit_buffer_status["ok"]:
            blocks.append(profit_buffer_status["message"])
        if daily_loss_pct >= s.daily_loss_limit_pct:
            blocks.append(f"Daily loss {daily_loss_pct:.2f}% has reached/exceeded limit {s.daily_loss_limit_pct:.2f}%")
        if daily_profit_giveback_pct >= s.daily_profit_giveback_pct:
            blocks.append(f"Daily profit giveback {daily_profit_giveback_pct:.1f}% exceeds allowed giveback {s.daily_profit_giveback_pct:.1f}%")

        if current_adds >= 1 and confidence < self._confidence_threshold(current_adds):
            warnings.append("Confidence has softened versus the previous add level; reduce faster if momentum stalls")
        if spread > s.max_spread * 0.75:
            warnings.append("Spread is near the pyramid ceiling; use stricter fill/deviation control")
        if profit_r > min_profit_r + 0.75 and not retest_confirmed:
            warnings.append("Price may be extended; wait for a retest before adding")
        if next_add_number >= 3:
            warnings.append("Final add is intentionally rare; skip unless all exceptional gates remain true")

        allowed = len(blocks) == 0
        next_add = asdict(self._add_plan(next_add_number, next_lot, min_conf, min_profit_r)) if allowed else None
        score = self._pyramid_score(confidence, profit_r, cleanliness, trend_alignment, liquidity_room, broker_score, current_adds, blocks)

        return {
            "enabled": s.enabled,
            "allowed": allowed,
            "mode": s.mode,
            "status": "ARMED_TO_ADD" if allowed else "WAITING_FOR_PROTECTION",
            "currentAdds": current_adds,
            "maxAdds": s.max_adds,
            "currentStage": stage,
            "baseLot": round(base_lot, 2),
            "nextLot": round(next_lot, 2),
            "maxLot": round(s.max_lot, 2),
            "projectedTotalLots": projected_total_lots,
            "score": score,
            "blocks": blocks,
            "warnings": warnings,
            "signals": {
                "confidence": round(confidence, 1),
                "quality": quality,
                "profitR": round(profit_r, 2),
                "lockedProfitR": round(locked_profit_r, 2),
                "cleanlinessScore": round(cleanliness, 1),
                "trendAlignmentScore": round(trend_alignment, 1),
                "liquidityRoomScore": round(liquidity_room, 1),
                "extensionAtr": round(extension_atr, 2),
                "volatilityExpansionClean": volatility_expansion_clean,
                "momentumDivergence": momentum_divergence,
                "finalExceptional": final_exceptional,
            },
            "riskGovernor": {
                "currentNetStackRiskPct": round(current_stack_risk_pct, 3),
                "rawStackRiskPct": round(raw_stack_risk_pct, 3),
                "projectedStackRiskPct": projected_stack_risk_pct,
                "projectedTotalExposurePct": projected_exposure_pct,
                "maxStackRiskPct": s.max_stack_risk_pct,
                "maxTotalExposurePct": s.max_total_exposure_pct,
                "maxTotalLots": s.max_total_lots,
                "marginLevelPct": margin_level,
                "minMarginLevelPct": s.min_margin_level_pct,
                "profitBuffer": profit_buffer_status,
            },
            "fastGuard": self._fast_guard(),
            "philosophy": [
                "First trade = prove direction",
                "Second trade/Add 1 = reward confirmation only after protection",
                "Third trade/Add 2 = press only if the trend remains clean",
                "Final add/Add 3 = rare, max-lot pressure only on exceptional conditions",
            ],
            "rules": {
                "antiMartingaleOnly": True,
                "neverAddToLoser": True,
                "lotScaling": "0.01 base -> 0.02 reward confirmation -> 0.03 press clean trend -> rare max-lot final add",
                "requiresTwoRecentWins": s.min_win_streak_for_aggressive,
                "requiresBreakEvenPlusCosts": s.require_break_even_plus_costs,
                "requiresAllPriorAddsProtected": s.require_prior_adds_protected,
                "requiresPullbackRetest": s.require_pullback_retest,
                "requiresNoNewsBlackout": s.require_news_clear,
                "requiresCleanStructure": s.require_structure_valid,
                "requiresNotLateOrExtended": s.require_not_late,
                "finalAddRequiresExceptionalConditions": s.require_final_exceptional_conditions,
                "requiresSpreadBelow": s.max_spread,
                "requiresBrokerScoreAbove": s.min_broker_score,
            },
            "nextAdd": next_add,
            "lotSchedule": [asdict(self._add_plan(i, self._lot_for_add(i, base_lot), self._confidence_threshold(i), self._profit_r_threshold(i))) for i in range(1, s.max_adds + 1)],
            "managementIntegration": {
                "beforeAdd": "Move the existing basket to break-even plus costs and confirm a clean pullback/retest.",
                "afterAdd": f"Move the new add to break-even at +{s.add_break_even_trigger_r:.2f}R, or close quickly if it reaches -{s.fast_guard_loss_r:.2f}R.",
                "trail": "Trail the basket behind M5/M15 structure once basket is above the configured trail trigger.",
                "deRisk": "Close newest/largest add first if confidence drops, structure breaks, spread spikes, or time-stop fails.",
                "tpPush": "Only push TP3/TP4 while HTF liquidity remains open and volatility expands cleanly.",
            },
            "summary": "Pyramiding now follows prove-confirm-press-exceptional logic. It rewards confirmed winners, presses only clean trends, and reserves the final max-lot add for rare exceptional conditions.",
        }

    def _add_plan(self, add_number: int, lot: float, min_confidence: float, min_profit_r: float) -> PyramidLegPlan:
        stage = self._stage(add_number)
        triggers = {
            1: "Second trade: after +0.85R, base SL at BE+costs, clean M5/M15 pullback retest confirms direction.",
            2: "Third trade: after +1.60R, Add 1 protected, continuation break/retest, trend still clean and not extended.",
            3: "Final rare add: after +2.80R, all earlier legs protected, SNIPER-only, HTF liquidity still open, exceptional cleanliness.",
        }
        return PyramidLegPlan(
            add_number=add_number,
            role=stage["role"],
            lot=round(lot, 2),
            trigger=triggers.get(add_number, "Exceptional continuation only."),
            min_profit_r=min_profit_r,
            min_confidence=min_confidence,
            min_cleanliness=self._cleanliness_threshold(add_number),
            min_trend_alignment=self._trend_alignment_threshold(add_number),
            min_liquidity_room=self._liquidity_room_threshold(add_number),
            max_extension_atr=self._max_extension_atr(add_number),
            required_state=self._required_state(add_number),
            stop_rule="New add SL behind latest valid M5/M15 structure; newest/largest add is cut first on invalidation.",
            fast_guard=self._fast_guard(),
            cancel_if=[
                "structure invalidation",
                "AI confidence drops below previous threshold",
                "spread or slippage spike",
                "high-impact news blackout",
                "momentum divergence",
                "move becomes late/overextended",
                "no progress within time-stop candles",
                "daily profit giveback exceeded",
                "margin level below safe floor",
            ],
        )

    def _required_state(self, add_number: int) -> list[str]:
        common = [
            "Base trade protected at BE+costs",
            "At least two recent GodMode bot wins",
            "AI decision remains TAKE_TRADE",
            "Pullback/retest confirmed; no chasing",
            "No news blackout and no spread/slippage spike",
            "Projected basket risk stays under cap",
        ]
        if add_number <= 1:
            return ["First trade has proved direction"] + common
        if add_number == 2:
            return ["Add 1 protected or strongly funded", "Trend remains clean across M5/M15/H1"] + common
        return ["SNIPER quality only", "All earlier legs protected", "HTF liquidity still open", "Final add exceptional gate passed", "Locked profit can fund max-lot risk"] + common

    def _stage(self, add_number: int) -> dict[str, str]:
        if add_number <= 1:
            return {"short": "Add 1", "role": "Second trade = reward confirmation", "strictness": "high"}
        if add_number == 2:
            return {"short": "Add 2", "role": "Third trade = press only if trend remains clean", "strictness": "very_high"}
        return {"short": "Final add", "role": "Rare final add = exceptional conditions only", "strictness": "exceptional"}

    def _lot_for_add(self, add_number: int, base_lot: float) -> float:
        s = self.settings
        if add_number <= 0:
            return round(base_lot, 2)
        # The final add is a deliberate "max-lot pressure" leg ONLY when final_add_max_lot is on;
        # otherwise every add (including the final one) climbs by lot_step, capped at max_lot — so
        # raising max_lot scales the whole ladder smoothly instead of one surprise jump.
        if add_number >= s.max_adds and s.final_add_max_lot:
            return round(s.max_lot, 2)
        return round(min(s.max_lot, base_lot + s.lot_step * add_number), 2)

    def _confidence_threshold(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.min_confidence_first_add
        if add_number == 2:
            return s.min_confidence_second_add
        return s.min_confidence_final_add

    def _profit_r_threshold(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.min_profit_r_first_add
        if add_number == 2:
            return s.min_profit_r_second_add
        return s.min_profit_r_final_add

    def _cleanliness_threshold(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.min_cleanliness_first_add
        if add_number == 2:
            return s.min_cleanliness_second_add
        return s.min_cleanliness_final_add

    def _trend_alignment_threshold(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.min_trend_alignment_first_add
        if add_number == 2:
            return s.min_trend_alignment_second_add
        return s.min_trend_alignment_final_add

    def _liquidity_room_threshold(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.min_liquidity_room_first_add
        if add_number == 2:
            return s.min_liquidity_room_second_add
        return s.min_liquidity_room_final_add

    def _max_extension_atr(self, add_number: int) -> float:
        s = self.settings
        if add_number <= 1:
            return s.max_extension_atr_first_add
        if add_number == 2:
            return s.max_extension_atr_second_add
        return s.max_extension_atr_final_add

    def _estimate_add_risk_pct(self, position: dict[str, Any], next_lot: float, base_lot: float) -> float:
        # Risk scales with BOTH the add's lot size AND its own stop distance. A pyramid add placed
        # behind nearby structure (tighter stop than the base trade) risks proportionally less; a
        # wider add stop risks more. When stop distances are supplied we model that explicitly;
        # otherwise we fall back to the lot-ratio-only approximation.
        base_risk_pct = float(position.get("baseRiskPct", position.get("riskPct", 0.35)) or 0.35)
        lot_ratio = next_lot / max(base_lot, 0.01)
        base_sl = float(position.get("baseStopDistance", 0) or 0)
        add_sl = float(position.get("addStopDistance", 0) or 0)
        if base_sl > 0 and add_sl > 0:
            return round(base_risk_pct * lot_ratio * (add_sl / base_sl), 3)
        return round(base_risk_pct * lot_ratio, 3)

    def _profit_buffer_check(
        self,
        add_number: int,
        locked_profit_r: float,
        profit_r: float,
        add_risk_pct: float,
        floating_profit_money: float,
        prospective_risk_money: float,
    ) -> dict[str, Any]:
        s = self.settings
        multiplier = 1.0
        if add_number == 2:
            multiplier = s.second_add_profit_buffer_multiplier
        elif add_number >= 3:
            multiplier = s.final_add_profit_buffer_multiplier
        required_buffer_r = add_risk_pct * s.profit_buffer_safety_pct * multiplier
        available_r_buffer = max(0.0, locked_profit_r) + max(0.0, profit_r - 1.0) * 0.35
        money_ok = True
        if floating_profit_money > 0 and prospective_risk_money > 0:
            money_ok = (prospective_risk_money <= floating_profit_money * s.profit_buffer_safety_pct / max(multiplier, 1.0))
        ok = available_r_buffer >= required_buffer_r and money_ok
        if add_number >= 3 and locked_profit_r < s.min_locked_profit_r_final_add:
            ok = False
        message = "Profit buffer can fund the add without exposing the basket beyond cap" if ok else (
            f"Profit buffer too small for {self._stage(add_number)['short']}: available {available_r_buffer:.2f}R, required {required_buffer_r:.2f}R; wait for more locked profit"
        )
        return {
            "ok": ok,
            "availableBufferR": round(available_r_buffer, 3),
            "requiredBufferR": round(required_buffer_r, 3),
            "lockedProfitR": round(locked_profit_r, 3),
            "minLockedProfitRFinalAdd": s.min_locked_profit_r_final_add,
            "floatingProfitMoney": round(floating_profit_money, 2),
            "prospectiveAddRiskMoney": round(prospective_risk_money, 2),
            "safetyPct": s.profit_buffer_safety_pct,
            "stageMultiplier": multiplier,
            "message": message,
        }

    def _final_exceptional_ok(
        self,
        confidence: float,
        quality: str,
        profit_r: float,
        locked_profit_r: float,
        cleanliness: float,
        trend_alignment: float,
        liquidity_room: float,
        extension_atr: float,
        volatility_expansion_clean: bool,
        momentum_divergence: bool,
    ) -> bool:
        s = self.settings
        return (
            quality == "SNIPER"
            and confidence >= s.min_confidence_final_add
            and profit_r >= s.min_profit_r_final_add
            and locked_profit_r >= s.min_locked_profit_r_final_add
            and cleanliness >= s.min_cleanliness_final_add
            and trend_alignment >= s.min_trend_alignment_final_add
            and liquidity_room >= s.min_liquidity_room_final_add
            and extension_atr <= s.max_extension_atr_final_add
            and volatility_expansion_clean
            and not momentum_divergence
        )

    def _fast_guard(self) -> dict[str, Any]:
        s = self.settings
        return {
            "cutNewestAddAtNegativeR": -abs(s.fast_guard_loss_r),
            "moveAddToBreakEvenAtR": s.add_break_even_trigger_r,
            "timeStopCandles": s.fast_guard_no_progress_candles,
            "exitOrder": "newest_and_largest_add_first",
            "basketTrailAfterR": s.basket_trail_after_r,
            "hardRules": [
                "Close newest add immediately if structure breaks",
                "Close newest add if no progress within time-stop candles",
                "Close all adds if base trade returns below BE+costs",
                "Disable new adds after any failed pyramid add this session",
                "Disable new adds after daily loss limit or profit giveback breach",
                "Disable new adds if broker execution score deteriorates",
            ],
        }

    def _pyramid_score(self, confidence: float, profit_r: float, cleanliness: float, trend_alignment: float, liquidity_room: float, broker_score: float, current_adds: int, blocks: list[str]) -> float:
        penalty = min(45, len(blocks) * 5) if blocks else 0
        raw = (
            confidence * 0.35
            + min(100.0, profit_r * 26) * 0.18
            + cleanliness * 0.16
            + trend_alignment * 0.13
            + liquidity_room * 0.08
            + broker_score * 0.10
            - current_adds * 3.5
            - penalty
        )
        return round(max(0.0, min(100.0, raw)), 1)

    def demo_position(self) -> dict[str, Any]:
        return {
            "symbol": "XAUUSD",
            "side": "BUY",
            "profitR": 1.18,
            "lockedProfitR": 0.25,
            "baseRiskPct": 0.35,
            "beMoved": True,
            "pyramidAdds": 0,
            "baseLot": self.settings.base_lot,
            "currentLots": self.settings.base_lot,
            "totalExposurePct": 1.1,
            "currentStackRiskPct": 0.35,
            "marginLevelPct": 720,
            "structureValid": True,
            "pullbackRetestConfirmed": True,
            "momentumConfirmed": True,
            "allPriorAddsProtected": True,
            "winsSinceLastLoss": 2,
        }

    @staticmethod
    def _camel(name: str) -> str:
        parts = name.split("_")
        return parts[0] + "".join(p.title() for p in parts[1:])
