# GodMode V15.10.4 R68.18 — patch guide

Three changes, in priority order. Line numbers are from the shipped
`backend/app.py` (31,394 lines) in
`GodModeGoldBotV15_10_4R68_18RESEARCHSESSIONOVERLAY.zip`.

---

## Patch 1 — stop the "Order NOT filled" storm

**Symptom:** five identical red alerts inside one minute (3:49 PM screenshot), all
reading `Reason: New live entry blocked by the high-impact economic-news window.`

### Root cause, in two parts

**(a) A one-word classification miss.** `_telegram_minimal_category()` routes to the
throttled `rejection` class only on these substrings:

```python
if "trade rejected" in tl or "order rejected" in tl \
   or "rejection summary" in tl or "order not sent" in tl:
    return "rejection"
```

The alert says **"Order NOT filled"** — none of them match. Verified against the
shipped code:

```
category      : 'other'                                     <- not 'rejection'
event_key     : other:19870694:bbf8a6479a6f6259...          <- hashes the FULL text
rejection key : rejection:19870694                          <- one per 90s window
```

The `rejection` key collapses every retry in the window regardless of side, lots or
reason. The `other` key hashes the whole message, so any variation in the reason
string — a spread value, a price, a count — mints a brand-new alert.

**(b) The real design fault.** `_execute_mt5_serialized()` (line 25969) calls
`_news_entry_guard()` and returns its block dict. That flows back to `_runner()`
(line ~24280) where **any** non-ok result is treated as an execution failure:

```python
if result.get("ok"):
    ...
else:
    block_msg = str(result.get("message") or "Unknown reason")[:400]
    _telegram_send_text(f"🔴 *GodMode — Order NOT filled*\n...")
```

A known, self-clearing **policy block** is being reported on the same red channel as
a genuine **broker rejection**. R48's intent was right — never leave a DISPATCHED
with no outcome — but its scope caught policy decisions too. The news window lasts
minutes while the scanner retries every couple of seconds, so the alert fires once
per attempt forever.

### The fix

Copy `telegram_event_policy.py` to `backend/services/`, then:

**1. Import and create one module-level latch:**

```python
from services.telegram_event_policy import (
    BlockLatch, classify_execution_outcome, format_block_message, format_clear_message,
)

EXECUTION_BLOCK_LATCH = BlockLatch(
    remind_after_seconds=float(
        (SETTINGS_STATE.get("telegram") or {}).get("blockReminderSeconds", 900.0)
    )
)
```

**2. Replace the `else:` branch at ~line 24280:**

```python
if result.get("ok"):
    AUTO_TRADE_STATE["lastFire"] = time.time()
    _capture_entry_context(result, decision_copy, payload, entry_type, strategy_name)
    result["event"] = result.get("openEvent") or _notify_trade_event("auto_trade", result, payload)
    # a fill proves every prior block has lifted
    for cleared in EXECUTION_BLOCK_LATCH.clear_all():
        try:
            _telegram_send_text(
                format_clear_message(cleared.get("reasonCode", "block"), cleared),
                event_key=f"block_clear:{cleared.get('reasonCode','block')}",
            )
        except Exception as exc:
            _report_suppressed_exception("execution_block_clear_telegram", exc)
else:
    outcome = classify_execution_outcome(result)
    should_alert, info = EXECUTION_BLOCK_LATCH.should_alert(outcome.reason_code) \
        if outcome.is_policy else (True, {})

    if should_alert and outcome.telegram:
        try:
            _telegram_send_text(
                format_block_message(outcome, result, signal_side, payload.get("volume", "?"), info),
                # forces the collapsing key even if classification drifts later
                event_key=f"{outcome.category}:{outcome.reason_code}",
            )
        except Exception as exc:
            _report_suppressed_exception("direct_execution_failure_telegram", exc)

    # the dashboard/journal still records EVERY attempt — only Telegram is throttled
    try:
        _push_notification(
            "Entries paused" if outcome.is_policy else "Order not filled",
            str(result.get("message") or "")[:400],
            "warning" if outcome.is_policy else "danger",
            {"blocked": True, "reason": result.get("reason"), "source": "direct_auto",
             "outcomeKind": outcome.kind, "suppressedAlerts": info.get("suppressed", 0)},
        )
    except Exception as exc:
        _report_suppressed_exception("direct_execution_failure_notification", exc)
```

**3. Add "order not filled" to the rejection class** (defence in depth — one line at
the `rejection` check in `_telegram_minimal_category`):

```python
if ("trade rejected" in tl or "order rejected" in tl or "rejection summary" in tl
        or "order not sent" in tl or "order not filled" in tl or "entries paused" in tl):
    return "rejection"
```

**4. Gate the dispatch earlier.** The direct path lacks the pre-dispatch guard the
auto path has at line 25088. Add it before `_execute_mt5_serialized` so a known
blackout never reaches DISPATCHED at all:

```python
_pre = _news_entry_guard()
if not _pre.get("ok"):
    return {**_pre, "policyBlock": True, "executionState": "POLICY_BLOCKED"}
```

### Verified result

`python3 test_telegram_event_policy.py` — 8/8 pass:

| Scenario | Before | After |
|---|--:|--:|
| The screenshot: 5 blocked dispatches | 5 alerts | **1** |
| 30-min news window, 2 s scan (900 attempts) | up to 900 | **2** (entry + one reminder) |
| Spread-spike message with changing digits | 6 alerts | **1** |
| Genuine broker rejection | 1 alert | **1** (unchanged) |

Nothing is hidden: every attempt still lands in the dashboard, journal and
notification store. Only the phone gets quieter.

---

## Patch 2 — cost-relative minimum stop

**This is the highest-expectancy change available in the bot.** Measured across
4,077,891 M1 bars: gross expectancy is flat (~0.00 R) at every stop size, while net
expectancy runs from −0.019 R at a 1.00 ATR stop to −0.221 R at a 0.08 ATR stop.
The entire 0.20 R difference is transaction cost.

Current config allows a $1.50 stop:

```
earlyIntentProbeMinStopPoints = 1.5   ->  cost is 29.3% of risk per trade
```

Run `python3 cost_relative_stop.py` for the full table against your live settings.

Copy `cost_relative_stop.py` to `backend/services/` and call it in the entry gate
chain, next to the existing spread gate:

```python
from services.cost_relative_stop import evaluate_stop, minimum_stop_for, volume_for_risk

gate = evaluate_stop(
    stop_distance=abs(entry_px - float(plan["sl"])),
    spread=float(market.get("spread") or 0.0),
    entry_slippage=float(broker_costs.get("slippage", 0.02)),
    exit_slippage=float(broker_costs.get("exitSlippage", 0.02)),
    min_cost_multiple=float(cfg.get("minStopCostMultiple", 20.0)),
)
if not gate.ok:
    if bool(cfg.get("widenStopToCostFloor", True)):
        new_stop = minimum_stop_for(spread, min_cost_multiple=...)
        # widening without resizing silently increases cash risk — always resize
        payload["volume"] = volume_for_risk(risk_cash, new_stop, contract_size)
        plan["sl"] = entry_px - new_stop if side == "BUY" else entry_px + new_stop
    else:
        return blocked(gate.reason, {"stopGate": gate.as_dict(), "policyBlock": True})
```

Suggested settings:

| Setting | Value | Why |
|---|---:|---|
| `automation.minStopCostMultiple` | `20.0` | caps cost at 5% of risk — the knee of the curve |
| `automation.widenStopToCostFloor` | `true` | keep the setup, fix the economics, resize the lot |
| `automation.earlyIntentProbeMinStopPoints` | `1.5` → **remove** | superseded; a fixed point floor cannot track spread |

---

## Patch 3 — burst quality

The burst machinery is already well built: one-batch-per-campaign lock, ATR-relative
stop room (0.55), armed-retest timing guard, per-leg dispatch timestamps, 900 s
blocker reminders. Three gaps remain.

**(a) The ladder escalates into weakness.** `0.04 → 0.06 → 0.08` adds *more* size at
*worse* prices. Both this study and your ChatGPT blueprint reach the same rule: a
burst is a risk-budget allocation, never a recovery ladder. Invert it — `0.08 → 0.06
→ 0.04` — so the largest leg sits at the best price and each add reduces marginal
risk. Total basket risk is unchanged; the average entry improves.

**(b) Legs inherit the base stop distance.** Each leg enters later and worse, so an
identical stop means later legs carry a higher cost-to-risk ratio. Apply Patch 2's
gate per leg, not once per batch.

**(c) No session gate on burst arming.** Bursts need continuation. Measured median
range per session (in ATR):

| Session | Median range | p90 |
|---|--:|--:|
| NY AM 08:00–12:00 | **0.572** | 1.048 |
| London 02:00–08:00 | 0.404 | 0.704 |
| Asia 18:05–02:00 | 0.377 | 0.683 |
| NY PM 12:00–17:00 | 0.310 | 0.640 |

NY AM offers 52% more room than Asia and 85% more than NY PM. Arm bursts where the
continuation actually exists — gate on `research_clock_policy` session plus a live
realised-range check, not on time alone.

---

## Patch 4 — do not let the session overlay silence New York

`research_clock_policy` sets New York weight to `0.0`. That is correct for the thing
it was derived from — **holding** exposure, where NY carried a −0.03 Sharpe over
11.7 years — but your bot does not hold, it enters and exits intraday. Those are
different measurements and the weight does not transfer.

Measured intraday trade quality by session (volatility breakout and its inverse,
0.35 ATR stop, 1.5 R target, costs charged, 2,992 trades each):

| Session | Mode | Win% | Expectancy | PF | IS | OOS |
|---|---|--:|--:|--:|--:|--:|
| NY AM | fade | 47.3% | −0.026 R | 0.93 | −0.062 | **+0.027** |
| London | fade | 47.1% | −0.030 R | 0.87 | −0.026 | −0.036 |
| NY PM | fade | 48.3% | −0.034 R | 0.85 | −0.052 | −0.007 |
| Asia | breakout | 47.0% | −0.043 R | 0.81 | −0.075 | +0.005 |
| NY AM | breakout | 44.1% | −0.061 R | 0.85 | −0.055 | −0.069 |

Two things to take from this. First, **NY AM is the best intraday cell, not the
worst** — the opposite of what the exposure weight implies. Second, every cell is
still negative and the IS/OOS signs disagree, so none of this is a strategy; it is
evidence about *where* to look.

There is also a genuine structural hint: Asia is the only session where breakout
beats fade, and NY/London both prefer fade. That matches the drift result — Asia
trends, New York chops — and it is the right shape for an engine selector.

**Recommendation:** keep `researchClockPolicyMode=SHADOW`. When you do promote it,
apply the session weight to **risk sizing only**, never as an entry on/off switch,
and derive a *separate* intraday weight from your own broker's fills rather than
reusing the exposure weight.
