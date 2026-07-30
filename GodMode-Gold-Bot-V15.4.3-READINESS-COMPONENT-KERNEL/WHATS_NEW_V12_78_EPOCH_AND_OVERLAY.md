# GodMode Gold Bot V12.78 — Old Trades Finally Gone + The UI Tells You The Truth Itself

## 1. Why old trades STILL showed after V12.76/77 (my bug, now fixed)

The auto data-epoch only fired when a previous version *marker* existed — but no old version
ever wrote one, so the first boot of the new engine took the "fresh install" path and skipped
the stamp. Result: the 365-day broker pull adopted every prior version's trades again
(your Analytics "200 trades / equity from June 25" screenshot).

**Fixed:** the epoch now also stamps on FIRST boot. A genuinely fresh account has no
bot-tagged deals, so it's a no-op for them; upgraders finally start clean. A manual purge you
already did is never overridden. Same-version reboots never move the cutoff.
Opt out with `GODMODE_KEEP_HISTORY_ON_UPGRADE=1` before first start.

## 2. The dashboard itself now announces when it's out of date

Instead of relying on changelogs: the backend injects, at serve time, into the OLD bundle's
own HTML (outside the React root, so the old app can't hide it):
- a fixed top banner when the bundle is stale, with the exact rebuild command, dismissible;
- a floating **⚙ Tools** button (bottom-right) linking to `/tools` on every page.
Once you rebuild, the banner disappears automatically.

## 3. /tools got real intelligence views

`http://127.0.0.1:8000/tools` now also renders live (no build needed):
- **Strategy Ranking** — rank score, PROVEN/LEARNING/UNPROVEN, live trades, live vs catalog
  win rate, execution timeframe, which strategy is picked this bar;
- **Why the bot skipped setups** — fire rate + top skip reasons from the decision journal;
- **AI Coach diagnosis** — the current plain-English coaching lines;
- **AI Entry-Audit scoreboard** — approve/downgrade win rates and veto count.
Plus the existing Purge buttons, CSV/PDF journal export and diagnostics links.

## 4. Settings resetting after every upgrade — the missing workflow

Every new zip is a fresh folder with default settings: MT5 login, feed URLs, Telegram, risk —
all gone. That is a big part of "everything keeps reverting."
New **`UPGRADE_HELPER_COPY_MY_SETTINGS.bat`** in the project root: run it in the NEW folder,
point it at the OLD folder, and it carries over settings.json, the decision journal, execution
memory, AI coach state, strategy memory and trade context — while deliberately NOT carrying
the version marker or epoch (the new engine still counts only its own trades).

## Validation
First boot stamps epoch and hides a July-8 trade; same-version reboot keeps it; a manual
purge is respected. Overlay HTML verified: banner + Tools button injected once, original
bundle script intact, no brace/escape pollution. /tools renders ranking, skip reasons,
coach diagnosis, scoreboard. Full V12.67–78 regression green (secret-safe save, feeds wiring,
import incl. aiAuditor, signals guarantee, M5 timeframe, journal rows). py_compile clean.
