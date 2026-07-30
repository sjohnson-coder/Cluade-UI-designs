# GodMode Pyramid Upgrade — Prove / Confirm / Press / Exceptional

## Philosophy implemented

The pyramid logic now follows the recommended model:

1. **First trade = prove direction**  
   The base 0.01 trade must prove the market direction. No add is allowed while the base trade is losing or unprotected.

2. **Second trade = reward confirmation**  
   Add 1 uses 0.02 only after the base trade is protected at BE+costs, profit has reached the required R threshold, and a clean pullback/retest confirms continuation.

3. **Third trade = press only if trend remains clean**  
   Add 2 uses 0.03 only if Add 1 is protected or strongly funded, trend alignment remains clean across higher timeframes, there is still target/liquidity room, and the move is not extended.

4. **Final add = rare exceptional condition only**  
   The final max-lot add is only allowed on SNIPER quality, very high confidence, strong locked profit, exceptional HTF trend alignment, enough liquidity/target room, low extension, clean volatility expansion, no divergence, low spread, no news blackout, and no failed pyramid add earlier in the session.

## Backend changes

Updated:

- `backend/services/pyramiding.py`
- `backend/services/live_execution.py`

Added/strengthened:

- `mode = PROVE_CONFIRM_PRESS_EXCEPTIONAL`
- Stage roles returned by `/api/pyramiding/plan`
- Stage-specific confidence thresholds
- Stage-specific profit-R thresholds
- Stage-specific market cleanliness thresholds
- Stage-specific HTF alignment thresholds
- Stage-specific liquidity-room thresholds
- Stage-specific maximum extension ATR thresholds
- Final-add exceptional gate
- Prior-add protection gate
- Previous failed pyramid add lockout
- Net stack risk logic so protected previous legs do not incorrectly block later adds
- Final-add locked-profit requirement
- Stronger exposure validator checks for third/final adds

## Default lot model

- Base trade: `0.01`
- Add 1: `0.02`
- Add 2: `0.03`
- Final add: capped `maxLot`, default `0.05`

## Key safety rules

- Never add to a losing trade
- Never add before BE+costs protection
- Never add if prior pyramid leg is not protected
- Never add during dirty/news conditions
- Never chase an extended move
- Never add if there is not enough liquidity/target room left
- Cut newest/largest add first on invalidation
- Stop adding after any failed pyramid attempt in the session
- Keep live trading dry-run unless `GODMODE_ENABLE_LIVE_TRADING=true`

## Validation completed

- Backend Python compile: passed
- Backend route smoke test: passed
- Pyramid Add 1 allowed under valid confirmation conditions: passed
- Pyramid Add 2 allowed under clean-trend conditions: passed
- Final add allowed under exceptional SNIPER conditions: passed
- Final add blocked when only HIGH quality, not SNIPER: passed
- Frontend TypeScript/Vite production build: passed
- NPM high-severity audit: 0 vulnerabilities
