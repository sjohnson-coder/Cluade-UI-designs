from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class _ComponentState:
    name: str
    probe: Callable[[], Any]
    interval_seconds: float
    timeout_seconds: float
    critical: bool
    max_age_seconds: float
    payload: Any = None
    in_flight: bool = False
    runs: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    skipped: int = 0
    last_attempt_at: float = 0.0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    last_duration_ms: float = 0.0
    last_error: str = ""
    future: Any = None
    started_perf: float = 0.0


class ReadinessComponentMonitor:
    """Bounded readiness probes with one in-flight call per component.

    A timed-out native probe is *not* resubmitted until the original worker
    finishes. This prevents the executor/thread accumulation caused by rotating
    a whole executor after every aggregate readiness timeout. Last-known-good
    payloads remain available with explicit age and error metadata.
    """

    def __init__(self, *, max_workers: int = 4) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="godmode-readiness-component",
        )
        self._states: dict[str, _ComponentState] = {}
        self._closed = False

    def register(
        self,
        name: str,
        probe: Callable[[], Any],
        *,
        interval_seconds: float,
        timeout_seconds: float,
        critical: bool,
        max_age_seconds: float,
    ) -> None:
        key = str(name).strip()
        if not key:
            raise ValueError("component name is required")
        with self._lock:
            self._states[key] = _ComponentState(
                name=key,
                probe=probe,
                interval_seconds=max(0.1, float(interval_seconds)),
                timeout_seconds=max(0.05, float(timeout_seconds)),
                critical=bool(critical),
                max_age_seconds=max(0.2, float(max_age_seconds)),
            )

    def names(self) -> list[str]:
        with self._lock:
            return list(self._states)

    def due(self, name: str) -> bool:
        with self._lock:
            state = self._states[name]
            if state.in_flight:
                return False
            base = state.last_attempt_at or state.last_success_at
            return not base or (time.time() - base) >= state.interval_seconds

    def _complete(self, name: str, future: Any) -> None:
        finished_perf = time.perf_counter()
        finished_at = time.time()
        try:
            result = future.result()
        except Exception as exc:  # pragma: no cover - exercised through async wrapper
            with self._lock:
                state = self._states.get(name)
                if state is None:
                    return
                state.in_flight = False
                state.future = None
                state.failures += 1
                state.last_failure_at = finished_at
                state.last_error = f"{type(exc).__name__}: {exc}"
                state.last_duration_ms = round((finished_perf - state.started_perf) * 1000.0, 3)
        else:
            with self._lock:
                state = self._states.get(name)
                if state is None:
                    return
                state.payload = deepcopy(result)
                state.in_flight = False
                state.future = None
                state.successes += 1
                state.last_success_at = finished_at
                state.last_error = ""
                state.last_duration_ms = round((finished_perf - state.started_perf) * 1000.0, 3)

    async def refresh(self, name: str, *, force: bool = False) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        with self._lock:
            if self._closed:
                return {"ok": False, "closed": True, "name": name}
            state = self._states[name]
            if state.in_flight:
                state.skipped += 1
                return {"ok": True, "skipped": True, "inFlight": True, "name": name}
            if not force and not self.due(name):
                state.skipped += 1
                return {"ok": True, "skipped": True, "inFlight": False, "name": name}
            state.in_flight = True
            state.runs += 1
            state.last_attempt_at = time.time()
            state.started_perf = time.perf_counter()
            future = loop.run_in_executor(self._executor, state.probe)
            state.future = future
            timeout = state.timeout_seconds
            future.add_done_callback(lambda fut, component=name: self._complete(component, fut))

        try:
            await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError:
            with self._lock:
                state = self._states[name]
                state.timeouts += 1
                state.last_failure_at = time.time()
                state.last_error = f"deadline exceeded ({timeout:.3f}s); original probe still running"
            return {"ok": False, "timedOut": True, "inFlight": True, "name": name}
        except Exception as exc:
            # Completion callback records the detailed state.
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "name": name}
        return {"ok": True, "timedOut": False, "name": name}

    def snapshot(self, name: str) -> dict[str, Any]:
        with self._lock:
            state = self._states[name]
            payload = deepcopy(state.payload)
            row = {
                "name": state.name,
                "payload": payload,
                "critical": state.critical,
                "maxAgeSeconds": state.max_age_seconds,
                "intervalSeconds": state.interval_seconds,
                "timeoutSeconds": state.timeout_seconds,
                "inFlight": state.in_flight,
                "runs": state.runs,
                "successes": state.successes,
                "failures": state.failures,
                "timeouts": state.timeouts,
                "skipped": state.skipped,
                "lastAttemptAt": state.last_attempt_at,
                "lastSuccessAt": state.last_success_at,
                "lastFailureAt": state.last_failure_at,
                "lastDurationMs": state.last_duration_ms,
                "lastError": state.last_error,
            }
        now = time.time()
        success_age = max(0.0, now - row["lastSuccessAt"]) if row["lastSuccessAt"] else None
        attempt_age = max(0.0, now - row["lastAttemptAt"]) if row["lastAttemptAt"] else None
        row["lastSuccessAgeSeconds"] = round(success_age, 3) if success_age is not None else None
        row["lastAttemptAgeSeconds"] = round(attempt_age, 3) if attempt_age is not None else None
        row["fresh"] = bool(success_age is not None and success_age <= row["maxAgeSeconds"])
        row["status"] = (
            "LIVE" if row["fresh"] and not row["lastError"] else
            "DEGRADED" if row["fresh"] else
            "COLLECTING" if row["inFlight"] and row["payload"] is None else
            "STALE"
        )
        return row

    def snapshots(self) -> dict[str, dict[str, Any]]:
        return {name: self.snapshot(name) for name in self.names()}

    async def refresh_due(self) -> dict[str, dict[str, Any]]:
        names = [name for name in self.names() if self.due(name)]
        if not names:
            return {}
        results = await asyncio.gather(*(self.refresh(name) for name in names), return_exceptions=False)
        return {row["name"]: row for row in results}

    async def refresh_all(self, *, force: bool = False) -> dict[str, dict[str, Any]]:
        results = await asyncio.gather(
            *(self.refresh(name, force=force) for name in self.names()),
            return_exceptions=False,
        )
        return {row["name"]: row for row in results}

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            executor = self._executor
        executor.shutdown(wait=False, cancel_futures=True)
