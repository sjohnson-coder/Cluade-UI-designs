# GodMode Gold Bot V12.54 — Loss-Feedback Entry Governor

## Why this build exists
The bot could still over-re-enter the same direction after a losing trade. That is dangerous because a failed BUY thesis can keep producing repeated BUY attempts during a developing selloff.

V12.54 adds a post-loss intelligence layer before any new first-entry is sent to MT5 or Telegram-approved.

## New protections

### 1. Same-direction loss memory
After a losing BUY/SELL, the bot now remembers:
- side
- close/failed price
- strategy
- confidence
- entry/SL context
- session
- timestamp

### 2. Fresh-edge proof required after loss
A same-direction re-entry after a loss now needs multiple confirmations:
- confidence must be materially higher than the failed setup
- price must move away from the failed exit by a minimum ATR distance
- M5 must reclaim EMA20/EMA50 in the trade direction
- recent M5 structure must break in the trade direction
- the bot should not repeat the same failed strategy unless the proof is strong
- same-side SCOUTs after a loss are blocked by default

### 3. Hard lock after repeated same-side losses
After repeated same-direction losses inside the configured window, the bot requires full reset proof before allowing that side again.

### 4. Telegram TAKE/SCOUT protected too
Telegram approval is also checked by the loss-feedback governor. Pending approvals created before the loss can no longer silently repeat a failed idea unless the fresh-edge proof passes.

### 5. Settings controls added
Settings → 5e. Automation & AI Recovery Monitor → Loss-Feedback Entry Governor:
- Loss-feedback governor
- Same-direction loss window
- Hard lock after same-side losses
- Re-entry min confidence
- Re-entry confidence delta
- Re-entry move from loss in ATR
- Require EMA reclaim
- Block same failed strategy
- No same-side scout after loss

## Recommended starting values
- Same-direction loss window: 90 minutes
- Hard lock after same-side losses: 2
- Re-entry min confidence: 82
- Re-entry confidence delta: 5
- Re-entry move from loss: 0.65 ATR
- Require EMA reclaim: ON
- Block same failed strategy: ON
- No same-side scout after loss: ON

## Behaviour example
Before:
BUY loses → BUY again → BUY again → heavy drawdown.

Now:
BUY loses → same-side BUY blocked until fresh structure, stronger confidence, EMA reclaim and price movement confirm a new edge.
