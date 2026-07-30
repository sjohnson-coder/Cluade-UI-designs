# GodMode Gold Trading Bot — NPM / Startup Code Audit Fix

## What was checked

- Frontend package.json and package-lock.json
- npm clean install using `npm ci`
- frontend TypeScript/Vite production build
- backend Python compile
- backend FastAPI route smoke tests
- frontend-to-backend API default routing
- static dashboard serving from backend
- Windows batch startup files

## Findings

The frontend code builds correctly. The `npm error Exit handler never called!` seen on Windows is normally an npm internal/cache/process issue rather than a TypeScript or React code error.

However, the previous startup flow depended on running `npm install` before the dashboard opened. That made startup fragile on Windows machines with a corrupted npm cache or unstable npm version.

## Fixes added

1. Backend now serves the already-built dashboard from `frontend/dist`.
2. New no-npm launcher added: `1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`.
3. API default now uses the current browser origin, so the built UI can talk to the backend without extra `.env` setup.
4. Vite dev server now proxies `/api` to `http://127.0.0.1:8000` when using frontend dev mode.
5. `start_all.bat` now opens the dashboard through the backend server.
6. `start_frontend.bat` now uses `npm ci` first instead of plain `npm install`.
7. Extra npm repair launcher added: `FIX_NPM_AND_START_DEV_FRONTEND.bat`.

## Verified

- Backend Python compile: PASS
- Frontend production build: PASS
- Clean npm ci test: PASS
- npm audit high severity: PASS, 0 vulnerabilities
- Backend static dashboard serve: PASS
- API route smoke test: PASS
- SPA fallback route: PASS

## Recommended run method

Double-click:

`1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`

Then open:

`http://127.0.0.1:8000`

This does not require npm install for previewing/running the dashboard.
