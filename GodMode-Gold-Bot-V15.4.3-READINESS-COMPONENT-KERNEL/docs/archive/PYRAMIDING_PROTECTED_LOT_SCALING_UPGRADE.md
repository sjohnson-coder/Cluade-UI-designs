# GodMode Pyramiding Upgrade: Protected Aggressive Lot Scaling

This upgrade converts the pyramiding model into a protected anti-martingale system.
It can scale from a 0.01 base position into 0.02, 0.03 and a capped max-lot add, but only after the trade has already proved itself.

## Core Logic

- The first trade opens at the configured base lot, for example 0.01.
- Pyramid Add 1 can open at 0.02 only after TP1 / +0.85R, break-even plus costs, clean pullback/retest, and sniper-grade confirmation.
- Pyramid Add 2 can open at 0.03 only after TP2 / +1.60R, continuation break/retest, expanding momentum, and stronger confidence.
- The final/max add can open only after TP3 / +2.40R, open higher-timeframe liquidity, and enough profit buffer to fund the extra exposure.

## Protection Rules Added

1. No adding to losing trades.
2. No add unless the original trade is protected at break-even plus costs.
3. Minimum two recent bot wins before aggressive scaling is allowed.
4. Pullback/retest required before every add so the bot does not chase late candles.
5. Profit-buffer funding check before each add.
6. Stack risk cap, total exposure cap, total lot cap and margin-level floor.
7. News blackout, spread, slippage, broker-quality and structure-validity gates.
8. Fast guard cuts the newest and largest add first.
9. New adds move to break-even at +0.35R.
10. Newest add is cut quickly at -0.22R or after 3 candles with no progress.
11. Daily loss and daily profit-giveback protection disable further adds.

## Updated Backend Files

- `backend/services/pyramiding.py`
- `backend/services/live_execution.py`
- `backend/services/mock_data.py`
- `backend/app.py`

## Updated API Endpoints

- `GET /api/pyramiding/settings`
- `POST /api/pyramiding/settings`
- `GET /api/pyramiding/plan`
- `POST /api/pyramiding/plan`
- `POST /api/pyramiding/execute`
- `POST /api/exposure/validate-pyramid`
- `POST /api/trades/pyramid-execute-real`

## Important Trading Note

This does not guarantee wins. It is designed to make aggressive compounding safer by allowing larger adds only when the basket is already protected and conditions remain unusually strong. Forward testing on demo should be completed before enabling live trading.
