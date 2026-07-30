# Dedicated range strategy — backtest verdict (do NOT trade range mean-reversion)

**Request:** add a dedicated range strategy so the bot trades chop "safely" instead of sitting it out.

**Verdict: range mean-reversion has no edge — it loses decisively, and a dedicated strategy would
only lose money.** The safe way to trade chop is the **fresh-leg override (V12.18)**, which is
already shipped and profitable. This documents why, with evidence, so the decision is on the record.

## What was tested
A standalone backtest of the core range bet — enter at a confirmed range extreme (price ≥78% up the
last-32-bar range or ≤22%, with low efficiency and ≥1.8-ATR width) and mean-revert toward the middle
— using the **real `_simulate` exit engine** (same SL-before-TP, costs, partial TPs as Validate). Two
exit geometries were compared on the same entries:

- **Range geometry** (the "proper" fix): tight stop just beyond the range edge, TP1..TP4 = 40/65/85/
  100% retrace toward the opposite edge.
- **Trend geometry** (the old FADE bet): SL = 0.75 ATR, TP = R-multiples.

## Results (36,000 M15 bars ≈ 1.5y, two independent seeds)
| Geometry | Trades | Expectancy | Win % | PF | Total R |
|---|---:|---:|---:|---:|---:|
| Range (seed 11) | 947 | **−0.79R** | 6.5% | 0.18 | −752 |
| Trend (seed 11) | 1,232 | −0.73R | 15.7% | 0.17 | −904 |
| Range (seed 29) | 919 | **−0.85R** | 5.2% | 0.12 | −785 |
| Trend (seed 29) | 1,177 | −0.76R | 15.1% | 0.14 | −895 |

Both geometries lose badly on both seeds. Strikingly, the "proper" range geometry made the **win rate
worse** (5–6%): the tight stop just beyond the edge is hit almost every time, because price sitting at
a range extreme is usually **breaking out**, not reverting.

## Why it loses (and why this keeps repeating)
You cannot tell a *range extreme that reverts* from a *breakout that continues* in real time — by the
time the trailing range/efficiency filter says "range," price at the edge is frequently starting the
next trend leg. Fading it catches the breakout in the face, and the cost of being wrong (a running
trend) dwarfs the occasional reversion win. This is the **exact inverse** of the fresh-leg override
(V12.18), which trades *with* that breakout — which is why fresh-leg **wins (+40–55% expectancy)** and
mean-reversion **loses**. It also matches the earlier FADE-mode finding (−0.73R, 18% win). Three
independent tests, same conclusion.

## Recommendation
- **Do not add a range mean-reversion strategy.** It is a proven, repeatable money-loser here.
- The "trade chop safely" goal is already met by the **fresh-leg override** — it takes the *profitable*
  side of a range (the break), at scout size, gated by your strictness.
- If you still want a disabled, clearly-labelled **experimental** range toggle to test on your own MT5
  history, it can be wired off-by-default — but the evidence says it loses, so it would ship OFF with
  this warning attached.

> Caveat: this is synthetic data, but the synthetic ranges are *sine waves that literally revert* — the
> most favourable possible case for mean-reversion — and it still loses. Real gold chop is not kinder.
