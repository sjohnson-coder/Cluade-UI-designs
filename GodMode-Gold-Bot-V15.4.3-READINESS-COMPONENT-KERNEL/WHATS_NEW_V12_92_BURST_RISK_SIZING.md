# GodMode Gold Bot V12.92 — Risk-based burst sizing (scales with account + lot size)

## Your two design points — both correct, both built
1. **Fixed -$0.75 basket stop was wrong** — it doesn't scale with lot size. FIXED: the basket
   hard-loss and giveback are now DERIVED from % of balance, not fixed dollars.
2. **Fixed lot per leg was wrong** — you want incremental sizing by account size + max risk, with
   the whole burst counting as ONE trade. BUILT exactly that.

## How it works now (riskModel = account_pct, default)
- The WHOLE burst risks at most **burstRiskPctOfBalance** of balance (default 1%). That is one
  trade's risk budget for the entire basket.
- That budget is converted to total lots via the existing gold tick-math ceiling
  (balance x risk% / stop-distance), then distributed across the legs.
- **Distribution: incremental_down** (your choice) — biggest leg first, each add = 0.6x the
  previous (incrementalDownStep). Safer: the largest position is the earliest/best-priced, adds
  shrink. Verified: batch of 3 -> [0.05, 0.03, 0.01].
- **Everything scales with balance**: double the account -> the budget (and lots, and the basket
  stop) roughly double, automatically. No fixed dollars anywhere in the risk path.
- **Basket exits are now risk-based too**: hard-loss = burstRiskPctOfBalance of balance;
  giveback = burstGivebackFractionOfPeak (40%) of peak once peak >= burstMinPeakPctForGiveback
  (0.2%) of balance.

## Safety preserved
- Per-leg cap (maxPerPositionLot) and maxTotalLots still clamp everything — raise these when you
  scale up.
- Near-BE early arm + self-protected legs (V12.91), one-batch-per-campaign, edge-valid-at-fire,
  200s fast-fail — all intact.
- demoOnlyUntilValidated still ON: burst runs on DEMO only. You can raise lots on demo NOW to
  test scaling (your choice); it will not trade live until you disable demo-only.
- Legacy fixed ladder still available: set riskModel = "fixed_usd" to revert.

## On your chart (the "missed signal")
Honest read: the SELLs printed at 4014-4017 — the BOTTOM of a completed 4033->4014 leg, then a
2-hour base at 4017. That is late entry into exhaustion, and the higher timeframe is flattening
into a range, not signalling a fresh sell. A burst there would be counter-trend-at-the-bottom —
the shape of your historical oversized losers. This is NOT a spot to pile in; the edge-valid gate
correctly keeps burst out of dead legs. Your instinct that it is late is right; the answer is not
more size there.

## Validation
Boot 0.077s. Incremental-down sizing verified [0.05,0.03,0.01]; budget scales with balance;
risk-based basket stop derives from balance %. Full V12.67-92 regression green.

## To scale up later
Raise burstRiskPctOfBalance (or maxPerPositionLot / maxTotalLots) after burst proves profitable
on demo. The risk stays a fixed % of account regardless of the numbers you set.
