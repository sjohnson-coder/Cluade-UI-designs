# GodMode Gold Bot V15.2.0 Hybrid Hardened

This release combines the V15.1.1 impulse-capture path with V15.1.3 journal-driven calibration improvements.

## Corrections

- Removed the misleading post-close "AI audit gate". Audit enforcement now exists only before order execution.
- Added latency protection for critical impulse entries. Qualified SHOCK and cascade-retest entries bypass synchronous LLM auditing by default.
- Reduced the AI auditor timeout from 20 seconds to 8 seconds for non-critical entries.
- Added explicit AI auditor configuration for downgrade blocking and critical-impulse bypass.
- Added configurable FSMMS body gating with OFF, SHADOW and ENFORCE modes.
- Body threshold adapts modestly to compression and expansion conditions.
- Ships in SHADOW mode so weak-print evidence is collected without suppressing valid early entries.
- Preserved persistent V15 decision attribution, calibration progress and unattributed-outcome diagnostics.
- Normalised release identity to V15.2.0-EARLY-IMPULSE-PREDICTOR.

## Recommended live settings

- Keep the AI auditor disabled until API credentials, latency and rate limits are validated.
- Keep FSMMS body gating in SHADOW mode until a statistically meaningful journal sample is available.
- Use ENFORCE only after comparing expectancy, missed entries and entry delay across sessions.
