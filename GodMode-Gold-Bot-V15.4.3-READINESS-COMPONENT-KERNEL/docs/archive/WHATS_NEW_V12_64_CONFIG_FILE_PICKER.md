# V12.64 — Config File Picker Upgrade

This build improves the Settings import/export workflow.

## Fixed

- **Import Config JSON** now opens the native file picker instead of asking you to paste JSON into a prompt.
- Only `.json` files are accepted.
- The selected config is parsed locally in the browser, then sent to the backend import endpoint.
- Import still creates the normal rollback snapshot before applying the new configuration.

## Improved

- **Export Config** now attempts to open the browser's native save-file dialog when supported.
- If the browser does not support a save-file dialog, it falls back to the normal download flow.
- Exported files now use a date-based filename like `godmode_config_2026-07-07.json`.

## Safety

- Secrets are still excluded by default from exported configs.
- Invalid files are rejected before import.
- Existing rollback behaviour is unchanged.
