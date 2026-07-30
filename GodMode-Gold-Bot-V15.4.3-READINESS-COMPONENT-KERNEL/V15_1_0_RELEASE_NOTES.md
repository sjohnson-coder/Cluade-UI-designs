# V15.0.8 — Intelligence Wired

Built on V15.0.7. This release connects the v15 intelligence stack to the trading
path for the first time, corrects the meaning of the headline "confidence" number,
rewrites the stop ratchet so trades are allowed to breathe, and fixes three
operational faults that made core controls appear broken.

## 1. The AI was never connected to trading decisions

The probability, regime, burst and exit engines ran on every scan, produced a full
forecast, attached it to the telemetry matrix — and were then discarded. The code
said so explicitly: *"the report is advisory and cannot authorize or veto
execution."* Every entry was decided by the older deterministic rule cascade.

This is the direct explanation for a high-confidence trade losing: the displayed
number never touched the decision.

**V15.0.8 wires it in VETO-ONLY** (`automation.v15AdvisoryVetoEnabled`, default on).
It can block a setup its own forecast condemns; it can never authorize one the
deterministic rules rejected. This direction is deliberate and non-negotiable while
`forecast.is_calibrated` is false: an uncalibrated model must never create exposure.
Veto-only is monotonically safe — the worst case is fewer trades, never more risk.

Thresholds (`v15MinWinProbability` 0.42, `v15MaxInvalidation` 0.72,
`v15MaxFastFail` 0.78) are deliberately loose. They are a coarse sanity filter, not
a claimed edge. Tighten only after the calibration counter passes 200.

## 2. "Confidence" was measuring data quality, not win probability

`confidence` was `1 - uncertainty`, where uncertainty was a weighted blend of
regime-classifier certainty, broker-feed cleanliness, news-feed availability and
score decisiveness. A setup could report 92% "confidence" while its modelled win
probability sat near a coin flip. The number was never wrong — it was answering a
different question than the operator was asking.

Now split into three explicitly named quantities:

| Field | Answers |
|---|---|
| `data_confidence` | "How trustworthy are my inputs?" (**not** a win rate) |
| `win_probability` | "What fraction of setups like this reach TP before SL?" |
| `is_calibrated` | Whether any of it is measured rather than hand-tuned |

`confidence` now carries `tp_before_sl` for backward compatibility.

## 3. Regime confidence was inflated

`primary, confidence = ordered[0]` took the winning regime's **raw score** as its
confidence. With scores `{strong_trend: 0.90, mean_reversion: 0.88}` the classifier
reported 90% confident while effectively coin-flipping between a trend read and its
exact opposite. Because this value is weighted 40% into the forecast's uncertainty
term, the inflation propagated straight into the headline number.

Confidence is now the **margin over the runner-up**. Near-ties collapse to
`transition` and are reported as contested.

## 4. Break-even was cutting trades that should have breathed

The old ratchet:

```
if peak >= 0.6: floor = max(floor, 0.02)      # ignores ATR entirely
if peak >= 1.0: floor = max(floor, peak - max(0.35, atr_r * 1.2))
if peak >= 1.5: floor = max(floor, peak - max(0.28, atr_r))
```

Two structural faults:

- **The 0.6R rung ignored volatility**, while both higher rungs scaled by ATR. On
  XAUUSD M5 a 0.6R excursion followed by a routine pullback is ordinary noise.
  Snapping to +0.02R there converts eventual winners into scratches — hardest in
  exactly the high-volatility conditions where the pullback is most expected.
- **No rung consulted forward evidence.** continuation, recovery and invalidation
  were all computed, passed in, and ignored. A setup with strong continuation was
  protected on the same schedule as one falling apart.

The rewrite makes both the **arming point** and the **trail width** functions of
volatility and evidence, adds an explicit `breathing` state, and keeps the ratchet
monotonic (verified: 0 violations in 4,000 randomised cases).

A **peak-retention backstop** (0.62× peak, the project's audited
`profitLockFraction`) was added after the first draft revealed its own hole: a wide
breathing band could otherwise leave a 1.6R peak protected at only +0.04R.
Breathing must not become "give it all back".

## 5. Burst could effectively never fire

`base_protected` required the ratchet to have armed; `minimum_profit` separately
required **current** profit ≥ 0.60R. A trade that armed at 0.60R and pulled back at
all satisfied neither, so the window was a razor-thin band that in practice never
opened. Burst now fires as the base trade *approaches* protection, using the same
`AdaptiveExitEngine` arm point the live ratchet uses, so the two cannot drift apart.

## 6. Validation lock and auto-trading would not switch

Root cause: **409 revision conflict.** The browser caches the settings revision it
last saw; any background write (MT5 heartbeat, autosave, maintenance patch) advances
it; the next toggle click submits a stale value, is rejected, and `Settings.tsx`
rolls the switch back visually.

The fix already existed in this codebase for `POST /api/settings` and had simply
never been propagated to the atomic toggles. Optimistic concurrency prevents *lost
updates* when two writers edit overlapping field sets. These endpoints each mutate
one boolean and are idempotent — no lost-update hazard, only a false-conflict
hazard. Multi-field writers (`/api/mt5/connect`, `config_import`, `rollback`) keep
strict enforcement.

## 7. Telegram recap was dead — cache race

`_refresh_analytics_cache_sync` blanked `_ANALYTICS_CACHE` *before* rebuilding it.
Any concurrent reader in the window crashed with `KeyError: 'data'`. This broke
`POST /api/telegram/recap` outright and made analytics reads intermittently fail.
The cache is now swapped atomically and read defensively.

## 8. Fonts

The global `!important` Arial override was present again and silently defeated every
Archivo / Inter / Geist Mono declaration in the same file (`!important` collapses
cascade specificity to source order, and it was last). Removed.

Separately: **Geist Mono was used for every numeric surface but never loaded** — all
prices and R-values were falling back to the browser default monospace. Now loaded.

## 9. Undiagnosable safety-gate rejection

A blocked manual trade reported only *"authoritative runtime readiness is not
healthy"* — true, but impossible to act on. The specific reasons were already
computed and thrown away at the boundary. They are now surfaced, e.g.
*"(Critical component unhealthy: reconciliation)"*.

Relatedly, the reconciliation loop called `RUNTIME_HEALTH.fail()` whenever MT5 was
disconnected. Being unable to reconcile while the broker link is down is an expected
idle state, not a component fault, and it produced a confusing double-blocker
stacked on the real, self-explanatory "MT5 is disconnected". Now reported as idle.
Nothing is loosened — the MT5 blocker still blocks.

## 10. V15.0.7 shipped with a failing test suite

Two tests asserting the Tick Guard source-only disclosure failed because
`RELEASE_MANIFEST.json` had been regenerated down to `{version, buildId, files}`,
dropping the `tickGuard` block. Restored, rebuilt from on-disk facts.

## Honest scope

These are engineering fixes. **They do not make a strategy profitable.** Connecting
the forecast does not make the forecast correct: the coefficients in
`probability_engine.forecast()` are hand-typed, and `is_calibrated` stays false
until 200 labelled outcomes exist. That is precisely why the model is wired
veto-only rather than as an authorizer.

To find out whether the edge is real, run in SHADOW/DEMO until the calibration
counter passes 200, then read the Brier score in
`GET /api/v15/overview → calibration`. A Brier score meaningfully below 0.25 means
the probabilities carry information; at or above it, they do not.

## Verification

- `python3 -m pytest` — 328 passed.
- `npx tsc --noEmit` — clean.
- `python3 VERIFY_RELEASE.py` — PASS (runtime + archive).
- Exit-engine monotonic invariant — 0 violations / 4,000 randomised cases.
- Toggle regression reproduced pre-fix and verified post-fix against a
  maximally-stale revision; multi-field writers confirmed still enforcing.

---

# V15.0.9 — Cascade Guard

## 1. Directional cascade guard (dump/pump backstop)

On 28 Jul XAUUSD fell ~4081 → ~4017 and the bot took BUY entries into it. Nothing
stopped that, because the only higher-timeframe protection was the HTF hard veto,
which requires BOTH the D1 AND H4 trend LABELS to already read bearish. Trend labels
are lagging aggregates — a one-session collapse leaves D1 still labelled from the
preceding days, so the AND-condition never became true while the move was happening.

There was no dump/pump execution gate at all. The `momentumSpikeWatch` setting that
resembled one lives in the **telegram** block, defaults to `False`, and only sends
an alert — it has never blocked a trade.

`_cascade_state()` measures net displacement in ATR over a rolling window plus
directional purity, so it fires on velocity rather than on labels. Counter-cascade
entries are blocked. Verified against a reconstruction of the 28 Jul move: BUY into
a DOWN cascade is blocked even at 80% model confidence; SELL is unaffected.

Fails OPEN if candles are unavailable — a guard that can block trades must not
manufacture blocks from a data outage.

Settings: `cascadeGuardEnabled` (on), `cascadeMinDisplacementAtr` (2.5),
`cascadeMinPurity` (0.55).

## 2. High-conviction post-loss cooldown override — OFF by default

Requested: ignore the loss cooldown when a high-probability setup appears. Granted,
but gated on three conditions, each blocking a specific failure of the naive version:

- **Calibrated model only.** `is_calibrated` is currently false. Letting an
  unvalidated score switch off a safety brake is circular — the same scorer that
  just lost would be authorising its own retry.
- **Must trade WITH the cascade, never against it.** This is the condition that
  matters. On 28 Jul the losing BUYs were bounce setups in an oversold cascade —
  exactly the pattern that scores HIGH on continuation and recovery features. A
  confidence-only override would have fired on precisely the trades that lost.
- **Never overrides the loss-streak breaker.** One loss is noise; N consecutive
  losses means the current read is systematically wrong.

Settings: `cooldownHighConvictionOverride` (off),
`cooldownOverrideMinWinProbability` (0.75).

## 3. Breathing telemetry — the real problem, instrumented not guessed

The 28 Jul session (7 trades, all SELL):

| Metric | Value | GodMode bar | |
|---|---|---|---|
| Win rate | 57% | — | fine |
| Avg win | 1.37 | — | |
| Avg loss | 2.22 | — | |
| Loss/Win | **1.63x** | < 1.50x | FAIL |
| Profit factor | **0.82** | > 1.30 | FAIL |

**Entries are not the problem — exits are.** A 57% win rate is a working entry
engine. The money is lost to asymmetry: winners scratched at +0.33/+0.45/+1.22
while losers ran to full stop at -2.73/-3.38. At an equal loss/win ratio the same
trades produce PF 1.33 — above the bar.

Suspected mechanism: live breathing requires `recoveryScore >= 70`
(`aiDynamicRecoveryScoreToBreathe`) while the recovery monitor's NEUTRAL fallback
is **50** and its error fallback is **0**. A winner is therefore protected rather
than given room, on any neutral or failed recovery read.

The threshold was deliberately **not** retuned. Changing a live stop parameter on
seven trades is curve-fitting. Instead `BREATHING_TELEMETRY` now records every
breath request, whether it was granted, the denied scores, and the running median,
exposed at `GET /api/trade-management/status → breathingTelemetry`. Tune from that once a
few dozen trades exist.

## 4. Fixed a bug introduced by the cooldown override itself

The override referenced `matrix` before it was constructed in `_auto_trade_tick`,
raising `UnboundLocalError` and killing the tick whenever an override was granted.
Caught in testing before release; detail is now stashed in `AUTO_TRADE_STATE` and
attached once the matrix exists.

---

# V15.1.2 — Cascade-Aligned Entry

## What was asked, and what was built instead

Request: "when there's a dump, detect it and sell; when there's a pump, detect it and
buy — on time, not late."

The literal form of that instruction is self-defeating. A move only becomes measurable
once it is extended, so "fire as soon as the cascade is detected" is structurally an
instruction to enter at the worst available price. This account already contains that
failure: the 15:06 SELL at 4025.58, entered near the session low, closed -3.38.

Built instead: the **cascade sets DIRECTION, the retest sets TIMING**. The existing
`_detect_impulse_retest` state machine already requires a pullback into the 23.6-61.8%
retracement, a rejection close, an anchor reclaim and an RSI reset before reporting
CONFIRMED. It refuses to arm at the extreme by construction.

The gap that was closed: that engine gates on `impulse_side == side`, so it only ever
VALIDATES a side the decision engine had already chosen. It could not propose one. In a
clean cascade where the base engine returned WAIT, the machinery never ran for the
with-cascade side at all — the setup was invisible rather than rejected.

Proposals pass through the identical downstream chain (HTF veto, advisory veto, risk
sizing, pre-live safety, session and spread filters). This can make a setup visible. It
cannot approve one.

## Two faults found in my own work, by testing it

**1. The anti-chase guard was missing, and the borrowed one does not work in a cascade.**
`_detect_impulse_retest` accepts `abs(price - ema20) <= atr * 0.65` as evidence of a
pullback. Inside a sustained one-way move EMA20 trails just behind price continuously,
so that clause stays true for the whole cascade — including at the extreme with no
retracement whatsoever. Verified: a pure 30-bar down-impulse with zero pullback still
reported CONFIRMED. Relying on it would have reproduced the exact 15:06 entry-at-the-low
failure this feature exists to prevent. An explicit retracement measurement was added,
taken directly from price and independent of any moving average.

**2. The feature was unreachable as first written.** A scan across 38 simulated pullback
depths fired **zero** times. The cascade was measured on a rolling 12-bar window, so any
retracement deep enough to clear the 20% anti-chase guard also flattened that window and
reported "no cascade". The two conditions were mutually exclusive — the same
mutually-unreachable-gates bug this project already hit with the burst engine
(`base_protected` AND current profit >= 0.6R).

The modelling error was treating a cascade as a per-bar measurement. It is a *context*:
a market that has just fallen 7 ATR is still a falling market during the pause. It now
latches on detection and holds until genuinely invalidated — retraced past the ceiling,
or reversed — rather than merely because price paused.

## Verified behaviour

Fed bar-by-bar through a single evolving market (impulse down, then pullback, then
resumption):

| bar | close | cascade | latched | retrace | fires |
|---|---|---|---|---|---|
| 0-4 | 4009-4016 | yes | no | 6-28% | no |
| 5 | 4013.80 | yes | yes | 22% | **SELL** |

Entry at 4013.80 against an impulse low of 4006.90 — **6.90 points above the low**.
Retest CONFIRMED, retracement 22%.

Anti-chase confirmed separately: same dump, still at the extreme, no pullback -> no
proposal.

Settings: `cascadeEntryEnabled` (on), `cascadeEntryMinRetrace` (0.20),
`cascadeEntryMaxRetrace` (0.75), `cascadeLatchBars` (10), `cascadeEntryQuality` (SCOUT).

## Still unresolved

The capture problem from the 8-trade session (PF 0.82, wins and losses both ~0.35R
against a 7-18pt stop) is **not** addressed here. Something is closing those trades well
before either stop or target; the time-stop spares profitable trades, so it is fast-fail
or the recovery-based cut. That requires the exit reason per trade from
`backend/data/decision_journal.jsonl`. Not diagnosed, not guessed at.
