# GodMode Gold Bot V12.62 — Trade Quality Governor

This upgrade focuses on the exact failure pattern seen in the user's screenshots: many small wins being wiped out by a few large losses, Burst firing in weak/choppy conditions, late entries after extension, and scaling while edge is not clean enough.

## Added

### 1. Large-Loss Fast-Fail Governor
- Tightens the default fast-fail floor from loose loss tolerance to a stricter session-protection model.
- Uses both R-based and points-based loss protection.
- If a trade is red, past the loss floor, and recovery probability is weak, it closes faster before becoming a large outlier loss.

### 2. Net Edge Governor
- Reads recent closed-trade performance from the in-memory cache only, so it does not hit MT5 history during entry decisions.
- If average loss is too large compared with average win, the bot switches to defensive filtering.
- Defensive filtering requires SNIPER-grade confidence before allowing another normal entry.

### 3. Late-Entry Blocker
- Blocks BUY/SELL entries that are too extended from EMA20 without a fresh pullback/reclaim.
- This is designed to stop chasing candles after the move is already mature.

### 4. Chop Overtrade Governor
- Calculates trend efficiency and direction flips from the current market snapshot.
- Blocks normal entries in low-efficiency/choppy tape unless strict scout conditions are met.

### 5. Strict Burst Safety Lock
- Burst is now stricter than normal trading.
- Burst is blocked in chop, late extensions, weak confidence, weak recovery, and after recent burst losses while session edge is weak.
- Burst fast-fail is tightened so a burst leg cannot become the largest loss of the day.

### 6. Strict Scaling Guard
- Pyramid/scaling now requires extremely clean continuation.
- Scaling is blocked if the market is choppy, late/extended, or confidence is below the scale-only floor.

## New Settings

Settings → Automation & AI Recovery Monitor now includes:
- Net Edge Governor
- Defensive avg loss/win ratio
- Defensive min confidence
- Large-loss fast fail
- Large-loss floor (R)
- Late-entry blocker
- Max entry extension ATR
- Chop overtrade governor
- Chop trend-efficiency floor
- Scale only min confidence

Settings → Protected Burst Mode now includes:
- Strict Burst Safety Lock
- Block Burst in chop
- Burst max extension ATR
- Burst fast-fail seconds
- Burst fast-fail R

## Speed / UI

The new governors use the cached dashboard/trade/market snapshots and do not trigger new heavy MT5 history scans. This preserves the V12.61 turbo UI behaviour.

## Recommended starting values

- Large-loss floor: -0.35R
- Large-loss points floor: 2.50 XAUUSD points
- Max entry extension: 0.95 ATR
- Burst max extension: 0.85 ATR
- Defensive avg loss/win ratio: 2.0
- Defensive min confidence: 86%
- Burst min confidence: 82%
- Burst recovery score: 72%
