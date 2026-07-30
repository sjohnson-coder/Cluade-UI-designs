from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VALID_MODES = {"SHADOW", "DEMO", "LIVE_RESTRICTED", "LIVE_FULL"}
OPEN_OPERATIONS = {"OPEN", "MULTI_TARGET_OPEN", "BURST", "PYRAMID", "PLACE_PENDING"}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


@dataclass(frozen=True)
class SafetyDecision:
    ok: bool
    mode: str
    payload: dict[str, Any]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    snapshot_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocked": not self.ok,
            "mode": self.mode,
            "payload": self.payload,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "snapshotId": self.snapshot_id,
            "message": "Pre-live safety gates passed." if self.ok else "Pre-live safety gate blocked execution: " + "; ".join(self.blockers),
        }


class PreLiveSafetySupervisor:
    """Independent fail-closed admission gate and immutable pre-trade journal."""

    def __init__(self, journal_path: str | Path) -> None:
        self.journal_path = Path(journal_path)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def normalise_mode(value: Any) -> str:
        mode = str(value or "LIVE_RESTRICTED").strip().upper()
        return mode if mode in VALID_MODES else "LIVE_RESTRICTED"

    def assess(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        config: dict[str, Any],
        mt5_status: dict[str, Any],
        market: dict[str, Any],
        account: dict[str, Any],
        open_positions: list[dict[str, Any]],
        unresolved_commands: int,
        runtime_ready: bool,
        runtime_reasons: tuple[str, ...] | list[str] | None = None,
        daily_pnl: float = 0.0,
        consecutive_losses: int = 0,
    ) -> SafetyDecision:
        candidate = dict(payload)
        operation = str(candidate.get("operation") or "OPEN").upper()
        mode = self.normalise_mode(config.get("mode"))
        blockers: list[str] = []
        warnings: list[str] = []
        snapshot_id = f"pts-{uuid.uuid4().hex}"

        if operation not in OPEN_OPERATIONS:
            decision = SafetyDecision(True, mode, candidate, (), (), snapshot_id)
            self._write_snapshot(decision, source, mt5_status, market, account, open_positions, daily_pnl, consecutive_losses)
            return decision

        if mode in {"SHADOW", "DEMO"} and not bool(candidate.get("dryRun")):
            blockers.append(f"deployment mode {mode} does not permit live broker orders")
        if not bool(mt5_status.get("connected")):
            blockers.append("MT5 is disconnected")
        if mt5_status.get("tradeAllowed") is False:
            blockers.append("MT5 terminal or account does not allow trading")
        if not runtime_ready:
            # V15.0.8 — name the failing subsystem. This blocker previously said only
            # "authoritative runtime readiness is not healthy", which is true but
            # undiagnosable: the operator sees a manual trade rejected with no way to
            # tell whether MT5 dropped, a background loop died, or a command is stuck
            # awaiting reconciliation. The underlying reasons were already computed by
            # _authoritative_readiness() and then thrown away at this boundary.
            detail = "; ".join(str(r) for r in (runtime_reasons or []) if r)
            blockers.append(
                f"authoritative runtime readiness is not healthy ({detail})" if detail
                else "authoritative runtime readiness is not healthy"
            )
        if unresolved_commands > 0:
            blockers.append(f"{unresolved_commands} broker command(s) require reconciliation")

        expected_symbol = str(config.get("symbol") or candidate.get("symbol") or "XAUUSD").upper()
        actual_symbol = str(candidate.get("symbol") or expected_symbol).upper()
        if actual_symbol != expected_symbol:
            blockers.append(f"symbol {actual_symbol} does not match configured symbol {expected_symbol}")

        market_source = str(market.get("source") or "").lower()
        if market_source in {"demo", "synthetic", "warming", "error"}:
            blockers.append(f"market source {market_source or 'unknown'} is not valid for live execution")
        tick_age = _finite(market.get("ageSeconds", market.get("tickAgeSeconds")), -1.0)
        max_tick_age = max(0.5, _finite(config.get("maxTickAgeSeconds"), 5.0))
        if tick_age >= 0 and tick_age > max_tick_age:
            blockers.append(f"market tick is stale ({tick_age:.2f}s > {max_tick_age:.2f}s)")

        spread = _finite(market.get("spread"), -1.0)
        max_spread = max(0.0, _finite(config.get("maxSpreadPrice"), 0.8))
        if spread < 0:
            blockers.append("live spread telemetry is unavailable")
        elif max_spread and spread > max_spread:
            blockers.append(f"spread {spread:.5f} exceeds maximum {max_spread:.5f}")

        daily_loss_limit = abs(_finite(config.get("maxDailyLoss"), 100.0))
        if daily_loss_limit and daily_pnl <= -daily_loss_limit:
            blockers.append(f"daily loss limit reached ({daily_pnl:.2f} <= -{daily_loss_limit:.2f})")
        max_losses = max(1, int(_finite(config.get("maxConsecutiveLosses"), 3)))
        if consecutive_losses >= max_losses:
            blockers.append(f"consecutive-loss lockout reached ({consecutive_losses}/{max_losses})")

        max_positions = max(1, int(_finite(config.get("maxOpenPositions"), 1 if mode == "LIVE_RESTRICTED" else 5)))
        if len(open_positions) >= max_positions:
            blockers.append(f"open-position limit reached ({len(open_positions)}/{max_positions})")

        if mode == "LIVE_RESTRICTED":
            if operation in {"BURST", "PYRAMID", "MULTI_TARGET_OPEN"} and not bool(config.get("allowComplexEntries", False)):
                blockers.append(f"{operation} is disabled in LIVE_RESTRICTED mode")
            max_volume = max(0.01, _finite(config.get("maxRestrictedVolume"), 0.01))
            requested = _finite(candidate.get("volume", candidate.get("lots")), 0.0)
            if requested <= 0:
                blockers.append("order volume is missing or invalid")
            elif requested > max_volume:
                candidate["volume"] = max_volume
                candidate["lots"] = max_volume
                warnings.append(f"volume capped from {requested:.2f} to {max_volume:.2f} lots")

        balance = _finite(account.get("balance"), 0.0)
        equity = _finite(account.get("equity"), balance)
        if balance > 0:
            drawdown_pct = max(0.0, (balance - equity) / balance * 100.0)
            max_drawdown = max(0.0, _finite(config.get("maxEquityDrawdownPct"), 5.0))
            if max_drawdown and drawdown_pct >= max_drawdown:
                blockers.append(f"equity drawdown lockout reached ({drawdown_pct:.2f}% >= {max_drawdown:.2f}%)")

        decision = SafetyDecision(not blockers, mode, candidate, tuple(blockers), tuple(warnings), snapshot_id)
        self._write_snapshot(decision, source, mt5_status, market, account, open_positions, daily_pnl, consecutive_losses)
        return decision

    def _write_snapshot(
        self,
        decision: SafetyDecision,
        source: str,
        mt5_status: dict[str, Any],
        market: dict[str, Any],
        account: dict[str, Any],
        open_positions: list[dict[str, Any]],
        daily_pnl: float,
        consecutive_losses: int,
    ) -> None:
        row = {
            "snapshotId": decision.snapshot_id,
            "timestamp": time.time(),
            "source": source,
            "mode": decision.mode,
            "ok": decision.ok,
            "blockers": list(decision.blockers),
            "warnings": list(decision.warnings),
            "payload": decision.payload,
            "mt5": {k: mt5_status.get(k) for k in ("connected", "tradeAllowed", "account", "server")},
            "market": {k: market.get(k) for k in ("symbol", "source", "price", "bid", "ask", "spread", "ageSeconds", "tickAgeSeconds")},
            "account": {k: account.get(k) for k in ("balance", "equity", "margin", "freeMargin")},
            "openPositionCount": len(open_positions),
            "dailyPnl": daily_pnl,
            "consecutiveLosses": consecutive_losses,
        }
        encoded = json.dumps(row, sort_keys=True, default=str) + "\n"
        with self._lock:
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
