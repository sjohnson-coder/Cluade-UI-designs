# V12.53 — Dynamic SL Audit + Dashboard Cache

## Confirmed / strengthened
- Unified AI Dynamic SL remains the primary winner protection controller. It ratchets a profit floor from peak profit, tightens when recovery probability is weak, and can breathe/widen only back to a protected in-profit floor when recovery probability is high.
- Staged anti-martingale pyramiding remains one-add-at-a-time: every current leg must be protected before the next add is considered.
- Pyramiding protection detection now uses broker truth. If the backend restarts but MT5 already has an in-profit SL, that leg is still treated as protected.

## Lag fix
- Dashboard now uses a short backend cache and no longer rebuilds full analytics twice on every mount.
- Frontend Dashboard reads cached dashboard/strategy/feed data from localStorage instantly when you return from another page.
- Dashboard refreshes live data every 2.5s, feeds every 30s, strategies every 60s.

## Notes
- No UI style redesign was made. Only data-loading behaviour and protection-state robustness changed.
- Dynamic SL and pyramiding still require backend + MT5 to remain running for active management. Broker SL/TP remain as backstops.
