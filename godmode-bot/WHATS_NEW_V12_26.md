# GodMode V12.26 — Multi-strategy scan + a transparency panel

You asked for two things: see *which* strategy the bot would pick (and why others are blocked), and
have it actually scan **all** strategies so you're not blocked when a better-suited one exists.

## 1. The AI now judges every strategy on its OWN gates, each bar

Before: in a "wait" regime (e.g. Compression / Range) the engine short-circuited straight to
**No-Trade / Standby** — it never gave your other strategies a chance, even an installed one built
for that regime.

Now, every bar:
- Each enabled strategy is scored (regime fit + live win-rate + expectancy + session) **and** judged
  against **its own** entry gates — chop tolerance (`minEfficiency`), confidence bar (`minTakeScore`),
  and R:R (`minRiskReward`) from its `gateProfile`.
- The bot takes the **best-ranked strategy that passes its own gates.** So if your top-ranked trend
  strategy is blocked by chop but you've installed a range-tolerant strategy that fits, **that one
  trades** instead of a blanket block.

### It still can't manufacture a losing trade
The **universal safety gates — news blackout, spread cap, cost discipline, dirty/illiquid market,
over-extension, structure, session, HTF, no-pyramid-into-losers — block ALL strategies.** Verified:
when those fire, the scan finds nobody eligible and stands aside. So the bot only "unblocks" a bar
when a *fitting, already-installed* strategy genuinely passes — it never loosens discipline to force
a chop trade. If no installed strategy fits the regime, it still (correctly) stands aside, and the
panel tells you to run the **Strategy Lab** to find/install one that does.

## 2. New "Strategy Scan" panel on the AI Agent page

A live table showing **every** enabled strategy with its **Score · Confidence · Verdict
(WOULD TRADE / blocked) · Why blocked**, with the chosen one tagged *selected*. Now when the bot
holds, you can see at a glance that it scanned the whole roster and exactly which gate stopped each
one — not an arbitrary "No-Trade."

## How to actually use it
Out of the box the built-in strategies all require a trending tape, so in chop they're all correctly
blocked (you'll see it in the panel). To trade a range/compression regime, open **Analytics →
Strategy Lab**, run it, and **install** a candidate that backtests positive there (e.g. a chop-tolerant
profile). Once installed it joins the scan with its own gates and the bot will select it when it fits
— exactly the "best strategy for each trade" behaviour, with the Lab's out-of-sample validation as the
guardrail.
