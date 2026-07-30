#!/usr/bin/env python3
"""Rebuild SHA256SUMS.txt and RELEASE_MANIFEST.json to match the current tree.

VERIFY_RELEASE.py compares every shipped file against these two inventories plus a hard-coded hash
of the compiled theme stylesheet. All three describe build OUTPUT, so a legitimate `npm run build`
invalidates all of them at once — and the product instructs the operator to run exactly that, in
REBUILD_UI_FIRST.txt, in start_frontend.bat, and in the stale-bundle banner app.py injects into the
served index.html. Before this script existed there was no supported way to get back to a verifying
release after following those instructions, so the only options were to leave the verifier failing
or to hand-edit checksum files, which defeats the point of having them.

Run this after an intentional rebuild, then run VERIFY_RELEASE.py to confirm the tree is coherent:

    cd frontend && npm run build && cd ..
    python REGENERATE_RELEASE_CHECKSUMS.py
    python VERIFY_RELEASE.py

The file selection rules are imported from VERIFY_RELEASE rather than reimplemented, so the two
scripts cannot drift apart in what they consider a release file.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from VERIFY_RELEASE import EXPECTED_BUILD, EXPECTED_VERSION, is_release_file, sha256  # noqa: E402

ROOT = Path(__file__).resolve().parent
SUMS = ROOT / "SHA256SUMS.txt"
MANIFEST = ROOT / "RELEASE_MANIFEST.json"


def release_files() -> list[Path]:
    return sorted(
        (p for p in ROOT.rglob("*") if p.is_file() and is_release_file(p, ROOT)),
        key=lambda p: p.relative_to(ROOT).as_posix(),
    )


def main() -> int:
    files = [p for p in release_files() if p not in {SUMS, MANIFEST}]

    previous = {}
    if MANIFEST.is_file():
        try:
            previous = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}

    manifest = {
        "version": EXPECTED_VERSION,
        "buildId": EXPECTED_BUILD,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Carried forward verbatim: these are disclosures about the release, not facts about the
        # file tree, and VERIFY_RELEASE asserts their exact shape.
        "tickGuard": previous.get("tickGuard", {
            "sourceIncluded": True,
            "compiledEx5Included": False,
            "protectionStatus": "INCOMPLETE until compiled and attached on Windows MT5",
        }),
        "verification": previous.get("verification", {}),
        "files": [
            {"path": p.relative_to(ROOT).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
            for p in files
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Order matters: VERIFY_RELEASE expects RELEASE_MANIFEST.json to appear in SHA256SUMS.txt but
    # expects the manifest to list neither inventory, so the manifest must exist and be final
    # before its digest is taken.
    sums_files = [p for p in release_files() if p != SUMS]
    SUMS.write_text(
        "".join(f"{sha256(p)}  {p.relative_to(ROOT).as_posix()}\n" for p in sums_files),
        encoding="utf-8",
    )

    print(f"Regenerated RELEASE_MANIFEST.json ({len(files)} files) and SHA256SUMS.txt ({len(sums_files)} files).")
    print("Now run: python VERIFY_RELEASE.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
