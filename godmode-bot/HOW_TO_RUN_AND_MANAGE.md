# GodMode Gold Bot — How to Run & Manage It

A plain-English guide to starting the bot, driving it day to day, and keeping it healthy — on
**Windows** and **macOS (iMac/MacBook)**.

---

## 1. Start the bot (one click)

### Windows
1. Double-click **`start_all.bat`**.
   - It installs the Python requirements (first run only), starts the backend, and serves the
     dashboard.
2. Your browser opens **http://127.0.0.1:8000** automatically. Leave the black command window open
   while you use the bot; closing it stops the bot.

### macOS (iMac / MacBook)
1. Double-click **`START_HERE_MAC.command`**.
   - **First run only:** if macOS says *"unidentified developer"* or *"cannot be opened"*,
     **right-click the file → Open → Open**. You only do this once.
   - It finds Python 3, creates an isolated environment, installs the requirements (1–2 min the
     first time), and launches — exactly like `start_all.bat` does on Windows.
2. Your browser opens **http://127.0.0.1:8000**. Leave the Terminal window open while you use the
   bot; closing it stops the bot.

> **No Python?** The Mac launcher tells you where to get it (python.org or `brew install python`).
> The optional `matplotlib` package (Telegram chart images) is installed best-effort — if it can't
> install on the newest Python, the bot still runs and everything else works.

---

## 2. Connect MetaTrader 5

> MT5's Python bridge runs on **Windows only**. On macOS the dashboard, analytics, backtester,
> Strategy Lab and Telegram alerts all run; live MT5 trade execution needs Windows (or a Windows VM
> / Parallels). On Mac without MT5 the app shows realistic demo data so you can learn every screen.

1. Open MT5 and log in to your broker (demo or live).
2. In the dashboard go to **Settings → 2. MT5 Connection → "Auto-detect Running MT5"** (or enter
   login/server/password and **Connect MT5**).
3. The top bar shows **MT5: Connected** and **Market: OPEN/CLOSED** when it's working.

---

## 3. Turn trading on (the safety ladder)

Live orders require **all** of these — by design, so nothing fires by accident:

1. **MT5 connected** (Settings → 2).
2. **Live Trading** ON (Settings → 3. Execution Control). *Leave it OFF to paper-trade in Dry Run.*
3. **Auto Trading** ON (Settings → 3).
4. **Kill switch clear** and (if enabled) **AI approval**.

Start in **Dry Run** for a few days, watch the **AI Agent** page to see *why* it takes or skips
each setup, then enable Live Trading only when you're satisfied.

---

## 4. Day-to-day management

| Page | What you do there |
|------|-------------------|
| **Dashboard** | Live signal, market-open/closed banner, why-this-trade confluence, MT5 chart. |
| **AI Agent** | Live, rules-based read of the market. The **"Why the AI is NOT trading yet"** card shows the exact blocking reasons (confluence, cost discipline, chop, spread). |
| **Trades** | Active/pending/closed trades, manual trade trigger (live-gated), **Export CSV**. |
| **Analytics → Overview** | Equity curve, **Returns Calendar** (click any day for what the AI detected + the best optimisation for the next day), top strategies, sessions. |
| **Analytics → Backtest** | **Run Backtest** and **Validate My Edge** (GO / CAUTION / NO-GO over ~2 yrs of your real MT5 history). Runs in the background — results stay even if you switch tabs or reload. |
| **Analytics → Strategy Lab** | Tests candidate trading *styles* on your own data and recommends an upgrade only if it beats your current config out-of-sample. Nothing applies until you click **Install** (and **Uninstall & revert** restores your previous settings). |
| **Journal** | Auto-filled from MT5 trade history; add your own notes with **New Journal Entry**; filter by date/outcome/strategy and **Search**. |
| **Settings** | MT5, execution, **AI strictness + per-mode confluence**, risk, alerts, data feeds, mobile access. |

---

## 5. Tuning the AI (Settings → 4. AI Strictness)

- **Strict Mode**: Relaxed → Balanced → Strict → Sniper (fewer, higher-quality trades as you go up).
- **Min Confluence per mode** (NEW): how many of the 12 live factors must agree before a trade is
  allowed, set independently for each mode. Defaults: Relaxed 2 · Balanced 3 · Strict 4 · Sniper 5.
  Higher = fewer but cleaner trades.
- **Range awareness / Cost discipline**: leave ON. They stop the two losing behaviours — buying the
  top / selling the bottom of a chop range, and taking trades where the spread is too big a fraction
  of the expected move.

**Golden rule:** change one thing, then **Backtest / Validate** before trusting it live.

---

## 6. Alerts & remote control

- **Telegram** (Settings → 7): get open/close alerts, daily/weekly recaps, and optional chart
  images. Works on any platform.
- **Phone, same Wi-Fi:** run `start_backend_mobile.bat` (Win) / `start_backend_mobile_mac.command`
  (Mac), then open `http://YOUR-PC-IP:8000` on your phone (the launcher prints the IP).
- **Phone, anywhere:** install free **Tailscale** on the PC and phone, open
  `http://<PC-Tailscale-IP>:8000`. Secure it with an access key (Settings → 13). Full steps in
  `MOBILE_REMOTE_ACCESS.md`.

---

## 7. Stop / restart / update

- **Stop:** close the command/Terminal window (or press `Ctrl+C` in it).
- **Restart:** double-click the start file again. Your settings persist (saved in
  `backend/data/settings.json`).
- **Re-install requirements:** delete the `.venv` folder (Mac) and re-launch, or re-run
  `python -m pip install -r backend/requirements.txt`.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Mac won't open the file | Right-click → **Open** → **Open** (clears Gatekeeper, once). |
| "Python 3 not found" (Mac) | Install from python.org, then double-click the launcher again. |
| Install seems to fail on Mac | It auto-falls back to the core packages and still starts; `matplotlib` is optional. |
| MT5 not connecting | Make sure MT5 is open and logged in; use **Auto-detect Running MT5**. |
| Bot won't trade | Check the **AI Agent → "Why the AI is NOT trading yet"** card — it tells you the exact gate. Also confirm the safety ladder in §3 and that the **Market** chip says OPEN. |
| Dashboard not loading | Make sure the start window is still open; reopen `http://127.0.0.1:8000`. |

> Educational tool. Trade responsibly; validate your edge before risking real money.
