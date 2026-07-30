# Use GodMode on your phone (mobile & remote access)

The bot runs on your PC (next to MetaTrader 5). These are the two safe ways to open its dashboard on
your phone. **MT5 must stay running and logged in on the PC** — the phone is just a remote screen.

---

## Option A — Same Wi‑Fi (easiest, home only)
1. On the PC, run **`start_backend_mobile.bat`** (instead of the normal start script). It binds the
   server to your whole network and prints your PC's IPv4 address(es).
2. On your phone's browser (same Wi‑Fi), open: **`http://YOUR-PC-IP:8000`**
   (e.g. `http://192.168.1.20:8000`).
3. Done. The phone shows the live dashboard.

> Only works while the phone is on the same Wi‑Fi as the PC.

---

## Option B — From anywhere (mobile data / other networks) with Tailscale
This is the **safe** way to reach the bot over the internet — a private mesh VPN, with **no
port‑forwarding** and **nothing exposed publicly**. Do **not** port‑forward a trade‑executing app.

1. Make a free account at **tailscale.com**.
2. Install Tailscale on the **PC** and sign in. Note the PC's Tailscale IP (looks like `100.x.y.z`).
3. Install Tailscale on the **phone** and sign in with the **same account**.
4. On the PC, run **`start_backend_mobile.bat`**.
5. On the phone (any network), open: **`http://<PC-Tailscale-IP>:8000`** (e.g. `http://100.101.102.103:8000`).

Only devices signed into *your* Tailscale account can reach the bot.

---

## Secure it with an access key (do this for Option B, recommended for A)
The bot's control actions (start/stop, execute, save settings) can require a secret key.

1. **On the server:** `start_backend_mobile.bat` now asks for an **Access key** when it starts — enter
   a strong secret (or set the `GODMODE_API_KEY` environment variable). Leave blank only on trusted
   home Wi‑Fi.
2. **In the app:** open **Settings → 13. Mobile & Remote Access**, type the **same** key into "API
   access key (this device)", and press **Save key**. It's stored only in that browser/phone and is
   sent as the `X-GodMode-Key` header on every write.
3. Without a matching key, write actions return **401** (read‑only views still load). Enter the key on
   each device you want to control the bot from.

> The key check only applies to changes (POST/PUT/DELETE). Viewing the dashboard never needs it.

---

## Notes
- The phone UI is fully responsive (verified 360px → desktop).
- If the dashboard loads but buttons "do nothing", you set a `GODMODE_API_KEY` on the server but
  haven't entered the matching key in **Settings → Mobile & Remote Access** on that device.
- Keep MT5 running on the PC; if the PC sleeps, the bot stops. Set the PC to not sleep for 24/5 use.
- The bot already knows when the market is closed (weekend) and stands down — see V12.20.
