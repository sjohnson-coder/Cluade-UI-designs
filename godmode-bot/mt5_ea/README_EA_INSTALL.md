# GodModeTickGuard — tick-level stop EA (sub-second management)

The Python bot manages trades on a ~3-second poll loop because the MetaTrader5
**Python** API is pull-based. This Expert Advisor runs *inside* MT5 and reacts on
**every tick** to do the fast, safety-critical work — break-even, ATR trailing, and a
hard protective floor — with sub-second latency. The Python AI keeps making the
intelligent decisions (entries, strategy, the recovery hold/cut verdict) and can
optionally steer the EA through a tiny control file.

It only touches positions stamped with your GodMode **magic number** or **comment
prefix**, so it will not interfere with manual or other trades.

## Install (2 minutes)
1. In MT5: **File → Open Data Folder** → `MQL5\Experts\`.
2. Copy `GodModeTickGuard.mq5` into that `Experts` folder.
3. In MT5 open **MetaEditor** (F4) → it appears in the Navigator → **Compile** (F7).
   It should compile with 0 errors.
4. Back in MT5, open **one XAUUSD chart** and drag **GodModeTickGuard** onto it.
5. On the **Common** tab tick **Allow Algo Trading**, and make sure the toolbar
   **Algo Trading** button is green.
6. On the **Inputs** tab set `MagicNumber` and `CommentPrefix` to EXACTLY match the
   bot (defaults: `20250525` and `GODMODE_`). Adjust BE/trail/floor to taste.

That's it — attach it once. It manages all GodMode positions across symbols.

## What each input does
- **Break-even**: once profit ≥ `BreakEvenAtR`, SL jumps to entry ± `BreakEvenBufferPts`.
- **Trailing**: once profit ≥ `TrailStartR`, SL trails `ATR × TrailATRMultiplier` behind price (tightens only).
- **Hard protective floor**: if loss reaches `HardFloorR` (e.g. −1.0R) it closes instantly — the sub-second safety net the 3s Python loop can't guarantee.
- **AI control bridge** (optional): reads `godmode_control.csv` for `HOLD`/`CUT` directives from the Python AI (see below).

## Hybrid with the Python AI (optional but recommended)
The AI Recovery Monitor decides whether an underwater trade is likely to **recover**
or is **invalidated**. To let that intelligence drive the EA at tick speed:

1. Find your terminal's files folder: **File → Open Data Folder → `MQL5\Files\`**.
2. In the GodMode app: **Settings → 5e → MQL5 control-file path**, paste that full
   `...\MQL5\Files` path and Save. (Leave `ControlFileCommon=false` in the EA.)
3. The bot writes `godmode_control.csv` (lines: `ticket,HOLD|CUT`). The EA reads it
   every second:
   - **HOLD** → the EA skips its hard floor so a recovering trade isn't cut early
     (the Python side holds its wider, **risk-capped** stop).
   - **CUT** → the EA closes the position on the very next tick.

If you don't set the path, the EA still runs fully autonomously (BE / trail / floor) —
the bridge is purely additive.

## Division of labour
| Job | Runs in | Cadence |
|---|---|---|
| Entries, strategy selection, confidence, HTF bias | Python bot | ~3 s |
| Recovery hold/cut verdict, dynamic (capped) SL | Python bot | ~3 s |
| Break-even, ATR trailing, hard floor | **this EA** | **every tick** |
| Enforce AI HOLD/CUT | this EA (via control file) | ~1 s |

## Safety notes
- The EA never *widens* a stop on its own — BE/trail only tighten. Only an explicit,
  already risk-capped AI SL can widen, and only if you enable the control bridge.
- Set `HardFloorR` no looser than your real per-trade risk tolerance; it is your
  instant catastrophe stop.
- Keep the Python bot's own break-even/trailing **on** as well — they are harmless
  duplicates; whichever tightens first wins, and the EA is simply faster.
