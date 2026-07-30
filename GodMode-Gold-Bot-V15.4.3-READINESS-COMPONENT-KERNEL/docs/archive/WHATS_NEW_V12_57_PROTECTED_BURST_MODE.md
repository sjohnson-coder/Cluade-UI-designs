# V12.57 — Protected Burst Mode

This build adds a safe, auditable alternative to the proposed 50-position martingale.

## What changed

- Added Protected Burst Mode with a Settings toggle.
- When Protected Burst is enabled, pyramiding is automatically switched off so audit results are clean.
- Burst does not open all positions immediately. It opens the base trade normally, waits for AI Dynamic SL to protect the basket beyond true BE + spread/slippage buffer, then adds a small batch.
- Max positions is configurable up to 50, but batch size is capped to avoid lag and order flooding.
- Demo-only safety lock is ON by default.
- Telegram can switch modes with buttons and commands: /burst_on, /burst_off, /pyramid_on, /pyramid_off, /modes.
- Telegram can approve one burst batch when manual confirmation is enabled.
- Burst uses confidence, recovery score, spread, protected-floor, total-lot and cooldown gates.
- It does not claim zero-loss; it prevents the dangerous version of instant 50-position exposure.

## Recommended validation

Keep Demo-only ON until at least 50 burst opportunities are reviewed in the AI Performance Coach. Start with max 5–10 positions, batch size 1, and 0.01 per-position lot.
