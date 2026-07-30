# GodMode Gold Bot V14.1.8 — Enterprise Consolidated

This release uses V14.1.4 as the stable baseline and selectively integrates the safe
part of the V14.1.5 defaults refactor. Safety-critical trade-management defaults now
come from one audited module, while the runner-aware 0.30 profit-lock policy is retained.
No numeric value-matching migration is included, so deliberate user settings are not
silently overwritten.

Additional hardening:
- consistent V14.1.8 identity across backend, frontend, bundle, Tick Guard and verifier;
- visible installer warnings instead of pass-only exception handlers;
- clean release packaging and regenerated checksums;
- live and auto trading remain disabled by default;
- Tick Guard EX5 still requires compilation in the target MetaEditor.
