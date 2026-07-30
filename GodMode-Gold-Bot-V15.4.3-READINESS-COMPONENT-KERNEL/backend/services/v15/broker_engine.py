from __future__ import annotations

from collections import defaultdict, deque
from statistics import fmean
from typing import Any

from .contracts import clamp

_REQUIRED = {"spread_points", "slippage_points", "latency_ms", "filled"}


class BrokerIntelligence:
    def __init__(self, window: int = 250):
        self.window = max(5, int(window))
        self._samples: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=self.window))

    def update(self, telemetry: dict[str, Any] | None) -> dict[str, Any]:
        telemetry = telemetry if isinstance(telemetry, dict) else {}
        session = str(telemetry.get("session") or "unknown").lower()
        if not _REQUIRED.issubset(telemetry) or any(telemetry.get(k) is None for k in _REQUIRED):
            return self.profile(session, telemetry_available=False)
        sample = {
            "spread": max(0.0, float(telemetry["spread_points"])),
            "slippage": abs(float(telemetry["slippage_points"])),
            "latency": max(0.0, float(telemetry["latency_ms"])),
            "filled": bool(telemetry["filled"]),
            "rejected": bool(telemetry.get("rejected", False)),
        }
        self._samples[session].append(sample)
        return self.profile(session, telemetry_available=True)

    def profile(self, session: str = "unknown", telemetry_available: bool | None = None) -> dict[str, Any]:
        items = list(self._samples.get(str(session).lower(), []))
        if not items:
            return {
                "session": session, "samples": 0, "quality": 0.5,
                "spread_points": None, "slippage_points": None, "latency_ms": None,
                "fill_rate": None, "uncertainty": 1.0,
                "telemetry_available": False if telemetry_available is None else bool(telemetry_available and items),
            }
        spread = fmean(x["spread"] for x in items)
        slip = fmean(x["slippage"] for x in items)
        latency = fmean(x["latency"] for x in items)
        fill = fmean(1.0 if x["filled"] and not x["rejected"] else 0.0 for x in items)
        quality = clamp(fill * 0.45 + clamp(1 - spread / 100) * 0.2 + clamp(1 - slip / 25) * 0.2 + clamp(1 - latency / 1000) * 0.15)
        return {
            "session": session, "samples": len(items), "quality": quality,
            "spread_points": spread, "slippage_points": slip, "latency_ms": latency,
            "fill_rate": fill, "uncertainty": clamp(1 / (1 + len(items) / 25)),
            "telemetry_available": True,
        }
