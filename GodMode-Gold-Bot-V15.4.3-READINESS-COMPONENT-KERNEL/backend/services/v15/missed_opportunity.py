from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class MissedOpportunityTracker:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.items: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    item = json.loads(line)
                    self.items[item["signal_id"]] = item
                except Exception:
                    continue

    def _append(self, item: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
            handle.flush()

    @staticmethod
    def _validate_geometry(side: str, entry: float, sl: float, tp: float) -> str:
        side = str(side).upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if not all(map(lambda x: isinstance(x, (int, float)), (entry, sl, tp))):
            raise ValueError("entry, sl and tp must be numeric")
        if side == "BUY" and not (sl < entry < tp):
            raise ValueError("BUY requires sl < entry < tp")
        if side == "SELL" and not (tp < entry < sl):
            raise ValueError("SELL requires tp < entry < sl")
        return side

    def register(self, signal_id: str, side: str, entry: float, sl: float, tp: float, gates: list[str], timestamp: int) -> dict[str, Any]:
        if not signal_id:
            raise ValueError("signal_id is required")
        if not isinstance(gates, list) or not all(isinstance(g, str) for g in gates):
            raise ValueError("gates must be a list of strings")
        side = self._validate_geometry(side, float(entry), float(sl), float(tp))
        with self._lock:
            if signal_id in self.items:
                raise ValueError(f"signal_id already exists: {signal_id}")
            item = {"signal_id": signal_id, "side": side, "entry": float(entry), "sl": float(sl), "tp": float(tp), "gates": list(gates), "timestamp": int(timestamp), "status": "open"}
            self.items[signal_id] = item
            self._append(item)
            return dict(item)

    def resolve(self, signal_id: str, prices: list[float], timestamp: int) -> dict[str, Any]:
        if not isinstance(prices, list) or not prices:
            raise ValueError("prices must be a non-empty chronological list")
        sequence = [float(p) for p in prices]
        with self._lock:
            if signal_id not in self.items:
                raise KeyError(signal_id)
            item = dict(self.items[signal_id])
            if item.get("status") == "resolved":
                return item
            side = item["side"]
            first_hit = None
            first_hit_index = None
            for index, price in enumerate(sequence):
                tp_hit = price >= item["tp"] if side == "BUY" else price <= item["tp"]
                sl_hit = price <= item["sl"] if side == "BUY" else price >= item["sl"]
                if tp_hit and sl_hit:
                    first_hit = "ambiguous"
                    first_hit_index = index
                    break
                if tp_hit:
                    first_hit = "tp"
                    first_hit_index = index
                    break
                if sl_hit:
                    first_hit = "sl"
                    first_hit_index = index
                    break
            classification = "profitable_miss" if first_hit == "tp" else "correct_reject" if first_hit == "sl" else "unresolved"
            item.update({
                "status": "resolved", "resolved_at": int(timestamp), "classification": classification,
                "first_hit": first_hit, "first_hit_index": first_hit_index,
                "max_price": max(sequence), "min_price": min(sequence), "observations": len(sequence),
            })
            self.items[signal_id] = item
            self._append(item)
            return dict(item)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            resolved = [x for x in self.items.values() if x.get("status") == "resolved"]
            return {"total": len(self.items), "resolved": len(resolved), "profitable_misses": sum(x.get("classification") == "profitable_miss" for x in resolved), "correct_rejects": sum(x.get("classification") == "correct_reject" for x in resolved), "unresolved": sum(x.get("classification") == "unresolved" for x in resolved), "gate_pressure": self._gate_pressure(resolved)}

    @staticmethod
    def _gate_pressure(items: list[dict[str, Any]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in items:
            if item.get("classification") == "profitable_miss":
                for gate in item.get("gates", []):
                    out[gate] = out.get(gate, 0) + 1
        return out
