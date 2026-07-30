from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.live_certification import (  # noqa: E402
    CERTIFICATION_SCHEMA_VERSION,
    MAX_CERTIFICATION_TTL_SECONDS,
    REQUIRED_GATES,
    evaluate_live_certification,
    sign_certification_payload,
)
from services.runtime_safety import atomic_write_json  # noqa: E402
from dotenv import load_dotenv  # noqa: E402


def _read_backend_build_id() -> str:
    """Read the current BUILD_ID directly from backend/app.py.

    V14.1.17: pinning EXPECTED_BUILD to a string literal was the ROOT CAUSE of
    'unattended live certification is incomplete'. Every release renamed BUILD_ID
    in app.py but this script kept asserting an older tag, so the signed cert had
    the wrong buildId and evaluate_live_certification failed BUILD_ID_MISMATCH.
    Reading it fresh here ends the drift permanently.
    """
    app_py = BACKEND / "app.py"
    for line in app_py.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("BUILD_ID"):
            _, _, rhs = stripped.partition("=")
            return rhs.strip().strip('"').strip("'")
    raise RuntimeError("Could not locate BUILD_ID in backend/app.py")


EXPECTED_BUILD = _read_backend_build_id()


def _artifact_path(evidence_root: Path, reference: str) -> Path:
    relative = Path(str(reference or "").strip())
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"unsafe evidence path: {reference!r}")
    root = evidence_root.resolve(strict=True)
    candidate = root / relative
    for parent in (root.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)):
        if parent.is_symlink():
            raise ValueError(f"symlink evidence path is not allowed: {reference!r}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"evidence path escapes root: {reference!r}") from exc
    if not resolved.is_file():
        raise ValueError(f"evidence artifact is not a regular file: {reference!r}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_and_sign(
    draft: dict[str, Any],
    *,
    evidence_root: str | Path,
    build_id: str,
    issuer: str,
    signing_key: str,
    now: float | None = None,
    ttl_seconds: int = 24 * 60 * 60,
) -> dict[str, Any]:
    """Hash every asserted gate and sign a bounded exact-build certificate."""
    if not isinstance(draft, dict):
        raise ValueError("certification draft must be a JSON object")
    if str(draft.get("buildId") or "") != str(build_id):
        raise ValueError("draft buildId does not match the expected release build")
    issuer_value = str(issuer or "").strip()
    if not issuer_value:
        raise ValueError("issuer is required")
    ttl = int(ttl_seconds)
    if ttl < 1 or ttl > MAX_CERTIFICATION_TTL_SECONDS:
        raise ValueError(
            f"ttl_seconds must be between 1 and {MAX_CERTIFICATION_TTL_SECONDS}"
        )
    root = Path(evidence_root)
    gates = draft.get("gates") if isinstance(draft.get("gates"), dict) else {}
    signed_gates: dict[str, dict[str, Any]] = {}
    used_references: set[str] = set()
    for gate in REQUIRED_GATES:
        row = gates.get(gate) if isinstance(gates.get(gate), dict) else {}
        if not bool(row.get("passed")):
            raise ValueError(f"gate is not marked passed: {gate}")
        reference = str(row.get("evidence") or "").strip()
        if not reference:
            raise ValueError(f"evidence reference is missing: {gate}")
        if reference in used_references:
            raise ValueError(f"evidence reference is reused: {reference}")
        used_references.add(reference)
        observed_at = row.get("observedAt")
        try:
            observed_value = float(observed_at)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"observedAt is invalid: {gate}") from exc
        artifact = _artifact_path(root, reference)
        signed_gates[gate] = {
            "passed": True,
            "observedAt": observed_value,
            "evidence": reference,
            "sha256": _sha256(artifact),
        }

    issued_at = float(time.time() if now is None else now)
    result = {
        "schemaVersion": CERTIFICATION_SCHEMA_VERSION,
        "buildId": str(build_id),
        "issuer": issuer_value,
        "signatureAlgorithm": "hmac-sha256",
        "issuedAt": issued_at,
        "expiresAt": issued_at + ttl,
        "gates": signed_gates,
    }
    result["signature"] = sign_certification_payload(
        result,
        signing_key=signing_key,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hash and HMAC-sign exact-build unattended-live evidence."
    )
    parser.add_argument(
        "--draft",
        type=Path,
        default=ROOT / "live_certification.template.json",
    )
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=ROOT / "backend" / "data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "backend" / "data" / "live_certification.json",
    )
    parser.add_argument("--issuer", default="local-release-officer")
    parser.add_argument("--ttl-hours", type=float, default=24.0)
    args = parser.parse_args()

    load_dotenv(BACKEND / ".env")
    signing_key = os.getenv("GODMODE_CERTIFICATION_HMAC_KEY", "")
    try:
        if args.evidence_root.resolve() != args.output.parent.resolve():
            raise ValueError(
                "--output must be directly inside --evidence-root so the runtime "
                "can re-verify every relative evidence path"
            )
        draft = json.loads(args.draft.read_text(encoding="utf-8"))
        certificate = prepare_and_sign(
            draft,
            evidence_root=args.evidence_root,
            build_id=EXPECTED_BUILD,
            issuer=args.issuer,
            signing_key=signing_key,
            ttl_seconds=int(args.ttl_hours * 3600),
        )
        status = evaluate_live_certification(
            certificate,
            build_id=EXPECTED_BUILD,
            evidence_root=args.output.parent,
            signing_key=signing_key,
            trusted_issuers={args.issuer},
        )
        if not status.get("approved"):
            raise ValueError(
                "self-verification failed: "
                + ", ".join(str(item) for item in status.get("failures", []))
            )
        atomic_write_json(args.output, certificate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        f"PASS: signed {EXPECTED_BUILD} certification for {args.issuer!r} "
        f"at {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
