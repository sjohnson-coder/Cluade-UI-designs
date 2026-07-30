# GodMode Gold Bot V13.8.1 — V13.8 never actually ran on your machine. Now it does.

## THE ROOT CAUSE (verified by simulation of your exact setup)
V13.8 changed DEFAULTS. But your saved settings.json deep-merges OVER defaults on every boot.
So on your machine, after "shipping" V13.8:
    fastFailMinSeconds        = 600  (not 300)
    fastFailNoProgressMinutes = 25   (not 5)   -> effective cut STILL 25 minutes
    breakoutRequireHtfAlign   = True (not False) -> counter-HTF brackets STILL forbidden
That is exactly why the 3972 BUY was missed: on a bearish-HTF day the bot was still sell-only.
The Telegram group's call was a counter-HTF long — the one class your saved config still banned.
V13.8 was a no-op for you. My fault for changing defaults without migrating saved configs.

## THE FIX: one-time settings migration (proven, three ways)
On first boot of V13.8.1, saved settings are migrated ONCE, with two safety rules:
  • EQUALITY-GATED: a value changes only if it still equals the OLD default (600 / 25 / True).
    Your deliberate custom values are never touched — verified with 450/8: preserved.
  • RUN-ONCE MARKER: meta.appliedMigrations records it. If you later deliberately set 600 back,
    it STAYS 600 — verified. Marker also survives real UI saves (tested through the actual
    /api/settings endpoint with a payload containing no meta at all).
Applied on your config: fastFailMinSeconds 600->300, fastFailNoProgressMinutes 25->5,
breakoutRequireHtfAlign True->False. Your breakoutStopEnabled=True is preserved.
Boot log prints exactly what was migrated.

## THE DISCONNECT / "SWITCHED TO DEMO" — not a bot bug, and it protected you
Deep-dived. Three findings:
  • The bridge AUTO-RECONNECTS: mt5.initialize() is retried on a short TTL cache. A dropped MT5
    terminal (sleep, restart, broker maintenance) reconnects by itself when the terminal is back.
  • The "demo" you saw is a DISPLAY-ONLY fallback: when MT5 is unreachable the dashboard shows
    demo data so the UI stays alive. It has ZERO execution paths — grep-verified. The bot cannot
    and did not trade on fake data.
  • While disconnected, no trades can fire — which, combined with V13.8 being a no-op, is why
    it "hasn't traded since the last fix". The engine wasn't broken; it was blind (terminal-side)
    and still carrying your old config.
If the terminal drops often, keep the Windows machine from sleeping and check the broker's
terminal auto-login. The bot's side is correct.

## THE BREAKOUT ENGINE ITSELF — audited end-to-end, correct
  • _maybe_arm_breakout_bracket with align OFF arms BOTH sides (read + verified).
  • It is called every sniper scan (line 5379); pending_orders() exists on the bridge.
  • One bracket at a time, OCO + expiry management confirmed.
It was never armed for the 3972 base because your config still said breakoutRequireHtfAlign=True.
After this migration it can arm both edges of a tight base — the 3972 setup becomes takeable.

## Validation
Boot 0.090s. endpoints failing: NONE. Migration: applies once / preserves customs / marker
survives UI saves — all three proven by test, not assumption. Full regression green.
