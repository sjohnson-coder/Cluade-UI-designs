# GodMode Gold Bot V15.1.2

## Impulse Capture + Calibration Integrity

This build combines the forming-candle pump/dump capture and SHOCK-regime impulse controls from V15.1.1 Impulse Capture with the calibration-attribution protections from V15.1.1 Calibration Integrity.

### Included
- 0.5-second forming-M5 impulse scanning.
- Qualified SHOCK pump/dump entries with displacement and anti-chase limits.
- Cascade proposal action-matrix rebuild.
- NaN/infinity-safe numerical clamping.
- Correct uncertainty direction around 50/50 ambiguity.
- Calibration maturity based only on `tp_before_sl` trade outcomes.
- Rejection of unattributable outcomes instead of assigning them to the latest report.
- Persistent decision attribution across backend restarts.
- Persistent unattributed-outcome diagnostics.
- Calibration progress, Brier score and baseline telemetry.
- Consistent V15.1.2 release identity.

### Verification
- Python compilation passed.
- 337 backend tests passed.
- Default `pytest -q` works without environment overrides.

Live trading still requires Windows MT5 compilation and broker demo-account soak testing before production use.
