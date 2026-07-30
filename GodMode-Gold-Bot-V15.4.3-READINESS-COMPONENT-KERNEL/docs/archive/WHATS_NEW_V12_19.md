# GodMode V12.19 — Strategy installs are ADDITIVE (no more global config rewrite)

This is the architecture change you asked for: **installing a strategy adds it to your rotation
with its own rules — it no longer rewrites the whole bot's strictness.**

## Before vs after
**Before:** clicking Install on a Lab candidate overwrote your **global** AI strictness (mode,
confidence, R/R, efficiency). One "Sniper Quality-Only" install silently clamped the *entire* bot
to sniper — which is why every 80% setup got parked. (V12.17 added the Uninstall to escape it.)

**Now:** Install registers the candidate as a **real strategy in the rotation**, carrying its own
**entry gates** (`gateProfile`: confidence / R-R / efficiency). The engine's router already scores
**every** strategy each bar (regime fit × win-rate × expectancy × session) and picks the best —
and now it judges that strategy's entry by **that strategy's own gates**, not one global lock.
Your global strictness is left exactly as you set it.

So if you install "Sniper Quality-Only," it becomes **one strict strategy competing in the mix** —
the router uses it only when it's genuinely the best fit, and only its trades are sniper-strict.
Your other strategies keep trading their own setups at your normal strictness. No global clamp.

**Honest note on selection:** the router favours the strategy with the best regime fit × win-rate ×
expectancy. On the current line-up the strong built-in specialists (e.g. Liquidity Sweep) usually
win, so an installed *generic strictness tuning* is picked only when it genuinely out-scores them —
which is "pick the best" working as intended. Installs that earn selection are ones with real,
superior backtest evidence and/or a distinct regime niche (that's what a future dedicated **range
strategy** is for). The guaranteed, immediate win here is the removal of the **global clamp**.

## Per-strategy gates (the engine foundation)
- A strategy may carry a `gateProfile = {minTakeScore, minRiskReward, minEfficiency}`.
- When that strategy is the one the router selects, the entry is judged by those values; otherwise
  the global strictness applies.
- The 12 built-in strategies carry **no** gateProfile, so their behaviour is **byte-for-byte
  unchanged** (verified: identical backtest to V12.18).

## Install / Uninstall
- **Install** = additive, non-destructive. Shows in the Strategies page; competes in the rotation.
- **Uninstall** (V12.17) removes it from the rotation. For new additive installs your global config
  is never touched; for a *legacy* install that had rewritten global strictness, Uninstall still
  restores it (snapshot, or safe balanced defaults) so anyone stuck in the old sniper lock is freed.

## Autonomy
Per your choice — **the AI recommends, you approve.** Nothing installs or switches itself; the Lab
back/forward-tests candidates and recommends, and you click Install. (No background auto-switching.)

## Validation
- Per-strategy gate plumbing is **zero-regression** — built-ins (no gateProfile) give a byte-identical
  backtest to V12.18 (0.274R, PF 1.49, strong; same with the idealRegimes boost).
- **Additive install leaves global strictness untouched** — installing "Sniper Quality" keeps the
  global mode at *balanced* (verified live + in backtest).
- **Legacy uninstall still un-sticks** the old global sniper lock (restores balanced).
- When an installed strategy **is** selected, its own gateProfile governs the entry (verified).

Validate on your own MT5 history before sizing up; the absolute numbers are synthetic.
