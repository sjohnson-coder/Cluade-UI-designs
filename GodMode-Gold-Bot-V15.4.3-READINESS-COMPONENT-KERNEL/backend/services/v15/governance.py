from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class ModelGovernance:
    MATERIAL_TYPES = {"risk_threshold", "entry_threshold", "exit_policy", "burst_policy", "position_sizing", "feature_set", "session_control"}

    def __init__(self, path: Path, artifacts_dir: Path | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = Path(artifacts_dir or self.path.parent / "model_artifacts")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.state = {"active": None, "history": [], "pending": []}
        if self.path.exists():
            try:
                self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                self.state = {"active": None, "history": [], "pending": []}

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _save_locked(self) -> None:
        temp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)

    @staticmethod
    def risk_adjusted_score(metrics: dict[str, Any]) -> float:
        return float(metrics.get("sortino", 0)) * 0.35 + max(0.0, 1 - float(metrics.get("drawdown", 1))) * 0.3 + max(0.0, 1 - float(metrics.get("brier", 1))) * 0.25 + min(1.0, float(metrics.get("samples", 0)) / 500) * 0.1

    def submit(self, candidate_id: str, change_type: str, metrics: dict[str, Any], artifact_path: Path | str | None = None, feature_schema: list[str] | None = None) -> dict[str, Any]:
        if not candidate_id:
            raise ValueError("candidate_id is required")
        if artifact_path is None:
            raise ValueError("a verifiable model artifact is required")
        source = Path(artifact_path).resolve()
        if not source.is_file():
            raise ValueError("model artifact does not exist")
        try:
            source.relative_to(self.artifacts_dir.resolve())
        except ValueError:
            raise ValueError("model artifact must be inside the governance artifacts directory")
        json.loads(source.read_text(encoding="utf-8"))
        schema = [str(x) for x in (feature_schema or [])]
        if not schema:
            raise ValueError("feature_schema is required")
        with self._lock:
            if any(x.get("candidate_id") == candidate_id for x in self.state["history"]):
                raise ValueError("candidate_id already exists")
            qualifies = bool(metrics.get("shadow_passed")) and int(metrics.get("samples", 0)) >= 200 and float(metrics.get("brier", 1)) <= 0.22 and float(metrics.get("drawdown", 1)) <= 0.15 and float(metrics.get("sortino", 0)) >= 1.0
            status = "rejected"
            if qualifies:
                status = "approval_required" if change_type in self.MATERIAL_TYPES else "promoted"
            record = {"candidate_id": candidate_id, "change_type": change_type, "metrics": dict(metrics), "score": self.risk_adjusted_score(metrics), "status": status, "created_at": time.time(), "artifact_path": str(source), "artifact_sha256": self._sha256(source), "feature_schema": schema}
            self.state["history"].append(record)
            if status == "approval_required":
                self.state["pending"].append(candidate_id)
            if status == "promoted":
                record["previous"] = self.state.get("active")
                self.state["active"] = candidate_id
            self._save_locked()
            return dict(record)

    def approve(self, candidate_id: str) -> dict[str, Any]:
        with self._lock:
            record = next((x for x in reversed(self.state["history"]) if x["candidate_id"] == candidate_id), None)
            if record is None:
                raise KeyError(candidate_id)
            if record["status"] != "approval_required":
                return dict(record)
            artifact = Path(record["artifact_path"])
            if not artifact.is_file() or self._sha256(artifact) != record["artifact_sha256"]:
                raise ValueError("candidate artifact integrity check failed")
            record["previous"] = self.state.get("active")
            record["status"] = "promoted"
            record["approved_at"] = time.time()
            self.state["active"] = candidate_id
            self.state["pending"] = [x for x in self.state["pending"] if x != candidate_id]
            self._save_locked()
            return dict(record)

    def active_artifact(self) -> dict[str, Any] | None:
        with self._lock:
            active = self.state.get("active")
            record = next((x for x in reversed(self.state["history"]) if x["candidate_id"] == active and x.get("status") == "promoted"), None)
            if not record:
                return None
            path = Path(record["artifact_path"])
            if not path.is_file() or self._sha256(path) != record["artifact_sha256"]:
                raise ValueError("active model artifact integrity check failed")
            return json.loads(path.read_text(encoding="utf-8"))

    def rollback(self) -> dict[str, Any]:
        with self._lock:
            active = self.state.get("active")
            record = next((x for x in reversed(self.state["history"]) if x["candidate_id"] == active and x.get("status") == "promoted"), None)
            if not record:
                return {"status": "no_active_model"}
            self.state["active"] = record.get("previous")
            record["status"] = "rolled_back"
            record["rolled_back_at"] = time.time()
            self._save_locked()
            return dict(record)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.state))
