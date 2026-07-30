# GodMode Gold Bot V12.46 — Multi-Timeframe Sniper Bias Matrix

This build upgrades the V12.45 low-latency sniper lane so it can stay fast while respecting the bigger market structure.

## Added

### 1. MTF Sniper Bias Matrix
The fast lane now keeps the clean-entry model:

- M5 = executable trigger
- M15 = setup/context
- M30 = transition filter
- H1 = session route
- H4 = institutional swing bias
- D1 = macro direction / major danger filter
- tick = final spread/bid/ask only

The bot does **not** require every timeframe to align. Instead, it scores the higher timeframes with a cached weighted matrix so entries are not delayed by repeatedly fetching H4/D1 candles.

### 2. Higher timeframe hard veto
If H4 and D1 are both strongly against the fast-lane direction, the sniper lane blocks the trade instead of taking a noisy M5 countertrend spike.

### 3. Scout mode for mixed context
If the M5 trigger is clean but the higher timeframe picture is mixed, the bot can downgrade the setup to SCOUT instead of forcing a full trade or rejecting everything.

### 4. M30 support added to MT5 bridge
The MT5 candle fetcher now supports M30 directly.

### 5. Settings controls
Settings → 5e. Automation & AI Recovery Monitor → Fast Sniper Lane now includes:

- MTF Bias Matrix ON/OFF
- MTF full score floor
- MTF scout floor
- H4/D1 hard veto ON/OFF
- MTF cache seconds
- M30 option for context timeframe

## Recommended settings

- Fast Sniper Lane: ON
- Trigger timeframe: M5
- Context timeframe: M15
- MTF Bias Matrix: ON
- MTF full score floor: 0.18
- MTF scout floor: -0.12
- H4/D1 hard veto: ON
- MTF cache seconds: 45
- Require closed M5 candle: ON

## Why this matters

This upgrade avoids two extremes:

1. **Too fast/noisy:** taking every M5 burst without knowing H1/H4/D1 context.
2. **Too slow/late:** waiting for all higher timeframes to fully align before allowing a trade.

V12.46 uses the higher timeframes as a bias matrix, not as a slow all-or-nothing gate.
