# GodMode V12.21 — Mobile & remote access (secure), + range-strategy verdict

Two things from your last request: (1) reach the bot from your phone safely, and (2) the dedicated
range strategy.

## 1) Mobile & remote access
You can now control the bot from your phone — on your Wi‑Fi or from anywhere — with a real security
key, instead of an open port.

- **Settings → 13. Mobile & Remote Access**: enter an **API access key** (stored on that device). The
  UI now sends it as `X-GodMode-Key` on every write, so the dashboard works when the server is
  exposed — previously, turning the key on would have broken the UI.
- **`start_backend_mobile.bat`** now prompts for that access key at startup (sets `GODMODE_API_KEY`)
  and binds to your network. Same-Wi‑Fi: open `http://YOUR-PC-IP:8000` on the phone.
- **From anywhere:** a **Tailscale** tunnel (free, private, no port-forwarding) — open
  `http://<PC-Tailscale-IP>:8000`. Full step-by-step in **`MOBILE_REMOTE_ACCESS.md`**.

**Security model (verified):** reads (the dashboard) always load; **writes** (start/stop, execute,
save) require the matching key — without it they return **401**. So exposing the bot doesn't let a
stranger trade your account. Set a strong key for any internet/Tailscale access.

## 2) Dedicated range strategy — tested, and the answer is *don't*
I built a dedicated range mean-reversion strategy with proper range geometry (tight stop beyond the
edge, target the range mid) and backtested it with the real exit engine. **It loses decisively**
(−0.79 to −0.85R expectancy, 5–6% win rate, over 36k bars × 2 seeds) — the tight stop gets run over
because price at a range extreme is usually *breaking out*, not reverting. This is the inverse of the
**fresh-leg override (V12.18)**, which trades *with* the break and wins (+40–55%). Full evidence in
**`RANGE_STRATEGY_FINDINGS.md`**.

**Bottom line:** the "trade chop safely" goal is already met by the fresh-leg override; a range
reversion strategy would only lose money, so it is intentionally **not** added. (It can be wired as a
disabled, clearly-labelled experimental toggle if you want to test it on your own MT5 history.)

## Validation
Backend compiles · frontend builds · API-key enforcement verified (read 200, write 401 without key /
200 with it) · range-strategy backtest run on two seeds with the real `_simulate` engine.
