# Pixel-Match UI Patch Notes

This patch forces the newly added institutional feature sections to inherit the exact same GodMode dashboard component system instead of using a separate feature-section visual language.

## Changed

- Removed custom feature-card layout usage from the React components.
- New feature modules now use the same shared `Card`, `SectionTitle`, `Tag`, `Checklist`, `DataTable`, `ProgressBar`, and grid system as the original dashboard.
- Dashboard now starts with the same `PageHeader` and standard top command cards before showing the new backend feature cards.
- Pyramiding, trade-management intelligence, real feeds, macro intelligence, execution engine, replay/versioning, testing, memory, calibration, and guardrails now visually match the same dashboard card skin.
- The shell remains unchanged: same logo, sidebar, topbar, browser frame, theme toggle, sound toggle, spacing, colors, and responsiveness.

## Verified

- Frontend production build passed with `npm run build`.
- Backend Python compile passed with `python -m py_compile app.py services/*.py`.
- Live trading remains protected by dry-run mode unless `GODMODE_ENABLE_LIVE_TRADING=true`.
