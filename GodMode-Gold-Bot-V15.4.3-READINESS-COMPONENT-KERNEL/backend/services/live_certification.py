"""Fail-closed, build-bound evidence gate for unattended live execution."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from pathlib import Path
from typing import Any


CERTIFICATION_SCHEMA_VERSION = 2
MAX_CERTIFICATION_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_EVIDENCE_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_CLOCK_SKEW_SECONDS = 300
MIN_SIGNING_KEY_BYTES = 32

REQUIRED_GATES = (
    "windowsMetaEditorCompile",
    "tickGuardAttached",
    "brokerSpecVerified",
    "orderLifecycleVerified",
    "dynamicSlReplayPassed",
    "burstFailureDrillsPassed",
    "demoSoakPassed",
    "tlsRemoteVerified",
    "backupRestoreVerified",
)


def _canonical_unsigned_payload(payload: dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("signature", None)
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sign_certification_payload(
    payload: dict[str, Any],
    *,
    signing_key: str,
) -> str:
    """Return an HMAC-SHA256 signature for a complete certification manifest."""
    key = str(signing_key or "").encode("utf-8")
    if len(key) < MIN_SIGNING_KEY_BYTES:
        raise ValueError(
            f"certification signing key must contain at least {MIN_SIGNING_KEY_BYTES} bytes"
        )
    return hmac.new(
        key,
        _canonical_unsigned_payload(payload),
        hashlib.sha256,
    ).hexdigest()


def _finite_timestamp(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _valid_sha256(value: Any) -> str | None:
    candidate = str(value or "").strip().lower()
    if len(candidate) != 64:
        return None
    try:
        bytes.fromhex(candidate)
    except ValueError:
        return None
    return candidate


def _resolve_evidence(
    reference: str,
    *,
    evidence_root: Path | None,
) -> tuple[Path | None, str | None]:
    if not reference or evidence_root is None:
        return None, "EVIDENCE_ROOT_UNAVAILABLE"
    relative = Path(reference)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None, "EVIDENCE_PATH_INVALID"
    try:
        root = evidence_root.resolve(strict=True)
        candidate = (root / relative).resolve(strict=True)
        candidate.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return None, "EVIDENCE_FILE_INVALID"
    if candidate.is_symlink() or not candidate.is_file():
        return None, "EVIDENCE_FILE_INVALID"
    return candidate, None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate_live_certification(
    payload: dict[str, Any] | None,
    *,
    build_id: str,
    now: float | None = None,
    evidence_root: str | Path | None = None,
    signing_key: str = "",
    trusted_issuers: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Verify a signed, build-bound manifest and every referenced evidence artifact."""
    payload = payload if isinstance(payload, dict) else {}
    now_value = float(time.time() if now is None else now)
    gates = payload.get("gates") if isinstance(payload.get("gates"), dict) else {}
    evidence_base = Path(evidence_root) if evidence_root is not None else None
    trusted = {str(item).strip() for item in (trusted_issuers or set()) if str(item).strip()}
    missing: list[str] = []
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    if int(payload.get("schemaVersion") or 0) != CERTIFICATION_SCHEMA_VERSION:
        failures.append("SCHEMA_VERSION_INVALID")
    if str(payload.get("buildId") or "") != str(build_id):
        failures.append("BUILD_ID_MISMATCH")

    issuer = str(payload.get("issuer") or "").strip()
    if not issuer or issuer not in trusted:
        failures.append("ISSUER_NOT_TRUSTED")
    if str(payload.get("signatureAlgorithm") or "").lower() != "hmac-sha256":
        failures.append("SIGNATURE_ALGORITHM_INVALID")
    signature = str(payload.get("signature") or "").strip().lower()
    signing_key_bytes = str(signing_key or "").encode("utf-8")
    if len(signing_key_bytes) < MIN_SIGNING_KEY_BYTES:
        failures.append("SIGNING_KEY_UNAVAILABLE")
    else:
        try:
            expected_signature = sign_certification_payload(
                payload,
                signing_key=signing_key,
            )
        except (TypeError, ValueError):
            expected_signature = ""
        if (
            len(signature) != 64
            or not expected_signature
            or not hmac.compare_digest(signature, expected_signature)
        ):
            failures.append("SIGNATURE_INVALID")

    issued_at = _finite_timestamp(payload.get("issuedAt"))
    expires_at = _finite_timestamp(payload.get("expiresAt"))
    if issued_at is None or issued_at > now_value + MAX_CLOCK_SKEW_SECONDS:
        failures.append("ISSUED_AT_INVALID")
    if expires_at is None or expires_at <= now_value:
        failures.append("CERTIFICATION_EXPIRED")
    if (
        issued_at is not None
        and expires_at is not None
        and expires_at <= issued_at
    ):
        failures.append("CERTIFICATION_WINDOW_INVALID")
    if (
        issued_at is not None
        and expires_at is not None
        and expires_at - issued_at > MAX_CERTIFICATION_TTL_SECONDS
    ):
        failures.append("CERTIFICATION_TTL_EXCEEDED")

    used_evidence_paths: set[str] = set()
    for name in REQUIRED_GATES:
        row = gates.get(name) if isinstance(gates.get(name), dict) else {}
        observed_at = _finite_timestamp(row.get("observedAt"))
        evidence_ref = str(row.get("evidence") or "").strip()
        evidence_hash = _valid_sha256(row.get("sha256"))
        passed = bool(row.get("passed"))
        gate_failures: list[str] = []

        if not passed:
            gate_failures.append(f"GATE_NOT_PASSED:{name}")
        if observed_at is None or observed_at > now_value + MAX_CLOCK_SKEW_SECONDS:
            gate_failures.append(f"EVIDENCE_TIMESTAMP_INVALID:{name}")
        elif now_value - observed_at > MAX_EVIDENCE_AGE_SECONDS:
            gate_failures.append(f"EVIDENCE_STALE:{name}")
        elif issued_at is not None and observed_at > issued_at + MAX_CLOCK_SKEW_SECONDS:
            gate_failures.append(f"EVIDENCE_AFTER_ISSUANCE:{name}")
        if not evidence_ref:
            gate_failures.append(f"EVIDENCE_REFERENCE_MISSING:{name}")
        elif evidence_ref in used_evidence_paths:
            gate_failures.append(f"EVIDENCE_REUSED:{name}")
        else:
            used_evidence_paths.add(evidence_ref)
        if evidence_hash is None:
            gate_failures.append(f"EVIDENCE_HASH_INVALID:{name}")

        artifact, path_error = _resolve_evidence(
            evidence_ref,
            evidence_root=evidence_base,
        )
        if path_error:
            gate_failures.append(f"{path_error}:{name}")
        elif artifact is not None and evidence_hash is not None:
            try:
                if not hmac.compare_digest(_file_sha256(artifact), evidence_hash):
                    gate_failures.append(f"EVIDENCE_HASH_MISMATCH:{name}")
            except OSError:
                gate_failures.append(f"EVIDENCE_FILE_UNREADABLE:{name}")

        valid = not gate_failures
        if not valid:
            missing.append(name)
            failures.extend(gate_failures)
        evidence[name] = {
            "passed": valid,
            "observedAt": observed_at,
            "evidence": evidence_ref or None,
            "sha256": evidence_hash,
            "failures": gate_failures,
        }

    approved = not failures and not missing
    return {
        "approved": approved,
        "grade": "A+" if approved else "NOT_CERTIFIED",
        "buildId": build_id,
        "certifiedBuildId": payload.get("buildId"),
        "issuer": issuer or None,
        "issuedAt": issued_at,
        "expiresAt": expires_at,
        "missingGates": missing,
        "failures": failures,
        "gates": evidence,
        "message": (
            "All unattended-live evidence gates passed for this exact build."
            if approved
            else "Unattended live execution is not certified for this exact build."
        ),
    }
