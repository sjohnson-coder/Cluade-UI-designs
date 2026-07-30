# GodMode V12.13 — Trusted strategy feed + daily auto-run

Completes the Strategy Lab's three candidate sources (library + AI + **feed**) and lets the whole
thing **run itself daily**.

## 1) Trusted strategy feed (the safe "scout the internet")
**Settings → 12e. Strategy Lab — Feed & Schedule → Trusted feed URL** (+ optional key).
Point it at a source **you control** that returns a JSON array of candidate strategy profiles (same
shape as the built-in library). The bot pulls them into the candidate pool and back/forward-tests
them on your data like everything else.

- **Use it now:** Analytics → Strategy Lab → **📡 Fetch feed**.
- **Safety:** feed candidates pass through the **exact same whitelist + clamp** as the AI ones — even
  a compromised "trusted" URL can't inject code or out-of-range parameters (verified: a feed entry
  carrying `code: "danger()"` comes out as nothing but its clamped, whitelisted profile). They're
  tagged `source: feed`, and nothing installs without your click.

This is the honest version of "scout the internet for strategies": *you* choose the source, and
every candidate is proven on your data before it can ever be recommended.

## 2) Daily auto-run (the Lab runs itself)
**Settings → 12e → Auto-run lab daily** (+ **Auto-run hour (UTC)** + **Improvement margin (R)**).
When enabled and MT5 is connected, once a day at the set hour the bot automatically:
1. pulls your trusted feed,
2. re-tests **every** candidate (library + AI + feed) against your **latest** history,
3. and alerts you — notification + top-bar + **sound** + **Telegram** — **only if** a candidate beats
   your current config by at least the **Improvement margin** out-of-sample.

You just get a heads-up when there's a genuinely better strategy worth a click; otherwise it stays
quiet. The run happens in a background thread, so it never interrupts live trading, and it's deduped
so the same recommendation won't re-alert.

## Now the full self-improving loop is closed
**Candidate sources:** curated library + **AI generator (Claude/ChatGPT)** + **trusted feed URL**.
**Cadence:** on-demand button *or* daily on its own.
**Always:** proven on your data, out-of-sample gated, you approve before anything trades.

## API
`POST /api/lab/fetch-feed` · daily auto-run runs inside the existing scheduler loop.

## Validation
Backend compiles ✓ · frontend builds ✓ · new Settings card + Fetch-feed button verified responsive
on mobile in a real browser ✓ · smoke-tested end-to-end (defaults, graceful no-URL, routes
registered) ✓ · **9 simulation suites pass**, including an expanded generator/feed suite proving feed
candidates get the same safety sanitization (code stripped, values clamped, `source: feed`).
