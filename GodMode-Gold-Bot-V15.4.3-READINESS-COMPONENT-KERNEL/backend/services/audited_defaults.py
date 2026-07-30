"""Audited trade-management defaults for V14.1.6.

This module is the single source of truth for safety-critical fallback values used
by both the settings factory and runtime trade-management path. It intentionally
does not migrate existing user values by numeric matching; user configuration is
preserved unless a schema-aware migration explicitly owns the field.
"""
from __future__ import annotations

BREAK_EVEN_AT_RR: float = 0.9
BREAK_EVEN_AT_POINTS: float = 3.0
PROTECT_START_POINTS: float = 3.0
BREAK_EVEN_BUFFER_POINTS: float = 0.8
TRAIL_START_RR: float = 1.0
TRAIL_ATR_MULT: float = 0.65
PROTECT_START_ATR: float = 0.55
TRAIL_START_ATR: float = 0.55
# ⚠ PHANTOM KNOB — READ BEFORE CHANGING (this value has been "fixed" 6 times)
# profitLockFraction is assigned into lock_frac in _auto_manage_open_trades and then
# UNCONDITIONALLY OVERWRITTEN a few lines later whenever aiDynamicStopEnabled is True
# (the default, in both code and packaged settings.json):
#     if ai_dynamic_stop and peak_cleared_noise:
#         lock_frac = max(AI_DYNAMIC_MIN_LOCK_FRACTION, 1 - AI_DYNAMIC_MAX_GIVEBACK_FRACTION)
#     elif ai_dynamic_stop:
#         lock_frac = 0.0
# So this constant ONLY governs the legacy path where aiDynamicStopEnabled is False.
# The EFFECTIVE retained-peak fraction in normal operation is:
#     max(AI_DYNAMIC_MIN_LOCK_FRACTION, 1 - AI_DYNAMIC_MAX_GIVEBACK_FRACTION) = 0.55
# Changing THIS number does not change live behaviour. Change the two constants above
# instead. 0.62 is retained here as the audited pre-V13.49 value for the legacy path.
PROFIT_LOCK_FRACTION: float = 0.62
PROFIT_LOCK_MIN_PEAK_ATR: float = 0.55
AI_DYNAMIC_MIN_LOCK_FRACTION: float = 0.30
AI_DYNAMIC_MAX_GIVEBACK_FRACTION: float = 0.45
AI_DYNAMIC_TIGHT_TRAIL_ATR: float = 0.45
AI_DYNAMIC_RECOVERY_SCORE_TO_BREATHE: float = 70.0
AI_DYNAMIC_LOW_SCORE_TIGHTEN: float = 42.0
AI_DYNAMIC_MINIMUM_LOCKED_R: float = 0.05
AI_DYNAMIC_MAX_BREATHS: int = 2
AI_DYNAMIC_BREATH_EXPIRY_SECONDS: int = 330
AI_DYNAMIC_FAST_FAIL_WINNER_GIVEBACK_R: float = 0.75
CONDITIONAL_TIME_STOP_ENABLED: bool = True
TIME_STOP_CUT_MINUTES: float = 4.0
TIME_STOP_WORKING_R: float = 0.30
TIME_STOP_PROFIT_REPRIEVE_R: float = 0.15
TIME_STOP_RECOVERY_SCORE_HOLD: float = 62.0
TIME_STOP_MAX_REPRIEVE_MINUTES: float = 8.0
FAST_FAIL_ENABLED: bool = True
FAST_FAIL_LOSS_R: float = -0.5
FAST_FAIL_MIN_SECONDS: int = 300
FAST_FAIL_NO_PROGRESS_MINUTES: float = 5.0
FAST_FAIL_NO_PROGRESS_CANDLES: int = 12
SMART_RECOVERY_ROOM: bool = True
RECOVERY_ROOM_ATR: float = 0.55
COUNTER_TREND_PROTECT_START_ATR: float = 0.35
COUNTER_TREND_FAST_FAIL_R: float = -0.35
COUNTER_TREND_TIME_STOP_MINUTES: float = 3.0

def assert_coherent() -> None:
    problems: list[str] = []
    if not 0.0 < PROFIT_LOCK_FRACTION <= 1.0: problems.append('profit lock fraction out of range')
    if not 0.0 <= AI_DYNAMIC_MAX_GIVEBACK_FRACTION < 1.0: problems.append('giveback fraction out of range')
    if COUNTER_TREND_PROTECT_START_ATR >= PROTECT_START_ATR: problems.append('counter-trend protection must be tighter')
    if COUNTER_TREND_FAST_FAIL_R <= FAST_FAIL_LOSS_R: problems.append('counter-trend fast-fail must be tighter')
    if COUNTER_TREND_TIME_STOP_MINUTES >= TIME_STOP_CUT_MINUTES: problems.append('counter-trend time-stop must be tighter')
    if TRAIL_START_ATR < PROTECT_START_ATR: problems.append('trail cannot start before protection')
    if PROFIT_LOCK_MIN_PEAK_ATR < PROTECT_START_ATR: problems.append('profit-lock floor below protect start')
    if TIME_STOP_PROFIT_REPRIEVE_R >= TIME_STOP_WORKING_R: problems.append('reprieve threshold must be below working threshold')
    if (1.0 - AI_DYNAMIC_MAX_GIVEBACK_FRACTION) < AI_DYNAMIC_MIN_LOCK_FRACTION: problems.append('giveback keep below minimum lock')
    if FAST_FAIL_MIN_SECONDS < 180: problems.append('fast-fail minimum is noise-level')
    if problems: raise AssertionError('audited defaults contradictions: ' + '; '.join(problems))

assert_coherent()


def effective_retained_peak_fraction(ai_dynamic_stop_enabled: bool = True) -> float:
    """The retained-peak fraction that ACTUALLY governs a live trade.

    Exists because PROFIT_LOCK_FRACTION is a phantom knob (see its comment): six
    separate releases "fixed" it without changing behaviour. Call this instead of
    reading PROFIT_LOCK_FRACTION when you want to know what the bot will really do.
    """
    if ai_dynamic_stop_enabled:
        return max(AI_DYNAMIC_MIN_LOCK_FRACTION, 1.0 - AI_DYNAMIC_MAX_GIVEBACK_FRACTION)
    return PROFIT_LOCK_FRACTION
