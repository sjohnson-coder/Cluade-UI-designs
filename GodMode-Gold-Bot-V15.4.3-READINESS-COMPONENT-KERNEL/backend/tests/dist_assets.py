"""Locate built frontend assets by role instead of by literal filename.

Seven tests in this suite asserted exact bundle names — `index-V1543-READINESS-COMPONENT-KERNEL.js`,
`Settings-V1513-JOURNAL-DRIVEN-FIXES.js`, `early-impulse-settings.js`. Vite does not and cannot
produce those names: it emits content-hashed filenames (`index-DpXGrFKT.js`), and the shipped dist
had been renamed by hand afterwards. The consequence was that the suite only passed against that
one hand-doctored directory, and running the rebuild the product itself instructs — REBUILD_UI_FIRST.txt,
start_frontend.bat, and the stale-bundle banner app.py injects into index.html all say to run
`npm run build` — turned seven green tests red with no defect involved.

This is the same failure mode the V14.1.17 note in test_v1416_consolidation.py already identified
for BUILD_ID string literals: assert the invariant, not an incidental spelling the build tool owns.
The helpers below resolve assets the way a browser does — by reading dist/index.html and following
its references — so they keep working across rebuilds while still failing loudly if an asset really
is missing.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
ASSETS = DIST / "assets"


def dist_index_html() -> str:
    return (DIST / "index.html").read_text(encoding="utf-8")


def main_bundle() -> Path:
    """The entry module dist/index.html loads, resolved through the document rather than guessed."""
    html = dist_index_html()
    match = re.search(r'<script[^>]+type="module"[^>]+src="/(assets/[^"]+\.js)"', html)
    assert match, "dist/index.html declares no module entry script — the build did not complete"
    path = DIST / match.group(1)
    assert path.is_file(), f"entry bundle {match.group(1)} referenced by index.html does not exist"
    return path


def chunk_containing(*needles: str) -> Path:
    """The built chunk holding every given marker (e.g. a settings key only one page emits)."""
    for path in sorted(ASSETS.glob("*.js")):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if all(needle in source for needle in needles):
            return path
    raise AssertionError(f"no built chunk contains all of {needles!r}")


def runtime_script(stem: str) -> Path:
    """A root-level runtime script, tolerating the version suffix on its filename.

    These ship as `predictor-live-v1529.js`, `burst-live-v1530.js` and so on; pinning the exact
    revision in a test means every future revision of the script breaks an unrelated assertion.
    """
    matches = sorted(DIST.glob(f"{stem}*.js"))
    assert matches, f"no runtime script matching {stem}*.js in frontend/dist"
    return matches[0]


def runtime_style(stem: str) -> Path:
    matches = sorted(DIST.glob(f"{stem}*.css"))
    assert matches, f"no runtime stylesheet matching {stem}*.css in frontend/dist"
    return matches[0]


def dist_text() -> str:
    """Every readable byte of the build, for whole-bundle content assertions."""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in DIST.rglob("*")
        if p.is_file()
    )
