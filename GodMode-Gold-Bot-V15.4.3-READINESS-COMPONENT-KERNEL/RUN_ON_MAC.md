# Run GodMode on a Mac (iMac / MacBook)

## One-click start
1. Unzip the **Mac** download anywhere (e.g. your Desktop).
2. **Double-click `START_HERE_MAC.command`.**
   - The first time, macOS may say *"cannot be opened because it is from an unidentified developer."*
     Fix it once: **right-click the file → Open → Open**. (Or System Settings → Privacy & Security →
     "Open Anyway".) After that, a normal double-click works.
3. A Terminal window opens, sets things up the first time (1-2 min), and your browser opens the
   dashboard at **http://127.0.0.1:8000**.
4. Keep that Terminal window open while you use the bot. Closing it stops the bot.

That's the whole setup - no npm, no build step (the dashboard is pre-built).

## Requirements
- **Python 3** (macOS doesn't always include it). If the launcher says Python is missing, install it
  from the App Store or https://www.python.org/downloads/macos/ (or `brew install python`), then
  double-click the launcher again. The launcher checks the common Homebrew and python.org locations
  automatically.

## If the first run looks like it failed
The launcher is built to *not* give up:
- It tries the full `requirements.txt` first (identical to Windows). If that hits a snag — almost
  always the **optional** `matplotlib` on the very newest Python — it automatically installs just the
  **core** packages the bot needs and continues. `matplotlib` only adds Telegram chart *images*; the
  bot runs fine without it.
- It self-heals the common Mac gotchas: it makes the `.command` files executable and clears the
  download "quarantine" flag, so the other launchers work on the next click.
- If it still can't install the core packages, it's almost always **no internet** — connect and
  re-run. The window stays open and prints the exact error.

## IMPORTANT - live MT5 trading is Windows-only
MetaTrader 5's automation API (the `MetaTrader5` Python package) **only runs on Windows**. On a Mac the
launcher installs everything else and the dashboard runs in **demo mode** - you get the full UI,
analytics, backtests, Strategy Lab, journal, charts and Telegram, but it **cannot place live MT5
trades from the Mac itself.** You have three good options:

1. **Best for most people - run the bot on a Windows PC/VPS, view it on the Mac.**
   Run the Windows zip on a Windows machine (or a cheap Windows VPS that stays on 24/5), then open the
   dashboard on your iMac from anywhere using the secure remote access (Settings → 13. Mobile &
   Remote Access + Tailscale - see `MOBILE_REMOTE_ACCESS.md`). MT5 + the bot live on Windows; your
   Mac is just the screen.
2. **Windows inside your Mac.** Run Windows via Parallels Desktop / VMware Fusion (Apple-Silicon Macs
   run Windows on ARM) or CrossOver, install MT5 + the Windows zip there.
3. **Mac for analysis only.** Use the Mac launcher to explore the dashboard, backtests and Strategy
   Lab on demo/synthetic data, while a separate Windows machine does the live trading.

## Mobile / same-Wi-Fi from the Mac
Double-click **`start_backend_mobile_mac.command`** instead - it prints your Mac's IP and lets you set
an access key, then you open `http://YOUR-MAC-IP:8000` on your phone. Full steps in
`MOBILE_REMOTE_ACCESS.md`.

## Stopping / restarting
- **Stop:** close the Terminal window (or press `Control-C` in it).
- **Restart:** double-click `START_HERE_MAC.command` again (subsequent starts are instant).
