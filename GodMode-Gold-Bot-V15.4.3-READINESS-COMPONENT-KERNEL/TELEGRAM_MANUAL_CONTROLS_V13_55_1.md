# Telegram Manual Controls — V13.55.1

Configure one bot token and one authorized `chatId` in Settings. Messages and callback buttons from every other chat are ignored.

## Open a protected manual market trade

```text
/buy 0.01
/buy 0.01 3310 3340 XAUUSD
/sell 0.02 3360 3315 XAUUSD
```

Arguments are lots, optional SL, optional TP, and optional symbol. If SL/TP is omitted, the bot creates protected levels from the current broker price. Account-risk and maximum-lot rules can reduce the requested lot.

The bot posts a **CONFIRM MANUAL TRADE** button. The command cannot send an order until that authorized button is pressed. The resulting order still needs live mode, validation, healthy protection, fresh Tick Guard attestation, and broker preflight.

## Protect an open GodMode position

```text
/be 123456789
/trail 123456789
```

Replace the number with the MT5 ticket.

- `/be` calculates a broker-legal, in-profit stop and permanently arms protection for that ticket.
- `/trail` applies the first legal trailing stop and remains armed. Later protection cycles continue ratcheting it as price advances.
- Neither command can widen a stop past the deterministic winner floor, move it back across entry, manage a non-GodMode position, or bypass serialized broker readback.
- If price has not moved far enough to place a profitable stop outside the broker's stops/freeze distance, the command fails closed and changes nothing.

The same BE/trail actions are available from the inline Telegram position buttons and the existing Trades page controls.

## Other useful controls

```text
/positions
/mode
/auto
/semi
/status
/kill
/help
```

The emergency kill command controls automated execution. Manual entries still pass the kill switch, validation, sizing, identity, protection-health, Tick Guard, and broker safety checks.

Direct trades opened inside MT5 are intentionally not auto-adopted. This prevents the bot from changing positions owned by another strategy or by you outside the GodMode confirmation path.
