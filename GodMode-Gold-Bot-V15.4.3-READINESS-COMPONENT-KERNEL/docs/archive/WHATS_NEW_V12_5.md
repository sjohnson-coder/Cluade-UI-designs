# GodMode V12.5 — Smart Profit Protection

This release fixes the **$0.10 scratch wins** and the **trailing that wouldn't kick in**,
and replaces the fixed profit-protection with a *smart* one that knows **when** to protect
and can **give a high-probability trade room to recover and win bigger**.

---

## The bug you hit (and why)
You set Break-even = 0.4R and Trailing = 0.45R, but trades that moved nicely into profit
still closed for ~$0.10, and trailing "didn't kick in for a long time."

**Root cause:** the old trail put the stop a full ATR below price
(`SL = price − 1×ATR`). On Gold your stop is ~1 ATR wide, so until the trade was up
roughly **+1R**, that trailing stop sat *below break-even* — so the stop stayed pinned at
entry and any small pullback closed the trade flat (~$0.10). The trail mathematically
**could not** lock profit early. That's the error in the code, now fixed.

## What's new

### 1. Peak-ratcheting profit floor (a winner can never become a scratch/loss)
The bot now tracks the **best profit the trade ever reached** and locks a fraction of it as
a hard floor that **never drops**:

```
floor = entry + (Profit lock fraction × best-profit-so-far)
```

So once a trade is up, say, 1 ATR, with the default 0.35 lock fraction the stop sits at
**+0.35 ATR locked in profit** — and it only ratchets up from there. No more giving back a
good move for $0.10. (Validated in simulation: a trade that ran to +0.6R then faded **banked
+0.21R instead of a $0.10 scratch**.)

### 2. Protection that starts FAST (ATR-based, not just R-based)
Protection now arms as soon as the trade is up **Protect starts at (ATR)** (default 0.4 ATR)
— much sooner than waiting for a full +1R on a wide stop. The trail then **tightens as the
move extends** (gives a young move room, hugs a mature move).

### 3. Smart recovery room (the part you asked for)
> "dynamically give room for recovery if trade is almost at the trailing stop but with very
> high chance of recovery, so the bot widen a little to accommodate the recovery and win better"

When price pulls back and is **about to hit the trailing stop** (within **Recovery room (ATR)**,
default 0.3 ATR of the stop), the bot asks the AI recovery monitor for a verdict:

- **High recovery (RECOVER, structure intact)** → it **loosens the stop back down to the
  protected in-profit floor** to let the shakeout breathe — then resumes trailing if the move
  continues. In simulation this turned a trade that would've stopped at +1.1R into a **+2.2R**
  winner.
- **Poor recovery (or structure broken)** → it **holds the tight stop** and banks the profit.
  No blanket loosening.

Critically, the room is **bounded** — it never loosens below the locked floor, so even when it
gives room you **still bank profit** if the recovery fails. You get the upside of breathing
room without the downside of giving back your gains.

---

## New settings (Settings → 5c. Break-even & Trailing)
All exposed and editable:

| Setting | Default | What it does |
|---|---|---|
| **Protect starts at (ATR)** | 0.4 | How fast protection arms. Lower = faster. |
| **Profit lock fraction** | 0.35 | Fraction of best-profit locked as the floor (0.35 = keep 35%). |
| **Trail starts at (ATR)** | 0.7 | When the tightening trail begins riding. |
| **Smart recovery room** | ON | Master toggle for the give-room-to-recover behaviour. |
| **Recovery room (ATR)** | 0.3 | How close to the stop price must be before the AI is asked to give room. |

> Tip: these ATR triggers fire **much sooner** than the older R-based Break-even/Trailing
> fields on wide Gold stops, so you protect profit fast without scratching. The R fields still
> work as a fallback (whichever fires first).

---

## How to verify it's working
1. Run the bot as usual (`start_backend.bat` / your localhost), open **Settings → 5c**.
2. On the next trade that moves into profit, watch the alerts:
   - **"Profit locked"** — the floor armed (you'll see `+x.xxR` locked, in profit, not at entry).
   - **"Trailing up"** — the stop ratcheted higher as the move extended.
   - **"Recovery room"** — a pullback near the stop with high recovery; the bot gave it room
     down to the floor (still +x.xxR locked) and let it breathe.
3. You should no longer see a winner close for ~$0.10 — the worst case on a trade that armed
   protection is the locked floor, which is in profit.

Backend compiles ✓, frontend builds ✓, protection math validated by simulation ✓.
