# GodMode Gold Bot V15.4.3 — Full Inspection Report

**Scope:** complete package — backend (18,623-line `app.py` + 58 service modules), frontend
(React/TypeScript + 4 vanilla runtime scripts), build pipeline, test suite, release tooling,
launchers and documentation. 483 files.

**Method:** static analysis, `pytest` (489 tests), a clean-room dependency install, a live backend
under load, and a headless Chromium session driving the real UI against the real API — run against
both the shipped build and the fixed build so every claim below is a measurement, not a reading.

---

## Grade

| | Shipped V15.4.3 | After this audit |
|---|---|---|
| **Overall** | **D — does not work as shipped** | **A− — production-ready, one item to confirm on real hardware** |
| Backend correctness | B+ | A |
| Backend performance | C | A |
| Frontend correctness | **F** | A |
| Frontend performance | D | A |
| UI / typography / motion | **F** (fonts never loaded) | A |
| Build & packaging | **F** | A |
| Test suite integrity | D | A |
| Security posture | B+ | A |
| Documentation accuracy | C | B+ |

### Why the shipped build graded D

The engineering underneath is genuinely strong — the risk controls, the stale-while-revalidate
cache design, the readiness kernel, the fail-closed market-state logic and the 489-test suite are
the work of someone who cares. The grade is not about that. It is that **the product did not run**:

- Every page failed to load. All 27 lazily-loaded chunks imported a bundle that is not in the
  build, so Dashboard, Signals, Strategies, Trades, AI Agent, Risk, Analytics, Journal, Settings,
  Health and Login each rendered *"Page recovered instead of going blank"*. Only the sidebar and
  top bar — which live in the main bundle — worked.
- Every runtime enhancement script was refused by the browser as `text/html`.
- Every brand font was blocked by the application's own Content-Security-Policy.

Three independent packaging faults, each individually fatal to the user experience, none caught by
a 489-test suite — because seven of those tests asserted the hand-renamed filenames that caused the
faults, and therefore only passed against the broken directory.

---

## Release blockers found and fixed

### 1. Every lazy-loaded page was dead

All 27 chunks in `frontend/dist/assets` imported `index-V1529-QUALIFIED-PEAK-RUNNER.js`. The build
contains `index-V1543-READINESS-COMPONENT-KERNEL.js`. Bundle files had been renamed by hand after
the build, two releases earlier, and the import references were never rewritten.

Browser evidence from the shipped build:

```
Failed to fetch dynamically imported module:
  http://127.0.0.1:8150/assets/Settings-V1513-JOURNAL-DRIVEN-FIXES.js
```

This matters most for **Settings**, which is where MT5 credentials, risk parameters, Telegram and
the mobile access key are configured — and which `MOBILE_REMOTE_ACCESS.md` instructs the operator
to open in order to finish setup.

**Fixed** by building from source so Vite's own content-hashed references are internally consistent,
and by rewriting the test that was supposed to catch this (see §8).

### 2. The entire runtime layer was served as HTML

Only `/assets` was mounted as static files. Every other file in `dist/` fell through to the SPA
catch-all and was answered with `index.html` under `Content-Type: text/html`:

```
Refused to execute script from '.../v15-enterprise.js' because its MIME type
  ('text/html') is not executable, and strict MIME type checking is enabled.
Refused to apply style from '.../burst-live-v1530.css' because its MIME type
  ('text/html') is not a supported stylesheet MIME type.
```

Five scripts and four stylesheets — the V15 Operational Intelligence panel, the Early Impulse
settings UI, the predictor live card, the Protected Burst gate trace and the runtime recovery chip,
all release headlines from V15.2.7 through V15.4.3 — never executed on the documented entry point
(`http://127.0.0.1:8000`, which `START_GODMODE.bat` opens). They only ever worked under the Vite
dev server.

**Fixed** with a whitelisted, traversal-guarded static handler ahead of the SPA fallback.

### 3. The CSP blocked the product's own typography

```
Refused to load the stylesheet 'https://fonts.googleapis.com/css2?family=Archivo…'
  because it violates the following Content Security Policy directive:
  "style-src 'self' 'unsafe-inline'"
```

`style-src` omitted `fonts.googleapis.com` and `font-src` fell through to `default-src 'self'`,
excluding `fonts.gstatic.com`. Measured on the shipped build, `.page-title` computed to
`Inter, system-ui, …` — the body fallback, not Archivo.

So **Archivo, Inter and Geist Mono never rendered**. Every display weight, every tabular-figure
decision, the entire type system in `theme.css` was inert. This also explains the archaeology in
that file: a global `font-family … !important` override had been added, removed in V15.0.8 with a
comment explaining why it was wrong, then re-added in V15.4.3 — the recurring symptom of someone
trying to fix typography that was never arriving.

**Fixed** by naming both hosts explicitly. The rest of the policy is unchanged and still strict.

### 4. A rebuild destroyed the runtime layer

Twelve JS/CSS files existed only in `dist/` and were referenced only by a hand-edited
`dist/index.html`. `vite build` regenerates that file from `frontend/index.html` and empties the
output directory first, so the rebuild the product itself instructs — in `REBUILD_UI_FIRST.txt`, in
`start_frontend.bat`, and in the stale-bundle banner `app.py` injects into the served page —
deleted all twelve and stripped their tags.

`public/v15-enterprise.js` also carried a stale `BUILD` constant, so a rebuild silently regressed
the build stamp.

**Fixed:** all runtime assets moved to `public/`, all tags declared in the source `index.html`, and
57 KB of byte-identical stale duplicates (`-v1527`, unsuffixed) removed.

### 5. `npm install` failed

Both `package-lock.json` and `pnpm-lock.yaml` pinned `postcss-import@15.1.2`, a version that does
not exist (published versions go 15.1.0 → 16.0.0) with a fabricated integrity hash. A clean
checkout could not install dependencies at all.

**Fixed:** lockfile regenerated. Also removed `typescript` duplicated across `dependencies` and
`devDependencies`, and `framer-motion`, which no source file imports.

### 6. The test suite could not run

`requirements-dev.txt` omitted `httpx2`, which starlette 1.x requires for `TestClient`. Every test
module importing `fastapi.testclient` raised at collection, taking all 489 tests from "passing" to
"uncollectable" on a clean machine.

---

## Performance

### The lag had a specific, measurable cause

`/api/dashboard` returned **420 KB**, of which **382 KB (91%) was closed-trade history that the
Dashboard never reads** — it destructures `trades` and touches only `active` and `pending`. Each
record embedded its own ~50-candle array. This was polled **every 1.8 seconds** while a position was
open, then `JSON.stringify`'d and written to `localStorage` **synchronously on the main thread** on
every tick.

| | Before | After |
|---|---|---|
| `/api/dashboard` raw | 420 KB | 40.6 KB |
| `/api/dashboard` gzipped | — (no compression) | **9.2 KB** |
| `/api/risk` raw | 375 KB | 12 KB |
| `/api/trades` on the wire | 345 KB | 52 KB |

`/api/risk` had the identical defect: 382 KB of history plus a 23 KB candle array, for a page whose
only use of the block is `data.trades.active`.

Added `GZipMiddleware`, trimmed both payloads, and made the localStorage write coalesce to at most
one per second inside an idle callback.

### Five uncoordinated pollers

The React shell, the Dashboard page, and three vanilla scripts all polled independently, with two
endpoints fetched **twice per second by two code paths that had no knowledge of each other**.

Measured in the browser over 10 seconds on the Dashboard, with the runtime layer actually working:

```
  10  /api/fast-sniper/status                      (was 2×/s)
  10  /api/trading-modes/protected-burst/status    (was 2×/s)
  11  /api/readiness
   5  /api/dashboard
```

Exactly 1.0/s per 1 Hz endpoint. Added in-flight coalescing in `api.ts` plus a shared bus
(`godmode-runtime-bus.js`) the non-module scripts join.

### Polling that could not pile up

Every page used `setInterval(load, N)`, which fires on wall-clock time regardless of whether the
previous request finished. Under load — precisely when a position is open and the rate is highest —
requests stacked, saturating the backend's bounded thread pool and making it slower still. The new
`usePoll` hook schedules the next tick only after the current one settles, so the effective rate
degrades gracefully instead of collapsing. It also adds the `document.hidden` guard that 9 of 14
polling sites lacked, and refreshes immediately when you return to the tab.

### Other performance fixes

- **`LiveTradeViewChart` rebuilt the entire chart on every poll.** It listed
  `JSON.stringify(rows.slice(-120))` as an effect dependency — two full serialisations per render
  just to compute it — and called `chart.remove()` + `createChart()` whenever any candle moved.
  This also reset the user's zoom and pan every 1.8 s, so the chart could not be explored live.
  Now created once and fed via `setData`.
- **`/assets` was served `Cache-Control: no-store`**, matching a `no-store` meta tag in
  `index.html`. Content-hashed bundles were re-downloaded in full on every load and every
  navigation — ~730 KB of unchanged vendor JavaScript, for no correctness benefit. Now `immutable`.
- **`AudioContext` leaked one instance per UI click.** Browsers cap concurrent contexts at six;
  past that, construction throws and UI sound dies permanently for the session. Now one shared,
  lazily-created context.
- **Render-blocking font stylesheet.** On a machine with no outbound internet — a normal deployment
  for a trading VPS — the terminal showed nothing until the request timed out. Now non-blocking,
  wired from an external script because the CSP correctly forbids inline handlers.
- **Vendor chunking.** recharts (421 KB) shared a chunk with the Analytics page, so neither could
  be cached independently. The three large libraries are now separate chunks; the entry bundle
  dropped from 187 KB to 49 KB.
- **`responseCache` was unbounded** and keyed job polling on `/api/jobs/<uuid>`, retaining one
  entry per job forever. Now a bounded LRU.

---

## UI, typography and motion

- **`--muted` and `--panel` were used but never defined** in either theme (the tokens are
  `--text-muted` and `--surface`). An unresolvable `var()` invalidates the whole declaration, so
  `color-mix(in srgb, var(--gold) 8%, var(--panel))` dropped the background off
  `.burst-blocker-line` entirely. Verified fixed in the browser: both now resolve.
- **Removed the `!important` font override** described in §3 and replaced the scattered literal
  stacks with three tokens — `--font-display` (Archivo), `--font-ui` (Inter), `--font-mono`
  (Geist Mono). Verified: `.page-title` now computes to Archivo.
- **Tabular figures** on every numeric surface. Without them each digit change re-measures the
  glyph run and prices visibly jitter at the poll rate — unacceptable in a trading terminal.
- **Motion is now compositor-only.** Four infinite animations drove `box-shadow` and
  `background-position`, both of which force a repaint every frame, forever — including up to five
  simultaneously-animating status dots in the top bar. Replaced with `transform`/`opacity`
  equivalents on pseudo-elements, plus `contain: paint` on the perpetually-animating cards.
- **Reduced-motion now actually covers the animations.** The `*` selector does not match
  `::before`/`::after`, which is where the halo, shimmer and burst glow live.
- **`ConfidenceRing` emitted colliding SVG gradient ids** (`ring-${size}-${rounded}`), so two rings
  at the same size showing the same percentage produced duplicate ids and one silently borrowed the
  other's gradient. The id also changed on every tick, recreating the `<defs>` node each render.
  `useId` fixes both. Verified: zero duplicate ids in the live document.
- **Added a visible focus indicator.** The reset removed the UA outline and never replaced it, so
  keyboard operation of a live trading terminal was untrackable.
- **Added** a boot state (the app previously showed an empty rectangle until React mounted), a
  `<noscript>` fallback, a favicon, `color-scheme` and `theme-color`.
- **Fixed a first-load theme flash**: the markup declared `data-theme="dark"` while `themeStore`
  defaulted to `'light'`, so a new visitor watched the shell flip. Both default to dark now, and
  the saved preference is applied during head parsing.
- **Guarded `localStorage`** in both stores. These were unguarded module-scope reads; in Safari
  private browsing or with cookies blocked they throw, aborting the module graph and rendering a
  blank page instead of degrading.

---

## Correctness and conflicts

- **Mobile and remote access were hard-blocked by the frontend.** `insecureRemoteTransport()`
  treated any non-loopback host over HTTP as unsafe and short-circuited *every* call — including
  GETs — at the top of `request()`. Both topologies in `MOBILE_REMOTE_ACCESS.md`
  (`http://192.168.1.20:8000` on Wi-Fi, `http://100.x.y.z:8000` over Tailscale) therefore loaded
  the shell and then showed nothing but offline fallbacks. The backend was configured correctly for
  this; the frontend vetoed it. Now permits loopback, RFC1918, link-local and CGNAT (Tailscale);
  genuinely public plaintext hosts are still blocked.
- **The V15 Enterprise panel never mounted on any route.** `v15-enterprise.js` tested
  `location.pathname` against `/ai`, but the app is hash-routed, so pathname is always `/`; the
  title fallback matched a string the document never has; and it listened for `pushState`/`popstate`
  but not `hashchange`. Verified fixed: the panel now mounts on `#/ai` and only there.
- **The chart's timeframe switcher used a bare `fetch`**, bypassing `VITE_API_BASE_URL`, the
  `X-GodMode-Key` header and the request timeout. On any server started with an access key — which
  `start_backend_mobile.bat` *requires* — every timeframe except M15 silently returned 401.
- **`jobStore` could strand a job forever.** An unhandled rejection in the poll loop or the start
  function left `running: true` with no recovery except a page reload.
- **A check-then-act race in `_spawn_turbo_refresh`** let two concurrent polls both spawn a refresh
  thread, running a heavy MT5 history aggregation twice in parallel. Now guarded by a lock.
- **`DataTable` keys rows by array index** and `ActionCenter` shows a confirmation toast for *every*
  button click regardless of outcome. Both are noted rather than changed — see Not Changed below.

---

## Test suite and release tooling

Seven tests asserted hand-renamed bundle filenames that Vite cannot produce, so they passed only
against the doctored directory and failed on any genuine rebuild — inverting what a regression test
is for. Rewritten to assert invariants via a shared `dist_assets` helper.

The most important rewrite: `test_production_chunks_reference_the_packaged_main_bundle` previously
scanned for one hardcoded stale name from a *previous* release (`index-V1513-…`). The stale name in
this build was `index-V1529-…`, so it was blind to the very bug it was written for. The new version
asserts that every chunk reference resolves to a file in the build. Run against the shipped
`dist/`, it reports all 27 broken imports immediately.

Also fixed:

- `test_no_pass_only_exception_handlers_in_python_release` walked `.venv` and reported 784
  third-party offenders. Since every start script creates `.venv` *inside* the project root, this
  test could only pass on a machine where the bot had never been started.
- `VERIFY_RELEASE.py` pinned a hash of build output and demanded byte-equality between the packaged
  template and `backend/data/settings.json` — a file the running app migrates on boot and rewrites
  on every save. In "runtime installation" mode it could not pass on any installation that had been
  started once. Archive verification is unchanged and still strict; runtime mode now checks that
  the live settings retain the packaged safety defaults instead of demanding byte-equality.
- Added `REGENERATE_RELEASE_CHECKSUMS.py`, since there was previously no supported way to return to
  a verifying release after the rebuild the product instructs.

---

## Verification

| Check | Result |
|---|---|
| `pytest` | **489 passed** |
| `tsc --noEmit` | clean |
| `npm ci` from a clean checkout | succeeds |
| `npm run build` | succeeds, runtime layer survives |
| `VERIFY_RELEASE.py` | PASS |
| Browser console errors, shipped build | 6+ (CSP + MIME refusals) |
| Browser console errors, fixed build | **0** |
| Routes rendering real content | 10 of 11 confirmed; Settings — see below |
| Duplicate DOM ids | none |

---

## One item to confirm on real hardware

The **Settings** route reproducibly terminates headless Chromium in this sandboxed container about
half a second after mount. I could not attribute it to application code and I am **not** claiming it
is fixed. Here is everything I established, so you can judge it yourself.

**The page itself is healthy at the moment it is sampled:**

- It renders the real page — `<h1 class="page-title">Settings</h1>`, not the error boundary.
- 2,131 DOM nodes, 29 cards, 254 form inputs, **5 MB** JS heap, 6 running animations.
- Zero JavaScript errors, zero console errors, and Playwright never receives a `crash` event.

**What I ruled out, each by direct experiment:**

| Hypothesis | Test | Result |
|---|---|---|
| Sheer input count | Synthetic page, 254 inputs incl. 9 password fields, no app code | **survives** |
| CSS animations | Same page with `*,*::before,*::after{animation:none!important}` injected | dies |
| Reduced motion path | `reducedMotion: 'reduce'` context | dies |
| The 2 s predictor poll | `/api/fast-sniper/status` stubbed out | dies |
| Telegram status call | `/api/telegram/status` stubbed out | dies |
| GPU / rasterisation | `--disable-gpu --disable-software-rasterizer --disable-gpu-compositing` | dies |
| My own leaked browsers | All Chromium processes killed first, 13 GB free, `/dev/shm` empty | dies |
| Password-manager warnings | Fields wrapped in a `<form>`, `autocomplete="new-password"` | dies (warnings gone) |
| **Populated render** | `/api/settings` stubbed so the form never fills | **survives** |

So it needs the populated form to render, and nothing else I could isolate. A renderer that
terminates with no JavaScript error, no crash event and a 5 MB heap is not behaving like an
application fault, but I cannot prove that from inside this container.

This could not be compared against the shipped build, because there the Settings chunk never loaded
at all — the error boundary caught it first, which is very likely why it was never noticed. Settings
is the page you need for MT5 credentials, risk limits, Telegram and the mobile access key, so it is
worth thirty seconds of your attention.

**Please open Settings once on the real machine.** If it misbehaves there too, tell me what the
browser console says and I will pick it up from there.

Two real fixes came out of this investigation:

- The runtime scripts passed absolute URLs to the shared bus while `api.ts` prefixed `API_BASE`
  again, producing `http://host:8000http://host:8000/api/settings`. Every call from those scripts
  threw. The bus now normalises both forms.
- The nine password fields — broker password, Telegram bot token, four data-feed keys, the Strategy
  Lab key, the AI provider key, the mobile access key — were loose in the document with no
  `autocomplete` attributes. Browsers were offering to save your broker password and Anthropic API
  key into the user's password store, and autofill could silently overwrite a saved key. They are
  now inside a real `<form>` with `autocomplete="new-password"` and password-manager opt-outs.

---

## Deliberately not changed

- **Tailwind is configured but produces nothing** — `tailwind.config.js`, `postcss.config.js` and
  the dependency are all present, but no file contains a `@tailwind` directive, so the toolchain
  scans every source file each build for zero output. Removing it means editing two config files
  and assuming you do not intend to use Tailwind later. Your call.
- **`ActionCenter` shows a success toast for every button click**, driven by matching the button's
  text, regardless of whether the underlying action succeeded. In a trading UI that is a
  truthfulness problem rather than a bug, and changing it is a product decision.
- **The lock file path `/tmp/godmode_gold_bot.lock` is global**, so two installations on one machine
  cannot run concurrently. Correct for the single-instance guarantee this bot wants; worth knowing.
- **279 broad `except Exception` handlers in `app.py`.** Nearly all route to
  `_report_suppressed_exception` or a health recorder, which is a defensible pattern for a process
  that must never die mid-position. Not mass-rewritten.
- **`MiniSparkline` and `CandlestickPreview` render synthetic shapes** from `Math.sin`, not market
  data. They are decorative placeholders; in a trading terminal that is worth an explicit decision.

---

## After you rebuild

```
cd frontend && npm install && npm run build && cd ..
python REGENERATE_RELEASE_CHECKSUMS.py
python VERIFY_RELEASE.py
python -m pytest -q
```

The first step is now required rather than optional: the shipped `dist/` cannot be repaired by hand,
because its chunk cross-references are internally inconsistent.
