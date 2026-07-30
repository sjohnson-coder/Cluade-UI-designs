# AI Entry Strictness + Auto-Trade Heartbeat Upgrade

This patch implements the requested trading behaviour:

- Loosen first-entry rules slightly.
- Keep pyramiding very strict.
- Add clear blocked-reason logging.
- Add auto-trade heartbeat feedback.
- Allow small scout trades only at base lot.
- Never pyramid unless the first trade proves itself.
- Add Settings controls to manage strict mode.

## New Settings section

Settings now includes **AI Strictness & First Entry** with:

- Strict Mode: Relaxed Scout, Balanced, Strict, Sniper Only
- Allow Scout Entries
- Scout Confidence %
- Standard Confidence %
- Sniper Confidence %
- Minimum Risk:Reward
- Maximum Spread
- Show Block Reasons

## Default behaviour

Default is **Balanced**:

- Scout entry threshold: 72%
- Standard entry threshold: 78%
- Sniper threshold: 90%
- Minimum R:R: 1.5
- Maximum spread: 0.40

Scout entries are base-lot only and cannot trigger pyramiding. Pyramiding still requires the first trade to be protected and proven.

## New/updated endpoints

- `GET /api/ai/strictness`
- `POST /api/ai/strictness`
- `GET /api/auto-trading/heartbeat`
- `GET /api/auto-trading/status` now includes heartbeat and strictness
- `POST /api/auto-trading/tick` now returns clear WAIT/BLOCKED reasons

## Validation

- Backend Python compile: PASS
- Frontend Vite/TypeScript build: PASS
- FastAPI smoke tests: PASS
