# GodMode Gold Bot V12.44 — Impulse Retest Entry Mode

This upgrade fixes the behaviour seen in the 1 July signals where the bot correctly detected a strong bullish move but only reported `NO ORDER` because RSI was 83–89 and price was already stretched.

## What changed

### 1. No more chasing blow-off candles
When gold makes a large directional displacement and RSI is hot, the bot will not market-buy/market-sell the top/bottom.

### 2. Retest is now armed instead of discarded
The engine now creates an `Impulse Retest` trigger plan:

- impulse direction,
- retest zone,
- invalidation level,
- RSI reset requirement,
- confirmation-close requirement.

Telegram watchlist alerts now say **Impulse retest armed — NO ORDER YET** instead of only showing a generic blocked forecast.

### 3. Second-leg continuation entry
On later scans, if price pulls back into the retest zone / EMA structure and prints confirmation after RSI cools, the bot can convert the setup into an executable trade.

### 4. New strategy added
Added a new built-in strategy:

`Impulse Retest Continuation`

It competes in the normal strategy rotation and is preferred during:

- Strong Bullish Trend,
- Strong Bearish Trend,
- Volatility Expansion,
- Macro Repricing.

### 5. New settings
Added Impulse Retest controls under Settings → 5e:

- Impulse Retest Mode
- Impulse min move ATR
- BUY arm RSI
- BUY resume max RSI
- SELL arm RSI
- SELL resume min RSI
- Retest min confidence

## Trading behaviour

The bot now follows this sequence:

1. Detect strong impulse.
2. Refuse to chase if RSI/extension are too high.
3. Arm a retest zone.
4. Wait for price to pull back and confirm.
5. Send Telegram TAKE/SCOUT setup only after retest confirmation.
6. Manage the trade with BE, trailing, partials, TP push, fast fail, and dynamic SL recovery.

## Safety note

This does not force trades. It simply turns a late high-RSI signal into a structured retest plan. News blackout, spread, cost, market cleanliness, risk caps, validation lock, Telegram semi-auto approval and lot guard still apply.
