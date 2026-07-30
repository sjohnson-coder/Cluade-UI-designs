# GodMode Gold Bot V12.45 — Low-Latency M5/M15 Sniper Lane

## Purpose
V12.45 adds a faster entry lane for clean momentum shifts without dropping into noisy M1/tick trading.

The design is:

- **M15 = context / bias safety**
- **M5 = executable trigger**
- **Tick = final current bid/ask/spread only**

This means the bot can react faster to swift XAUUSD momentum shifts, but it still avoids taking random M1 noise.

## What changed

### 1. Fast Sniper Lane
Added a new low-latency decision path that checks:

- M5 displacement candle
- M5 breakout of recent structure
- M5 EMA20/EMA50 alignment or transition reclaim
- M15 context not opposing the move
- RSI is not overheated
- price is not too extended from M5 EMA20
- spread/news/dirty-market safety

If clean, it can produce a `TAKE_TRADE` decision even when the heavier M15/H1 engine is still waiting.

### 2. Cleaner entry philosophy preserved
The bot does **not** trade M1 or tick-based noise. It only uses tick to execute a confirmed M5/M15 signal at the live bid/ask.

### 3. Faster auto loop
When Fast Sniper Lane is enabled, the background auto-entry loop runs at about **1 second** instead of 3 seconds.

### 4. Fast Telegram approval
Telegram TAKE/SCOUT buttons are now sent **before** chart upload. The chart is sent afterwards as context. This avoids chart upload delaying semi-auto approval.

### 5. Faster Telegram button polling
Telegram callback polling is now configurable and defaults to about **2 seconds** instead of 12 seconds.

### 6. Fast lane status endpoint
Added:

```text
/api/fast-sniper/status
```

This shows whether the fast lane is active, its last decision, latency, loop timing and why it did or did not fire.

### 7. Settings UI controls
Added under:

```text
Settings → 5e. Automation & AI Recovery Monitor → Fast Sniper Lane
```

Controls include:

- Fast Sniper Lane ON/OFF
- Fast loop seconds
- Decision TTL seconds
- Trigger timeframe
- Context timeframe
- Min displacement ATR
- Breakout lookback candles
- Max extension ATR
- Min sniper confidence
- Allow transition scout
- Require closed M5 candle

## Recommended default
For cleaner but faster entries:

```text
Context timeframe: M15
Trigger timeframe: M5
Require closed M5 candle: ON
Min displacement ATR: 0.75
Max extension ATR: 1.15
Min sniper confidence: 76
Allow transition scout: ON
```

Turn `Require closed M5 candle` OFF only for more aggressive demo testing.

## Safety note
This upgrade makes the bot faster, but it does not guarantee profit. Forward-test on demo first and check execution memory for fill delay, slippage and rejected orders.
