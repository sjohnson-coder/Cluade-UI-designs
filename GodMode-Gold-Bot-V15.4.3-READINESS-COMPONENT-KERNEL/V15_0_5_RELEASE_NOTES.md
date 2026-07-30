# GodMode Gold Bot V15.0.5 Operational Controls Fix

## Fixed controls and execution paths

- Validation Lock now persists immediately through one atomic endpoint and updates both `validation.enabled` and `execution.validationLockEnabled` together.
- Live and Auto controls preserve settings-revision concurrency and return the real authoritative blockers instead of optimistic UI-only success.
- Manual and automatic first entry are no longer deadlocked by an uninitialised protection heartbeat while the account is flat.
- Open positions still require a fresh healthy protection heartbeat before another entry is admitted.
- Frontend order mutations refresh backend readiness instead of permanently trusting the initial offline browser state.
- The deployed frontend bundle now matches the V15.0.5 source instead of retaining stale V14/V15.0.3 controls and identity.

## Telegram reliability

- Send Test and Test Recap now require a genuine Telegram Bot API `{ok: true}` response; HTTP 200 with `{ok: false}` is treated as failure.
- Markdown entity errors retry once as plain text so a formatting error does not silently lose an alert.
- Failed sends no longer poison the duplicate-message cache, allowing an immediate legitimate retry.
- Requested WAIT forecasts report failure truthfully and only start their cooldown after successful delivery.
- Scheduled daily and weekly recaps are marked delivered only after Telegram confirms the send.
- Saving Telegram credentials no longer claims they were verified; Send Test performs the actual delivery check.
- Test Recap only requests a WAIT forecast when that feature is enabled.

## Reference typography

- Inter is used for body copy and Archivo for headings, display text and dashboard chrome, matching the attached reference package.
- The release imports the font families at runtime and contains no redistributed font binaries.

## Release and hidden-integrity fixes

- Active launcher, installer, Tick Guard, backend and frontend identities are aligned to `V15.0.5-OPERATIONAL-CONTROLS-FIX`.
- Launcher settings self-tests advance the settings revision after every atomic write, avoiding a revision race.
- V15 overview reporting overwrites stale persisted release identity with the running build.
- Readiness now requires the validation gate to pass when validation locking is enabled.
- The release verifier now checks the complete manifest inventory, hashes, sizes, missing files, unexpected files, active installer identities and deployed asset identity.

## Safety boundary

Backend admission, Tick Guard, broker reconciliation, pre-live restrictions, risk lockouts, live certification and exact-build checks remain authoritative. Switching Validation Lock off does not bypass broker, account, risk, reconciliation, protection or build-safety gates.
