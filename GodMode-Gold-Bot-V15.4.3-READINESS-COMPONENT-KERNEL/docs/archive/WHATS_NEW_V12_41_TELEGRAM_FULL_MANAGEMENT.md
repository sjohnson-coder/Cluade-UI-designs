# GodMode Gold Bot V12.41 — Telegram Full Management Bridge

This build strengthens the Telegram semi-auto path so a Telegram-approved trade is managed exactly like an auto-approved trade.

## Added / fixed

1. **Telegram TAKE/SCOUT inherits the full decision trade plan**
   - Structural SL
   - TP1, TP2, TP3, TP4 plan
   - TP4 broker backstop for single-runner trades

2. **Telegram-approved split TP1-TP4 support**
   - If lot size is large enough, Telegram TAKE/SCOUT can now use crash-safer split child positions.
   - Each child order gets its own broker TP.
   - If the lot is too small, it safely falls back to a single TP4 runner.

3. **Full management auto-arms after Telegram execution**
   - Break-even
   - Smart trailing
   - Partial profit closes when broker lot size allows
   - TP push
   - Fast-fail/protective close
   - Telegram management alerts

4. **Split-order context capture fixed**
   - Multi-target child order/deal/position IDs are now stored in the trade context store.
   - Closed-trade history and learning can attribute split child orders to the correct strategy.

## Important limitation

App-managed BE/trailing/partials/TP-push/fast-fail require the backend to keep running and MT5 to stay connected.
Broker-side SL and TP remain active even if the backend is closed. Split child TP orders provide stronger crash-safety when lot size is large enough.
