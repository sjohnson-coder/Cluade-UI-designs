from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any, Callable


@dataclass
class LaneMetrics:
    name: str
    runs: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    rotations: int = 0
    in_flight: bool = False
    last_attempt_at: float = 0.0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    last_duration_ms: float = 0.0
    last_error: str = ""


class ProtectedThreadLane:
    """A bounded dedicated executor lane with deadlines and observable health.

    This prevents readiness and other live-control jobs from waiting behind the
    default asyncio executor. A timed-out executor is rotated so later cycles can
    continue even if one native dependency remains blocked.
    """

    def __init__(self, name: str, *, max_workers: int = 1, timeout_seconds: float = 0.75) -> None:
        self.name = name
        self.max_workers = max(1, int(max_workers))
        self.timeout_seconds = max(0.05, float(timeout_seconds))
        self._lock = threading.RLock()
        self._executor = self._new_executor()
        self._metrics = LaneMetrics(name=name)

    def _new_executor(self) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=f"godmode-{self.name}")

    def _rotate(self) -> None:
        with self._lock:
            old = self._executor
            self._executor = self._new_executor()
            self._metrics.rotations += 1
        old.shutdown(wait=False, cancel_futures=True)

    async def run(self, fn: Callable[..., Any], *args: Any, timeout_seconds: float | None = None, **kwargs: Any) -> Any:
        timeout = self.timeout_seconds if timeout_seconds is None else max(0.05, float(timeout_seconds))
        started = time.perf_counter()
        now = time.time()
        with self._lock:
            executor = self._executor
            self._metrics.runs += 1
            self._metrics.in_flight = True
            self._metrics.last_attempt_at = now
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(executor, lambda: fn(*args, **kwargs))
        try:
            result = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError:
            with self._lock:
                self._metrics.timeouts += 1
                self._metrics.failures += 1
                self._metrics.last_failure_at = time.time()
                self._metrics.last_error = f"deadline exceeded ({timeout:.3f}s)"
            self._rotate()
            raise
        except Exception as exc:
            with self._lock:
                self._metrics.failures += 1
                self._metrics.last_failure_at = time.time()
                self._metrics.last_error = f"{type(exc).__name__}: {exc}"
            raise
        else:
            with self._lock:
                self._metrics.successes += 1
                self._metrics.last_success_at = time.time()
                self._metrics.last_error = ""
            return result
        finally:
            with self._lock:
                self._metrics.in_flight = False
                self._metrics.last_duration_ms = round((time.perf_counter() - started) * 1000.0, 3)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            payload = asdict(self._metrics)
        now = time.time()
        payload["lastSuccessAgeSeconds"] = (
            round(max(0.0, now - payload["last_success_at"]), 3) if payload["last_success_at"] else None
        )
        payload["healthy"] = bool(payload["last_success_at"] and (payload["lastSuccessAgeSeconds"] or 0.0) <= 5.0)
        return payload

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
        executor.shutdown(wait=False, cancel_futures=True)
