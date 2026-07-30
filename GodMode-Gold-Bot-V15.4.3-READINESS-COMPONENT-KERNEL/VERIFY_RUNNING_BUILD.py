from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "backend" / "app.py"
PORT_URL = "http://127.0.0.1:8000/api/readiness"


def expected_build() -> str:
    text = APP.read_text(encoding="utf-8")
    match = re.search(r'^BUILD_ID\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise RuntimeError("BUILD_ID not found in backend/app.py")
    return match.group(1)


def probe(timeout: float = 1.5) -> tuple[bool, str, dict]:
    try:
        req = urllib.request.Request(PORT_URL, headers={"Accept": "application/json", "Cache-Control": "no-store"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
        return True, str(payload.get("buildId") or payload.get("build") or ""), payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False, "", {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", help="Return 0 when port is free, 10 for exact build, 20 for wrong build")
    parser.add_argument("--require", action="store_true", help="Require the exact build to be running")
    args = parser.parse_args()
    expected = expected_build()
    reachable, actual, payload = probe()
    if args.preflight:
        if not reachable:
            print(f"PORT_FREE expected={expected}")
            return 0
        if actual == expected:
            print(f"EXACT_BUILD_ALREADY_RUNNING buildId={actual} pid={payload.get('pid','unknown')}")
            return 10
        print(f"WRONG_BUILD_ON_PORT expected={expected} actual={actual or 'unknown'} pid={payload.get('pid','unknown')}")
        return 20
    if args.require:
        if reachable and actual == expected:
            print(f"PASS exact backend build is running: {actual}")
            return 0
        if reachable:
            print(f"FAIL port 8000 belongs to the wrong backend. Expected {expected}, got {actual or 'unknown'}.")
        else:
            print(f"FAIL backend did not answer on port 8000. Expected {expected}.")
        return 1
    print(json.dumps({"reachable": reachable, "expected": expected, "actual": actual, "payload": payload}, indent=2))
    return 0 if reachable and actual == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
