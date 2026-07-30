# GodMode Gold Bot V12.66 — Deep Conflict Fix

This build is a stability patch focused on the conflicts reported after V12.65:

## Fixed

1. **Settings not saving reliably**
   - Replaced direct `settings.json` writes with a locked, atomic temp-file + replace save.
   - Added a settings save audit file so failed saves are no longer silent.
   - Strips runtime-only UI keys such as `mt5`, `source`, `stale`, and `staleReason` before saving. This prevents live status objects from being written back into the persistent config.
   - Avoids nested double-save when changing execution mode from Settings.

2. **Rollback not working**
   - Every manual Settings save, AI fix, and Config Import now creates a rollback snapshot.
   - Rollback IDs now include milliseconds + a UUID suffix so snapshots created in the same second cannot overwrite each other.
   - The Settings rollback button now rolls back the last save / AI fix / import, not only AI fixes.
   - Config Import now records its rollback snapshot for the rollback button.

3. **Signals page going blank**
   - Added an app-level Error Boundary. A page crash now shows a recovery card instead of a white screen.
   - Signals page now normalises backend/stale responses. If `/api/signals` returns an object, cached error, stale response, or temporary non-array payload, it is ignored safely instead of crashing React.
   - Signals data and market snapshot now load together with guarded error handling.
   - The Execute Signal button no longer tries to execute a `WAIT`/blocked item.

4. **Config pollution conflict**
   - Previous saves could send the returned `settings.mt5` runtime status back into `/api/settings`. The backend would eventually persist it. That is now blocked.

## Validation performed

- `python -m py_compile backend/app.py services/*.py` passes.
- `npm run build` passes and rebuilt `frontend/dist`.
- Local API test confirms `/api/settings`, `/api/signals`, `/api/config/rollback-snapshots`, save, and rollback return valid responses.

## Recommended live launcher

Use:

`1_START_GODMODE_BOT_NO_NPM_REQUIRED.bat`

or:

`start_backend.bat`

Do not use the dev reload launcher for live trading.
