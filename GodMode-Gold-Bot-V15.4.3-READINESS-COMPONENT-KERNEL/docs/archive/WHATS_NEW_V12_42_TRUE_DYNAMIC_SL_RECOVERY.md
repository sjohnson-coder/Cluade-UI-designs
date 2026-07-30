# GodMode Gold Bot V12.42 — True Dynamic SL Recovery

This build adds the dedicated Dynamic SL Recovery behaviour requested by Segun:

> If a trade goes sideways or starts moving against the bot, the bot keeps monitoring the live market, news/dirty conditions, structure, momentum and recovery evidence. If the bot has evidence that the trade is still valid and can recover, it can widen the stop just before SL to give the trade breathing room. If the bot finds that the setup is invalid, news/dirty market has changed the environment, or the recovery probability is weak, it fast-fails to reduce damage.

## Added

### True Dynamic SL Recovery Engine
New function: `dynamic_sl_recovery_decision()` in `backend/services/ai_monitor.py`.

It decides one of:

- `WIDEN` — high-confidence recovery, trade is near SL, safe capped SL exists.
- `HOLD` — recovery evidence exists but not near SL, or widening is not safe.
- `CUT` — setup invalidated, recovery score weak, dirty/news conditions, or spread spike against weak recovery.

### Near-SL / Near-Loss Trigger
The bot only considers widening when:

- price is within `dynamicSlNearSlAtr` ATR of the current SL, or
- floating loss reaches `dynamicSlNearLossR`.

This prevents random early widening.

### Hard Risk Cap + Max Extra R
Dynamic SL widening is limited by both:

- `dynamicSlMaxRiskPct` — hard account-equity risk cap, and
- `dynamicSlMaxExtraR` — maximum extra distance beyond the original R.

So it cannot endlessly widen stops.

### News/Dirty Market = Cut
If enabled, `dynamicSlNewsHardCut` makes the bot cut rather than widen when a trade is underwater during dirty/news conditions.

### Bounded Attempts and Cooldown
New controls:

- `dynamicSlMaxWidenCount`
- `dynamicSlCooldownChecks`
- `dynamicSlGraceChecks`
- `dynamicSlMaxHoldChecks`

This stops unlimited recovery holding.

### Tighten Back After Recovery
Once a widened trade recovers by `dynamicSlPostWidenTightenAtR`, the bot moves the SL back toward break-even/+cost.

### Settings UI Added
Settings → 5e now exposes:

- True Dynamic SL Recovery
- Dynamic SL max risk %
- Max extra R allowed
- Near-SL trigger ATR
- Near-loss trigger R
- Minimum recovery score to widen
- Max SL widen attempts
- Cooldown between widens
- News/dirty market = cut
- Tighten back after recovery R

## Important Safety Note
This is not martingale and does not add to losing trades. It only gives a valid trade limited extra room when recovery evidence is strong. If the setup is invalid, the bot cuts.
