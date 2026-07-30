# GodMode V12.6 — Volatility-Normalized Position Sizing

Builds on V12.5 (Smart Profit Protection). This release fixes the **single biggest
real-money risk gap**: the bot was sizing every trade with a **fixed lot**, so the dollars
at risk swung wildly with how wide the stop was.

---

## The problem
Your `Risk per trade (%)` setting (0.5%) existed but was **never used** — entries used a fixed
`Base Lot` (and the win-streak ladder on top). With a fixed 0.05 lot on Gold:

| Setup | Stop width | $ risked with fixed 0.05 lot |
|---|---|---|
| Calm range | $4.00 | **$20** |
| Normal | $10.00 | **$50** |
| Volatile / news | $20.00 | **$100** |

Same "size", but **5× difference in actual risk**. In volatile regimes you were silently
risking far more than intended — exactly when Gold is most dangerous.

## The fix — risk-based base lot
The base lot is now sized so each trade risks ~`Risk per trade (%)` of **live equity**, given
the trade's **real stop distance**:

```
risk_$        = equity × riskPerTrade%
loss_per_lot  = (stopDistance ÷ tickSize) × tickValue     (broker-accurate)
base lot      = risk_$ ÷ loss_per_lot      (rounded DOWN to broker step, clamped to min/max)
```

Now (equity $10k, risk 0.5% = $50 target):

| Setup | Stop width | Risk-based lot | $ risked |
|---|---|---|---|
| Calm | $4.00 | 0.12 | **$48** |
| Normal | $10.00 | 0.05 | **$50** |
| Volatile | $20.00 | 0.02 | **$40** |

**Constant dollar risk** — a tight setup gets a bigger lot, a wide/volatile setup gets a
smaller lot, all targeting the same risk. (Validated by simulation across all regimes.)

## How it works with what you already have
- **Win-streak ladder rides on top.** First trade = the risk-based base; each consecutive win
  still adds `Lot Step` up to `Max Lot`; a loss still resets to base.
- **Max Lot is still a hard ceiling.** If your risk-based size exceeds it (bigger account),
  raise `Max Lot` to size fully — the bot flags this (`maxLotCapped`) so it's never silent.
- **Pyramid adds are unchanged** — they keep the engine's own protected add-sizing.
- **Always rounds DOWN** to the broker lot step, so it never overshoots the risk budget.
- **Graceful fallback** to the fixed `Base Lot` whenever MT5 equity or broker tick specs
  aren't available (so nothing breaks offline / in dry-run).
- **Broker min-lot clamp**: on a small account where even the minimum lot risks more than your
  target, it uses the broker minimum and flags `minClamped` (you're at the smallest tradeable
  size — consider a smaller risk % or it's just the floor).

## New / activated settings — Settings → 9. Lot Scaling & Pyramid
| Setting | Default | What it does |
|---|---|---|
| **Volatility-normalized sizing** | ON | Master toggle. OFF = the old fixed-lot ladder. |
| **Risk per trade (%)** | 0.5 | Now actually drives entry size (was previously unused). |
| **Base Lot** | 0.01 | Now the **floor / fallback** when sizing can't compute. |

> Needs MT5 connected (uses live equity + the broker's tick value). Turn it OFF any time to
> return to the exact fixed-lot ladder behaviour.

---

## Also in this build
- Aligned the Break-even/Trailing UI default values with the backend (cosmetic consistency
  from the V12.5 audit).
- Audit confirmed: no contradictions between the new sizing and fast-fail, smart protection,
  TP-push, pyramiding, or the manual execute endpoint (manual trades still use your lot).

Backend compiles ✓ · frontend builds ✓ · sizing math validated by simulation ✓.

### One thing to know (from the audit)
The **DXY / US10Y macro model runs on a fixed stub** unless you set `GODMODE_DXY_URL` /
`GODMODE_US10Y_URL` env vars — unconfigured, it injects a mild constant "bullish gold" tilt
rather than a real macro read. Wiring live macro + calendar feeds (and neutralizing that stub)
is the recommended next upgrade.
