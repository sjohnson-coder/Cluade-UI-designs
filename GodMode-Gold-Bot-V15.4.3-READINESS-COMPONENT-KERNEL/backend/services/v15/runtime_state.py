from __future__ import annotations

import json
import os
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

_SECRET_KEYS = {"bottoken", "bot_token", "token", "apikey", "api_key", "password", "secret"}


def _redact(value: Any, key: str = "") -> Any:
    normal = key.replace("-", "_").lower()
    if any(secret in normal for secret in _SECRET_KEYS):
        return "***configured***" if value else ""
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class RuntimeStateManager:
    """Authoritative serialised state for the V15 intelligence subsystem.

    Legacy execution state remains owned by the established V14 runtime; this manager
    explicitly mirrors selected health/decision information rather than claiming ownership
    of settings, MT5 or TickGuard files.
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {}
        self._revision = 0
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._revision = int(payload.get("revision", 0))
                self._state = dict(payload.get("state") or {})
            except Exception:
                self._state = {}
                self._revision = 0

    def _persist_locked(self) -> None:
        payload = {"revision": self._revision, "updated_at": time.time(), "state": self._state}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        temp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: Exception | None = None
        for delay in (0.01, 0.02, 0.05, 0.1, 0.2):
            try:
                os.replace(temp, self.path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(delay)
        try:
            with self.path.open("w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            temp.unlink(missing_ok=True)
        if not self.path.exists() and last_error:
            raise last_error

    def update(self, namespace: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = dict(self._state.get(namespace) or {})
            current.update(deepcopy(patch))
            self._state[namespace] = current
            self._revision += 1
            self._persist_locked()
            return self._snapshot_locked(public=False)

    def _snapshot_locked(self, public: bool) -> dict[str, Any]:
        state = deepcopy(self._state)
        if public:
            state = _redact(state)
        return {"revision": self._revision, "state": state}

    def snapshot(self, public: bool = True) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(public)

    def publish_command(self, publisher: str, command: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            receipt = {"id": uuid.uuid4().hex, "publisher": str(publisher), "sequence": int(self._state.get("command_sequence", 0)) + 1, "created_at": time.time(), "command": deepcopy(command)}
            self._state["command_sequence"] = receipt["sequence"]
            self._state["last_command"] = receipt
            self._revision += 1
            self._persist_locked()
            return receipt
