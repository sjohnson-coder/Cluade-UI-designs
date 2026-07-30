from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PerformanceMemory:
    """Bot-only performance memory.

    Only trades stamped as GodMode bot trades are recorded into optimisation memory.
    This prevents manual MT5 trades or other EAs from corrupting strategy scoring,
    probability calibration, spread/slippage analysis and pyramiding unlock logic.
    """

    def __init__(self, path: str | Path = "data/godmode_memory.sqlite") -> None:
        self.path = Path(path)
        self.magic = int(os.getenv("GODMODE_MAGIC_NUMBER", "20250525"))
        self.comment_prefix = os.getenv("GODMODE_COMMENT_PREFIX", "GODMODE_")
        self.allow_manual = os.getenv("GODMODE_ALLOW_MANUAL_TRADE_MEMORY", "false").lower() == "true"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        try:
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

    def _init(self):
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, symbol TEXT, strategy TEXT, session TEXT, side TEXT,
                confidence REAL, spread REAL, slippage REAL, pnl REAL, r_multiple REAL, outcome TEXT,
                source TEXT, magic INTEGER, comment TEXT, bot_trade INTEGER DEFAULT 1
            )""")
            # Backward-compatible migrations for older local databases.
            cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
            for col, ddl in {
                "source": "ALTER TABLE trades ADD COLUMN source TEXT",
                "magic": "ALTER TABLE trades ADD COLUMN magic INTEGER",
                "comment": "ALTER TABLE trades ADD COLUMN comment TEXT",
                "bot_trade": "ALTER TABLE trades ADD COLUMN bot_trade INTEGER DEFAULT 1",
                "seeded": "ALTER TABLE trades ADD COLUMN seeded INTEGER DEFAULT 0",
                "broker_ticket": "ALTER TABLE trades ADD COLUMN broker_ticket TEXT",
            }.items():
                if col not in cols:
                    conn.execute(ddl)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_broker_ticket "
                "ON trades(broker_ticket) WHERE broker_ticket IS NOT NULL AND broker_ticket <> ''"
            )
            # Backfill: flag any pre-existing seed rows (inserted before the `seeded` column existed)
            # so they're excluded from live calibration/ranking too.
            conn.execute("UPDATE trades SET seeded=1 WHERE COALESCE(seeded,0)=0 AND comment = ?",
                         (f"{self.comment_prefix}seed",))
            conn.execute("""CREATE TABLE IF NOT EXISTS ai_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, event TEXT, detail TEXT, payload TEXT
            )""")
            conn.commit()

    def is_bot_trade(self, trade: dict[str, Any]) -> tuple[bool, str]:
        if self.allow_manual:
            return True, "manual memory override enabled"
        source = str(trade.get("source", "")).lower()
        comment = str(trade.get("comment", ""))
        magic_raw = trade.get("magic", trade.get("magicNumber"))
        try:
            magic = int(magic_raw) if magic_raw is not None else None
        except Exception:
            magic = None
        # Client-controlled flags and labels are not provenance. Only stamps
        # written into the broker execution itself are admissible evidence.
        if magic == self.magic:
            return True, "magic number matches"
        if comment.startswith(self.comment_prefix):
            return True, "comment prefix matches"
        return False, "trade was not stamped as a GodMode bot trade"

    def seed_if_empty(self):
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM trades WHERE bot_trade=1").fetchone()[0]
            if count:
                return
            samples = [
                ("XAUUSD", "Liquidity Sweep + Order Block Retest", "London", "BUY", 87, 0.12, 0.02, 631.42, 2.31, "WIN"),
                ("XAUUSD", "HTF Trend Continuation", "New York", "SELL", 82, 0.16, 0.05, 284.10, 1.18, "WIN"),
                ("XAUUSD", "London Open Breakout", "London", "BUY", 76, 0.24, 0.08, -146.20, -0.78, "LOSS"),
                ("XAUUSD", "VWAP Mean Reversion", "London Mid", "SELL", 71, 0.18, 0.04, 212.40, 1.05, "WIN"),
            ]
            for row in samples:
                # seeded=1 → these sample rows populate the UI on first run but are EXCLUDED from the
                # live-decision stats (calibration / ranking), so demo data can never fake a live edge.
                conn.execute(
                    "INSERT INTO trades (ts,symbol,strategy,session,side,confidence,spread,slippage,pnl,r_multiple,outcome,source,magic,comment,bot_trade,seeded) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), *row, "godmode_bot", self.magic, f"{self.comment_prefix}seed", 1, 1),
                )
            conn.commit()

    def record_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        ok, reason = self.is_bot_trade(trade)
        if not ok:
            return {"ok": False, "recorded": False, "rejected": True, "reason": reason, "memoryScope": "bot_only"}
        with self._write_lock, self._conn() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO trades (ts,symbol,strategy,session,side,confidence,spread,slippage,pnl,r_multiple,outcome,source,magic,comment,bot_trade,broker_ticket) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    datetime.now(timezone.utc).isoformat(),
                    trade.get("symbol", "XAUUSD"),
                    trade.get("strategy"),
                    trade.get("session"),
                    trade.get("side"),
                    trade.get("confidence"),
                    trade.get("spread"),
                    trade.get("slippage"),
                    trade.get("pnl"),
                    trade.get("rMultiple"),
                    trade.get("outcome"),
                    trade.get("source", "godmode_bot"),
                    int(trade.get("magic", self.magic) or self.magic),
                    str(trade.get("comment", f"{self.comment_prefix}record")),
                    1,
                    str(trade.get("ticket") or trade.get("positionId") or "") or None,
                ),
            )
            conn.commit()
            if cursor.rowcount == 0:
                return {
                    "ok": True,
                    "recorded": False,
                    "duplicate": True,
                    "memoryScope": "bot_only",
                }
        return {"ok": True, "recorded": True, "memoryScope": "bot_only"}

    def auto_journal(self, event: str, detail: str, payload: str = "") -> dict[str, Any]:
        with self._write_lock, self._conn() as conn:
            conn.execute("INSERT INTO ai_journal (ts,event,detail,payload) VALUES (?,?,?,?)", (datetime.now(timezone.utc).isoformat(), event, detail, payload))
            conn.commit()
        return {"ok": True, "event": event}

    def stats(self, live_only: bool = False) -> dict[str, Any]:
        """live_only=True → EXCLUDE seeded sample rows, so the engine's confidence calibration and
        strategy ranking learn ONLY from real bot trades. Default (UI) includes seeds for display."""
        self.seed_if_empty()
        where = "WHERE bot_trade=1" + (" AND COALESCE(seeded,0)=0" if live_only else "")
        with self._conn() as conn:
            rows = conn.execute(f"SELECT strategy, session, spread, slippage, pnl, r_multiple, outcome, confidence FROM trades {where}").fetchall()
        total = len(rows)
        wins = [r for r in rows if r[6] == "WIN" or (r[4] is not None and r[4] > 0)]
        by_strategy: dict[str, list] = {}
        by_session: dict[str, list] = {}
        by_session_strategy: dict[str, list] = {}   # "<session>|<strategy>" → rows (per-session learning)
        spreads: list[float] = []
        slips: list[float] = []
        calibration_bins: dict[str, dict[str, int]] = {}
        for r in rows:
            by_strategy.setdefault(r[0] or "Unknown", []).append(r)
            by_session.setdefault(r[1] or "Unknown", []).append(r)
            by_session_strategy.setdefault(f"{r[1] or 'Unknown'}|{r[0] or 'Unknown'}", []).append(r)
            if r[2] is not None:
                spreads.append(float(r[2]))
            if r[3] is not None:
                slips.append(float(r[3]))
            conf = float(r[7] or 0)
            bucket = f"{int(conf // 10) * 10}-{int(conf // 10) * 10 + 9}"
            calibration_bins.setdefault(bucket, {"total": 0, "wins": 0})
            calibration_bins[bucket]["total"] += 1
            if r[6] == "WIN" or (r[4] is not None and r[4] > 0):
                calibration_bins[bucket]["wins"] += 1

        def summarize(group: dict[str, list]):
            out = []
            for key, vals in group.items():
                w = [v for v in vals if v[6] == "WIN" or (v[4] is not None and v[4] > 0)]
                pnl = sum(float(v[4] or 0) for v in vals)
                out.append({"name": key, "trades": len(vals), "wins": len(w), "winRate": round(len(w) / max(len(vals), 1) * 100, 2), "pnl": round(pnl, 2)})
            return sorted(out, key=lambda x: x["pnl"], reverse=True)

        calibration = []
        # V12.74: numeric bucket order ("60-69" before "100-109"), not string order
        for bucket, data in sorted(calibration_bins.items(), key=lambda kv: int(kv[0].split("-")[0])):
            calibration.append({"bucket": bucket, "samples": data["total"], "actualWinRate": round(data["wins"] / max(data["total"], 1) * 100, 2)})
        return {
            "memoryScope": "bot_only",
            "totalTrades": total,
            "winRate": round(len(wins) / max(total, 1) * 100, 2),
            "strategyPerformance": summarize(by_strategy),
            "sessionPerformance": summarize(by_session),
            "sessionStrategyPerformance": summarize(by_session_strategy),
            "spreadMemory": {"avgSpread": round(sum(spreads) / max(len(spreads), 1), 3), "samples": len(spreads)},
            "slippageMemory": {"avgSlippage": round(sum(slips) / max(len(slips), 1), 3), "samples": len(slips)},
            "probabilityCalibration": calibration,
        }
