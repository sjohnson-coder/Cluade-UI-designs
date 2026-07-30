from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator


def _directory_fsync_supported() -> bool:
    return os.name != "nt"


def atomic_write_json(
    path: str | Path,
    payload: Any,
    *,
    mode: int = 0o600,
) -> None:
    """Atomically replace JSON and verify the committed file before reporting success.

    The file itself is flushed before replacement. Directory fsync is attempted for
    crash durability but is best-effort because some supported filesystems reject
    directory handles after the replacement has already committed.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, mode)
        except OSError as exc:
            # A restrictive chmod can be unavailable on some Windows filesystems.
            # The atomic write still completes, while the caller can audit the final
            # permissions on platforms that expose POSIX modes.
            _chmod_unavailable = exc
        os.replace(temporary, target)
        # Windows does not support opening a directory with os.open for fsync in
        # the same way POSIX filesystems do. Attempting it produces a misleading
        # PermissionError after the file has already been safely replaced, which
        # previously flooded the backend console and made a healthy persistence
        # path look broken. File fsync + atomic replace + JSON readback are the
        # supported durability checks on Windows.
        if _directory_fsync_supported():
            try:
                directory_fd = os.open(str(target.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError as exc:
                # At this point os.replace has committed the new generation.
                # Raising would falsely tell callers that no state change occurred
                # and can trigger an unsafe duplicate retry.
                logging.getLogger("godmode").warning(
                    "Directory fsync unavailable after atomic JSON commit for %s: %s",
                    target,
                    exc,
                )
        # A readback catches truncated/corrupt storage before the caller reports success.
        with target.open("r", encoding="utf-8") as handle:
            json.load(handle)
    finally:
        if temporary.exists():
            temporary.unlink()


class LoopLatencyWatchdog:
    """Hysteresis-based event-loop lag detector; avoids flapping on one slow tick."""

    def __init__(
        self,
        *,
        expected_interval_seconds: float,
        lag_threshold_seconds: float,
        breach_limit: int = 3,
        recovery_limit: int = 2,
    ) -> None:
        if expected_interval_seconds <= 0 or lag_threshold_seconds < 0:
            raise ValueError("watchdog intervals must be positive")
        if breach_limit < 1 or recovery_limit < 1:
            raise ValueError("watchdog limits must be at least one")
        self.expected_interval_seconds = float(expected_interval_seconds)
        self.lag_threshold_seconds = float(lag_threshold_seconds)
        self.breach_limit = int(breach_limit)
        self.recovery_limit = int(recovery_limit)
        self._breaches = 0
        self._recoveries = 0
        self._ok = True

    def observe(self, elapsed_seconds: float) -> dict[str, Any]:
        elapsed = max(0.0, float(elapsed_seconds))
        lag = max(0.0, elapsed - self.expected_interval_seconds)
        if lag > self.lag_threshold_seconds:
            self._breaches += 1
            self._recoveries = 0
            if self._breaches >= self.breach_limit:
                self._ok = False
        else:
            self._recoveries += 1
            if self._recoveries >= self.recovery_limit:
                self._ok = True
                self._breaches = 0
        return {
            "ok": self._ok,
            "elapsedSeconds": round(elapsed, 6),
            "lagSeconds": round(lag, 6),
            "consecutiveBreaches": self._breaches,
            "consecutiveRecoveries": self._recoveries,
            "thresholdSeconds": self.lag_threshold_seconds,
        }


class RuntimeHealth:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._components: dict[str, dict[str, Any]] = {}

    def beat(self, component: str, detail: str = "ok", **metrics: Any) -> None:
        with self._lock:
            previous = self._components.get(component, {})
            self._components[component] = {
                **previous,
                "ok": True,
                "lastOkAt": time.time(),
                "lastEventAt": time.time(),
                "detail": detail,
                "metrics": metrics,
            }

    def fail(self, component: str, error: BaseException | str, **metrics: Any) -> None:
        with self._lock:
            previous = self._components.get(component, {})
            self._components[component] = {
                **previous,
                "ok": False,
                "lastErrorAt": time.time(),
                "lastEventAt": time.time(),
                "detail": str(error),
                "metrics": metrics,
                "failures": int(previous.get("failures", 0)) + 1,
            }

    def snapshot(self, stale_after: dict[str, float] | None = None) -> dict[str, Any]:
        stale_after = stale_after or {}
        now = time.time()
        with self._lock:
            out: dict[str, Any] = {}
            for name, raw in self._components.items():
                row = dict(raw)
                last = float(row.get("lastEventAt", 0.0) or 0.0)
                row["ageSeconds"] = round(now - last, 2) if last else None
                threshold = stale_after.get(name)
                row["stale"] = bool(threshold and last and now - last > threshold)
                if row["stale"]:
                    row["ok"] = False
                    row["detail"] = f"stale for {row['ageSeconds']}s"
                out[name] = row
            return out


class ExecutionLedger:
    """Durable, process-safe idempotency and transaction journal for order requests."""

    IDENTITY_FIELDS = ("idempotencyKey", "executionId", "signalId", "tradeId")

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS execution_commands (
                    idempotency_key TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    source TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at REAL,
                    broker_order TEXT,
                    broker_deal TEXT,
                    broker_position TEXT
                )"""
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(execution_commands)").fetchall()}
            for col, ddl in {
                "attempt_count": "ALTER TABLE execution_commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
                "lease_expires_at": "ALTER TABLE execution_commands ADD COLUMN lease_expires_at REAL",
                "broker_order": "ALTER TABLE execution_commands ADD COLUMN broker_order TEXT",
                "broker_deal": "ALTER TABLE execution_commands ADD COLUMN broker_deal TEXT",
                "broker_position": "ALTER TABLE execution_commands ADD COLUMN broker_position TEXT",
            }.items():
                if col not in cols:
                    conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_status ON execution_commands(status, updated_at)")

    @staticmethod
    def explicit_identity(payload: dict[str, Any]) -> str:
        for field in ExecutionLedger.IDENTITY_FIELDS:
            value = str(payload.get(field) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def key_for(payload: dict[str, Any], source: str, bucket_seconds: int = 30) -> str:
        explicit = ExecutionLedger.explicit_identity(payload)
        operation = str(payload.get("operation") or "OPEN").upper()
        if explicit:
            # An execution identity is global for an operation, not scoped to the route that
            # happened to receive a retry. The same command retried through another API path
            # must still resolve to one durable ledger row.
            raw = f"{operation}:{explicit}"
        else:
            # Mutations are naturally idempotent by ticket + requested final state.
            # Live opens MUST provide an explicit stable identity; time buckets are not safe.
            stable = {
                "source": source, "operation": operation,
                "ticket": payload.get("ticket") or payload.get("position"),
                "symbol": payload.get("symbol"),
                "side": payload.get("side") or payload.get("direction"),
                "volume": payload.get("volume") or payload.get("lots"),
                "sl": payload.get("sl"), "tp": payload.get("tp"),
                "comment": payload.get("comment"),
            }
            if operation in {"OPEN", "MULTI_TARGET_OPEN", "BURST", "PYRAMID"}:
                stable["missingExplicitIdentity"] = True
            raw = json.dumps(stable, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def begin(self, payload: dict[str, Any], source: str, lease_seconds: int = 45) -> tuple[bool, str, dict[str, Any] | None]:
        key = self.key_for(payload, source)
        now = time.time()
        request_id = str(uuid.uuid4())
        with self._lock, self._conn() as conn:
            existing = conn.execute("SELECT * FROM execution_commands WHERE idempotency_key=?", (key,)).fetchone()
            if existing:
                status = str(existing["status"] or "")
                lease = float(existing["lease_expires_at"] or 0.0)
                # A broker-confirmed rejection/known failure means the command did not
                # execute and is therefore safe to retry with the same identity. This is
                # essential for protective SL changes that can be transiently rejected
                # by a freeze level or moving price. FILLED/PARTIAL and uncertain
                # ACKNOWLEDGED/UNKNOWN outcomes remain strictly deduplicated.
                terminal = status in {"FILLED","PARTIAL","DRY_RUN","RECONCILED","CANCELLED"}
                # ACKNOWLEDGED/UNKNOWN are uncertain broker outcomes and MUST remain blocked
                # until explicit reconciliation, regardless of lease expiry.
                uncertain = status in {"ACKNOWLEDGED", "UNKNOWN"}
                active = status in {"CREATED","VALIDATED","SUBMITTING"} and lease > now
                # A stale SUBMITTING row may already have reached MT5 before the process died.
                # It must never be retried blindly; convert it to UNKNOWN and require broker reconciliation.
                if status == "SUBMITTING" and lease <= now:
                    conn.execute("UPDATE execution_commands SET status='UNKNOWN', updated_at=?, lease_expires_at=NULL, error=? WHERE idempotency_key=?",
                                 (now, "Submission lease expired; broker outcome must be reconciled before retry.", key))
                    return False, key, {"status":"UNKNOWN","requestId":existing["request_id"],"result":None,"leaseExpiresAt":0.0,
                                        "error":"Submission lease expired; reconciliation required."}
                if terminal or uncertain or active:
                    result = json.loads(existing["result_json"]) if existing["result_json"] else None
                    return False, key, {"status": status, "requestId": existing["request_id"], "result": result, "leaseExpiresAt": lease}
                conn.execute("UPDATE execution_commands SET request_id=?, status='VALIDATED', updated_at=?, lease_expires_at=?, attempt_count=COALESCE(attempt_count,0)+1, error=NULL WHERE idempotency_key=?",
                             (request_id, now, now + lease_seconds, key))
                return True, key, {"status":"VALIDATED","requestId":request_id,"recovered":True}
            conn.execute(
                "INSERT INTO execution_commands (idempotency_key,request_id,created_at,updated_at,source,status,request_json,result_json,error,attempt_count,lease_expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (key, request_id, now, now, source, "VALIDATED", json.dumps(payload, default=str), None, None, 1, now + lease_seconds),
            )
        return True, key, {"status": "VALIDATED", "requestId": request_id}

    def mark_submitting(self, key: str, lease_seconds: int = 45) -> None:
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE execution_commands SET status='SUBMITTING', updated_at=?, lease_expires_at=? WHERE idempotency_key=?", (time.time(), time.time()+lease_seconds, key))

    @staticmethod
    def normalize_broker_result(result: dict[str, Any]) -> dict[str, Any]:
        """Flatten MT5 bridge response shapes into one canonical confirmation record."""
        nested = result.get("result") if isinstance(result.get("result"), dict) else {}
        request = result.get("request") if isinstance(result.get("request"), dict) else {}
        mt5_request = result.get("mt5Request") if isinstance(result.get("mt5Request"), dict) else {}
        def first(*values: Any) -> Any:
            for value in values:
                if value not in (None, "", 0, 0.0):
                    return value
            return None
        return {
            "retcode": first(result.get("retcode"), nested.get("retcode"), (result.get("executionMetrics") or {}).get("retcode")),
            "order": first(result.get("order"), nested.get("order")),
            "deal": first(result.get("deal"), nested.get("deal")),
            "position": first(result.get("position"), result.get("ticket"), nested.get("position")),
            "requestedVolume": first(result.get("requestedVolume"), request.get("volume"), mt5_request.get("volume")),
            "filledVolume": first(result.get("filledVolume"), nested.get("volume")),
            "requestedPrice": first(result.get("requestedPrice"), mt5_request.get("price"), (result.get("executionMetrics") or {}).get("requestedPrice")),
            "filledPrice": first(result.get("filledPrice"), nested.get("price"), (result.get("executionMetrics") or {}).get("filledPrice")),
            "confirmed": bool(result.get("confirmed") or result.get("filled") or first(result.get("deal"), nested.get("deal"), result.get("position"), nested.get("position"))),
        }

    def finish(self, key: str, result: dict[str, Any]) -> None:
        canonical = self.normalize_broker_result(result)
        result = {**result, "brokerConfirmation": canonical}
        dry = bool(result.get("dryRun"))
        ok = bool(result.get("ok"))
        requested_volume = float(canonical.get("requestedVolume") or 0.0)
        filled_volume = float(canonical.get("filledVolume") or 0.0)
        confirmed = bool(canonical.get("confirmed"))
        # Successful SL/TP modifications and closes can be confirmed by readback marker.
        mutation_confirmed = bool(result.get("readbackConfirmed"))
        if dry: status = "DRY_RUN"
        elif not ok: status = "REJECTED"
        elif requested_volume and filled_volume and filled_volume + 1e-9 < requested_volume: status = "PARTIAL"
        elif confirmed or mutation_confirmed: status = "FILLED"
        else: status = "ACKNOWLEDGED"
        # Preserve a lease for uncertain outcomes; they cannot be retried until reconciled.
        lease = None if status not in {"ACKNOWLEDGED"} else time.time() + 86400 * 365
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE execution_commands SET status=?, updated_at=?, lease_expires_at=?, result_json=?, error=?, broker_order=?, broker_deal=?, broker_position=? WHERE idempotency_key=?",
                (status, time.time(), lease, json.dumps(result, default=str), None if ok else str(result.get("message", "rejected")),
                 str(canonical.get("order") or ""), str(canonical.get("deal") or ""), str(canonical.get("position") or ""), key),
            )

    def fail(
        self,
        key: str,
        error: BaseException | str,
        unknown: bool = False,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE execution_commands SET status=?, updated_at=?, lease_expires_at=?, error=?, "
                "result_json=COALESCE(?,result_json) WHERE idempotency_key=?",
                (
                    "UNKNOWN" if unknown else "FAILED",
                    time.time(),
                    (time.time() + 86400 * 365) if unknown else None,
                    str(error),
                    json.dumps(result, default=str) if result is not None else None,
                    key,
                ),
            )


    def reconcile(self, key: str, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        allowed = {"FILLED", "PARTIAL", "REJECTED", "FAILED", "CANCELLED", "RECONCILED"}
        status = str(status).upper()
        if status not in allowed:
            raise ValueError(f"Invalid reconciliation status: {status}")
        with self._lock, self._conn() as conn:
            conn.execute("UPDATE execution_commands SET status=?, updated_at=?, lease_expires_at=NULL, result_json=COALESCE(?,result_json), error=? WHERE idempotency_key=?",
                         (status, time.time(), json.dumps(result, default=str) if result is not None else None, error, key))

    def get(self, key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM execution_commands WHERE idempotency_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def unresolved(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM execution_commands WHERE status IN ('SUBMITTING','ACKNOWLEDGED','UNKNOWN') ORDER BY updated_at").fetchall()
        return [dict(r) for r in rows]

    def stale(self, older_than_seconds: int = 60) -> list[dict[str, Any]]:
        cutoff=time.time()-older_than_seconds
        with self._conn() as conn:
            rows=conn.execute("SELECT * FROM execution_commands WHERE status IN ('VALIDATED','SUBMITTING','ACKNOWLEDGED','UNKNOWN') AND updated_at<?",(cutoff,)).fetchall()
        return [dict(r) for r in rows]


    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM execution_commands ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [dict(row) for row in rows]


def configure_logging(data_dir: str | Path) -> logging.Logger:
    logger = logging.getLogger("godmode")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    path = Path(data_dir) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path / "godmode.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    if os.getenv("GODMODE_CONSOLE_LOG", "true").lower() in {"1", "true", "yes"}:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(console)
    return logger
