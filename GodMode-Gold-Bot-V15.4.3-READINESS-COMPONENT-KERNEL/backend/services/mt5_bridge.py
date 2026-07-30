from __future__ import annotations

import math
import os
import logging
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Any

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - MT5 is Windows/terminal dependent
    mt5 = None


SUCCESS_RETCODES = {10008, 10009, 10010}
TRADE_RETCODE_CLOSE_ONLY = 10044
LOGGER = logging.getLogger("godmode.mt5")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


class MT5Bridge:
    """Safe MT5 bridge — upgraded v3.

    Changes:
    - _ensure_initialized is cached (re-checks only every 10s to avoid hammering MT5).
    - copy_rates requests 250 candles (was 120) so EMA-200 is properly seeded.
    - market_snapshot now also fetches H1 candles for multi-timeframe analysis.
    - closed_bot_trades returns newest-first (was oldest-first).
    - closed_bot_trades no longer skips trades based on profit==0; now filters
      only DEAL_ENTRY_OUT records so opens don't pollute history.
    """

    def __init__(self) -> None:
        self.live_enabled = os.getenv("GODMODE_ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.auto_trading_enabled = os.getenv("GODMODE_AUTO_TRADING", "false").lower() == "true"
        self.symbol = os.getenv("MT5_SYMBOL", "XAUUSD")
        self.magic = int(os.getenv("GODMODE_MAGIC_NUMBER", "20250525"))
        self.comment_prefix = os.getenv("GODMODE_COMMENT_PREFIX", "GODMODE_")
        self.max_deviation = int(os.getenv("GODMODE_MAX_DEVIATION", "30"))
        self.terminal_path = os.getenv("MT5_TERMINAL_PATH", "").strip()
        self.login = os.getenv("MT5_LOGIN", "").strip()
        self.password = os.getenv("MT5_PASSWORD", "").strip()
        self.server = os.getenv("MT5_SERVER", "").strip()
        self.last_connect_message = "Not connected yet."
        # Connection cache to avoid hammering mt5.initialize()
        self._init_ok: bool = False
        self._init_detail: str = ""
        # Market open/closed detection — differential tick-staleness (timezone-safe): we watch
        # whether the broker's last-tick TIME keeps advancing, not its absolute value.
        self._last_tick_value: float = 0.0
        self._last_tick_change: float = 0.0
        self._init_at: float = 0.0
        self._init_ttl: float = 10.0  # re-check every 10 seconds
        # V13.9 reconnect hardening: consecutive failure counter. When >0, the next attempt does a
        # FULL mt5.shutdown() before initialize() — the documented cure for a wedged IPC session
        # (terminal alive, pipe dead), which plain re-initialize() cannot heal.
        self._init_fail_count: int = 0
        # Short-TTL market-snapshot cache. The UI polls several endpoints every ~5s and each one used
        # to trigger its OWN 7-call multi-timeframe MT5 fetch (tick + symbol_info + M15/H1/H4/D1,
        # ~1200 candles). Caching the built snapshot for a few seconds lets all the near-simultaneous
        # polls in one cycle share ONE fetch — cutting MT5 IPC ~70% with no meaningful staleness
        # (M15+ candles don't move in a few seconds; order fills re-read the live tick at execution).
        # TTL = 2.5s: short enough that the 3s auto-PROTECTION loop always refetches fresh data (never
        # manages trades on stale prices), long enough to collapse the UI's simultaneous snapshot polls
        # (AI Agent fires action-matrix + market-snapshot together via Promise.all, plus the topbar) into
        # one fetch. Override with GODMODE_SNAPSHOT_TTL=0 to disable caching entirely.
        self._snap_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._snap_cache_at: dict[tuple[str, str], float] = {}
        self._snap_ttl: float = float(os.getenv("GODMODE_SNAPSHOT_TTL", "2.5") or 2.5)
        # V12.58: MetaTrader5 Python IPC is not reliably safe under many concurrent
        # calls from UI polling + auto management + Telegram. Serialize all MT5
        # terminal access to prevent the dashboard/pages from freezing after hours.
        self._ipc_lock = threading.RLock()
        self._connect_lock = threading.RLock()
        self._last_hard_reconnect_at: float = 0.0
        self._hard_reconnect_cooldown: float = 20.0
        # V12.61: open_positions previously called history_deals_get once PER open
        # position to approximate booked commission/swap. With Burst mode this can
        # mean 20-50 expensive history scans every dashboard poll, causing the UI to
        # freeze. Cache entry costs and batch-fetch them once per short window.
        self._entry_cost_cache: dict[str, float] = {}
        self._entry_cost_cache_at: float = 0.0
        self._entry_cost_cache_ttl: float = float(os.getenv("GODMODE_ENTRY_COST_CACHE_TTL", "20") or 20)
        # A broker can temporarily switch a symbol/account to close-only. Retcode
        # 10044 is deterministic, so repeated entry retries only hammer the trade
        # server and can stall burst/multi-target flows. Keep a symbol-scoped,
        # in-memory cooldown while still allowing closes and protection changes.
        self.close_only_cooldown_seconds: float = max(
            30.0,
            _safe_float(
                os.getenv("GODMODE_BROKER_CLOSE_ONLY_COOLDOWN_SECONDS", "300"),
                300.0,
            ),
        )
        self._broker_entry_state_lock = threading.RLock()
        self._broker_close_only_by_symbol: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _symbol_key(symbol: str) -> str:
        return str(symbol or "").strip().upper()

    def broker_entry_cooldown(self, symbol: str | None = None) -> dict[str, Any]:
        """Return the current symbol-scoped close-only cooldown without broker I/O."""
        key = self._symbol_key(symbol or self.symbol)
        now = time.time()
        with self._broker_entry_state_lock:
            state = dict(self._broker_close_only_by_symbol.get(key) or {})
            until = float(state.get("untilEpoch") or 0.0)
            if until <= now:
                self._broker_close_only_by_symbol.pop(key, None)
                return {
                    "active": False,
                    "symbol": key,
                    "classification": "BROKER_CLOSE_ONLY",
                    "retcode": TRADE_RETCODE_CLOSE_ONLY,
                    "retryAfterSeconds": 0,
                }
            state["active"] = True
            state["retryAfterSeconds"] = max(1, int(math.ceil(until - now)))
            return state

    def _activate_close_only_cooldown(
        self,
        symbol: str,
        source: str,
        detail: str = "",
    ) -> dict[str, Any]:
        key = self._symbol_key(symbol)
        now = time.time()
        until = now + self.close_only_cooldown_seconds
        with self._broker_entry_state_lock:
            previous = self._broker_close_only_by_symbol.get(key) or {}
            until = max(until, float(previous.get("untilEpoch") or 0.0))
            state = {
                "active": True,
                "symbol": key,
                "classification": "BROKER_CLOSE_ONLY",
                "retcode": TRADE_RETCODE_CLOSE_ONLY,
                "source": str(source or "broker"),
                "detail": str(detail or "Broker permits position-closing operations only.")[:500],
                "detectedAtEpoch": now,
                "detectedAtUtc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "untilEpoch": until,
                "untilUtc": datetime.fromtimestamp(until, timezone.utc).isoformat(),
                "durationSeconds": int(self.close_only_cooldown_seconds),
                "retryAfterSeconds": max(1, int(math.ceil(until - now))),
            }
            self._broker_close_only_by_symbol[key] = state
            return dict(state)

    @staticmethod
    def _close_only_fields(cooldown: dict[str, Any]) -> dict[str, Any]:
        return {
            "blocked": True,
            "brokerCloseOnly": True,
            "classification": "BROKER_CLOSE_ONLY",
            "retcode": TRADE_RETCODE_CLOSE_ONLY,
            "cooldown": cooldown,
        }

    @staticmethod
    def _admission_fields(detail: dict[str, Any]) -> dict[str, Any]:
        keys = {
            "brokerCloseOnly",
            "classification",
            "retcode",
            "cooldown",
            "tradeMode",
            "tradeModeName",
            "marketClosed",
            "marketStateUnavailable",
            "marketState",
        }
        return {key: detail[key] for key in keys if key in detail}

    def _entry_market_admission(self, symbol: str) -> tuple[bool, dict[str, Any]]:
        """Fresh, fail-closed market-state gate for every live entry submission."""
        try:
            state = self.market_open(symbol)
            if not isinstance(state, dict) or not isinstance(state.get("open"), bool):
                raise ValueError("market_open returned a malformed state")
        except Exception as exc:
            LOGGER.exception("MT5 market-state probe failed symbol=%s", symbol)
            state = {
                "open": False,
                "reason": f"Market-state probe failed closed: {type(exc).__name__}: {exc}",
                "source": "error",
                "error": True,
            }
        if state.get("open") is True:
            return True, {"marketState": state}
        unavailable = bool(state.get("error") or state.get("source") == "error")
        return False, {
            "blocked": True,
            "marketClosed": not unavailable,
            "marketStateUnavailable": unavailable,
            "marketState": state,
            "message": (
                "New live entry blocked: authoritative market state is unavailable."
                if unavailable
                else f"New live entry blocked: {state.get('reason') or 'market is closed'}."
            ),
        }

    def configure(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        self.symbol = str(payload.get("symbol", self.symbol) or self.symbol)
        self.magic = _safe_int(payload.get("magicNumber", payload.get("magic", self.magic)), self.magic)
        self.comment_prefix = str(payload.get("commentPrefix", self.comment_prefix) or self.comment_prefix)
        self.max_deviation = _safe_int(payload.get("maxDeviation", self.max_deviation), self.max_deviation)
        new_path = str(payload.get("terminalPath", self.terminal_path) or "").strip()
        new_login = str(payload.get("login", self.login) or "").strip()
        new_password = str(payload.get("password", self.password) or "").strip()
        new_server = str(payload.get("server", self.server) or "").strip()
        # Invalidate init cache if connection params changed
        if new_path != self.terminal_path or new_login != self.login or new_server != self.server:
            self._init_ok = False
            self._init_at = 0.0
        self.terminal_path = new_path
        self.login = new_login
        self.password = new_password
        self.server = new_server
        # V14.1.16 SAFETY FIX — these two lines both wrote self.live_enabled, and because
        # dryRun was evaluated LAST it silently overrode an explicit disable. The settings
        # payload always carries BOTH keys, so `liveTradingEnabled=False, dryRun=False`
        # resolved to live_enabled=True — arming the broker bridge for real orders even
        # though the operator had explicitly turned Live Trading off. Unchecking "Dry Run"
        # in the UI while leaving "Live Trading" off was enough to reach it.
        # Correct semantics: live ONLY when explicitly enabled AND not in dry run.
        if "liveTradingEnabled" in payload or "dryRun" in payload:
            explicit_live = bool(payload.get("liveTradingEnabled", self.live_enabled))
            in_dry_run = bool(payload.get("dryRun", not self.live_enabled))
            self.live_enabled = explicit_live and not in_dry_run
        if "autoTradingEnabled" in payload:
            self.auto_trading_enabled = bool(payload.get("autoTradingEnabled"))
        return self.status()

    def set_live_enabled(self, enabled: bool) -> dict[str, Any]:
        self.live_enabled = bool(enabled)
        return self.status()

    def set_auto_trading_enabled(self, enabled: bool) -> dict[str, Any]:
        self.auto_trading_enabled = bool(enabled)
        return self.status()

    def _ensure_initialized(self) -> tuple[bool, str]:
        if mt5 is None:
            return False, "MetaTrader5 package unavailable. Install requirements on Windows and keep MT5 open."
        with self._connect_lock:
            now = __import__("time").time()
            # Use cached result if fresh — avoids hammering mt5.initialize() on every API call.
            if self._init_ok and (now - self._init_at) < self._init_ttl:
                return True, self._init_detail
            return self._ensure_initialized_locked(now)

    def _ensure_initialized_locked(self, now: float) -> tuple[bool, str]:
        try:
            # V13.9: if the last attempt failed, tear the session down completely before retrying.
            # A wedged pipe makes bare initialize() fail forever; shutdown+initialize heals it, and
            # with terminal_path set it can even RELAUNCH a closed terminal.
            if self._init_fail_count > 0:
                try:
                    mt5.shutdown()
                except Exception as _suppressed_exc:
                    logging.getLogger(__name__).warning("Recoverable failure in mt5_bridge.py:144: %s", _suppressed_exc)
            init_kwargs: dict[str, Any] = {}
            if self.terminal_path:
                init_kwargs["path"] = self.terminal_path
            if self.login and self.password and self.server:
                init_kwargs.update({"login": int(float(self.login)), "password": self.password, "server": self.server})
            ok = mt5.initialize(**init_kwargs) if init_kwargs else mt5.initialize()
            if ok and self.login and self.password and self.server:
                login_ok = mt5.login(int(float(self.login)), password=self.password, server=self.server)
                if not login_ok:
                    msg = f"MT5 login failed: {mt5.last_error()}"
                    self.last_connect_message = msg
                    self._init_ok, self._init_detail, self._init_at = False, msg, now
                    self._init_fail_count += 1
                    return False, msg
            if ok:
                # V13.9: initialize() returning True does NOT mean the broker link is alive — the
                # terminal can be open but disconnected. Caching that as success made the watchdog
                # stand down while still blind. Verify the actual broker connection before
                # declaring victory; otherwise keep the failure state so reconnection keeps trying.
                try:
                    _t = mt5.terminal_info()
                    _broker_ok = bool(_t and getattr(_t, "connected", False))
                except Exception:
                    _broker_ok = False
                if not _broker_ok:
                    msg = "MT5 terminal initialized but NOT connected to broker (check terminal login / network)."
                    self.last_connect_message = msg
                    self._init_ok, self._init_detail, self._init_at = False, msg, now
                    self._init_fail_count += 1
                    return False, msg
                self.last_connect_message = "initialized"
                self._init_ok, self._init_detail, self._init_at = True, "initialized", now
                self._init_fail_count = 0
                return True, "initialized"
            msg = f"MT5 initialize failed: {mt5.last_error()}"
            self.last_connect_message = msg
            self._init_ok, self._init_detail, self._init_at = False, msg, now
            self._init_fail_count += 1
            return False, msg
        except Exception as exc:
            self._init_ok, self._init_detail, self._init_at = False, str(exc), now
            self.last_connect_message = str(exc)
            self._init_fail_count += 1
            return False, str(exc)

    def mark_dead(self, reason: str = "terminal_unreachable") -> None:
        """V13.9 — invalidate the init cache the moment the terminal stops answering, instead of
        trusting a cached 'initialized' for up to init_ttl seconds while the terminal is a corpse.
        The next _ensure_initialized() then performs a real (shutdown-first) reconnect attempt."""
        self._init_ok = False
        self._init_detail = reason
        self._init_fail_count = max(1, self._init_fail_count)
        self.invalidate_snapshot_cache()

    def hard_reconnect(self) -> dict[str, Any]:
        """Serialized, cooldown-protected teardown/reinitialize for a genuinely dead IPC session."""
        with self._connect_lock:
            now = time.time()
            if self._init_ok and (now - self._init_at) < self._init_ttl:
                return {"ok": True, "detail": "already_connected"}
            if now - self._last_hard_reconnect_at < self._hard_reconnect_cooldown:
                wait = self._hard_reconnect_cooldown - (now - self._last_hard_reconnect_at)
                return {"ok": False, "detail": f"reconnect_cooldown:{wait:.1f}s"}
            self._last_hard_reconnect_at = now
            if mt5 is not None:
                try:
                    mt5.shutdown()
                except Exception as _suppressed_exc:
                    logging.getLogger(__name__).warning("Recoverable MT5 shutdown failure: %s", _suppressed_exc)
            self._init_ok = False
            self._init_fail_count = max(1, self._init_fail_count)
            self.invalidate_snapshot_cache()
            ok, detail = self._ensure_initialized_locked(time.time())
            return {"ok": ok, "detail": detail}

    def invalidate_snapshot_cache(self) -> None:
        """Drop the short-TTL market-snapshot cache so the next call fetches fresh from MT5
        (used on connect / disconnect / manual refresh)."""
        self._snap_cache.clear()
        self._snap_cache_at.clear()

    def connect(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.configure(payload or {})
        self.invalidate_snapshot_cache()
        ok, detail = self._ensure_initialized()
        return {"ok": ok, "detail": detail, "status": self.status()}

    def disconnect(self) -> dict[str, Any]:
        if mt5 is not None:
            try:
                mt5.shutdown()
            except Exception as _suppressed_exc:
                logging.getLogger(__name__).warning("Recoverable failure in mt5_bridge.py:229: %s", _suppressed_exc)
        self.invalidate_snapshot_cache()
        self.last_connect_message = "MT5 shutdown requested from UI."
        return {"ok": True, "status": self.status()}

    def _is_bot_record(self, item: Any) -> bool:
        magic = getattr(item, "magic", None)
        comment = str(getattr(item, "comment", "") or "")
        return _safe_int(magic, -1) == self.magic or comment.startswith(self.comment_prefix)

    def _exit_reason_label(self, deal: Any, net_pnl: float | None = None) -> str:
        """Map an MT5 closing-deal reason code to a human label (TP/SL/manual/etc.).

        V13.6: MT5 reports DEAL_REASON_SL for ANY stop-order fill — including a TRAILING or
        BREAK-EVEN stop that closed the trade IN PROFIT. The old label said "Stop loss hit" on
        those too, so Johnson's journal showed 130 winners labelled "Stop loss hit" and every
        loser as "Closed by bot" — the labels read exactly backwards and made the journal
        actively misleading. When we know the trade's P&L we now say what actually happened.
        """
        if mt5 is None:
            return "Closed"
        code = _safe_int(getattr(deal, "reason", -1), -1)
        if code == getattr(mt5, "DEAL_REASON_SL", 4) and net_pnl is not None:
            # a stop that fired in profit is a trailing/BE stop banking the trade, not a loss
            return "Trailing/BE stop (profit)" if net_pnl > 0 else "Stop loss hit"
        mapping = {
            getattr(mt5, "DEAL_REASON_CLIENT", 0): "Closed manually",
            getattr(mt5, "DEAL_REASON_MOBILE", 1): "Closed manually (mobile)",
            getattr(mt5, "DEAL_REASON_WEB", 2): "Closed manually (web)",
            getattr(mt5, "DEAL_REASON_EXPERT", 3): "Closed by bot",
            getattr(mt5, "DEAL_REASON_SL", 4): "Stop loss hit",
            getattr(mt5, "DEAL_REASON_TP", 5): "Take profit hit",
            getattr(mt5, "DEAL_REASON_SO", 6): "Stop out (margin)",
        }
        return mapping.get(code, "Closed")

    def status(self) -> dict[str, Any]:
        ok, detail = self._ensure_initialized()
        if not ok:
            return {
                "available": mt5 is not None,
                "connected": False,
                "tradeAllowed": False,
                "liveTradingEnabled": self.live_enabled,
                "dryRun": not self.live_enabled,
                "autoTradingEnabled": self.auto_trading_enabled,
                "source": "not_connected",
                "detail": detail,
                "symbol": self.symbol,
                "magic": self.magic,
                "commentPrefix": self.comment_prefix,
                "terminalPath": self.terminal_path,
                "hasPassword": bool(self.password),
                "brokerEntryCooldown": self.broker_entry_cooldown(self.symbol),
            }
        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            connected = bool(terminal and getattr(terminal, "connected", False))
            if not connected:
                # V13.9: init said OK but the terminal is not answering / not broker-connected.
                # Kill the cached success NOW so the very next call attempts a real reconnect,
                # rather than serving "initialized" for the rest of the TTL window.
                self.mark_dead("terminal_not_connected")
            return {
                "available": True,
                "connected": connected,
                "tradeAllowed": bool(terminal and getattr(terminal, "trade_allowed", False)),
                "liveTradingEnabled": self.live_enabled,
                "dryRun": not self.live_enabled,
                "autoTradingEnabled": self.auto_trading_enabled,
                "source": "mt5" if connected else "not_connected",
                "detail": self.last_connect_message if self.last_connect_message != "initialized" and not connected else ("Connected" if connected else "MT5 terminal is open but not connected to broker."),
                "terminalName": getattr(terminal, "name", None) if terminal else None,
                "terminalDataPath": getattr(terminal, "data_path", None) if terminal else None,
                "terminalCommonDataPath": getattr(terminal, "commondata_path", None) if terminal else None,
                "terminalConnected": bool(getattr(terminal, "connected", False)) if terminal else False,
                "server": getattr(account, "server", None) if account else None,
                "login": getattr(account, "login", None) if account else None,
                "broker": getattr(account, "company", None) if account else None,
                "currency": getattr(account, "currency", None) if account else None,
                "leverage": getattr(account, "leverage", None) if account else None,
                "symbol": self.symbol,
                "magic": self.magic,
                "commentPrefix": self.comment_prefix,
                "terminalPath": self.terminal_path,
                "hasPassword": bool(self.password),
                "brokerEntryCooldown": self.broker_entry_cooldown(self.symbol),
            }
        except Exception as exc:
            return {
                "available": True,
                "connected": False,
                "tradeAllowed": False,
                "liveTradingEnabled": self.live_enabled,
                "dryRun": not self.live_enabled,
                "autoTradingEnabled": self.auto_trading_enabled,
                "source": "error",
                "detail": str(exc),
                "symbol": self.symbol,
                "magic": self.magic,
                "commentPrefix": self.comment_prefix,
                "terminalPath": self.terminal_path,
                "hasPassword": bool(self.password),
                "brokerEntryCooldown": self.broker_entry_cooldown(self.symbol),
            }

    def is_hedging(self) -> bool:
        """True only on a real MT5 RETAIL_HEDGING account (where independent
        opposite/multiple positions on one symbol are allowed)."""
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None:
            return False
        try:
            info = mt5.account_info()
            return bool(info and getattr(info, "margin_mode", None) == getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2))
        except Exception:
            return False

    def account_snapshot(self) -> dict[str, Any]:
        ok, detail = self._ensure_initialized()
        if not ok:
            return self._empty_account(detail)
        try:
            info = mt5.account_info()
            if not info:
                return self._empty_account(f"MT5 account_info unavailable: {mt5.last_error()}")
            balance = _safe_float(getattr(info, "balance", 0.0))
            equity = _safe_float(getattr(info, "equity", 0.0))
            trade_mode_raw = getattr(info, "trade_mode", None)
            try:
                trade_mode = int(trade_mode_raw) if trade_mode_raw is not None else None
            except (TypeError, ValueError):
                trade_mode = None
            demo_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
            contest_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1))
            real_mode = int(getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2))
            if trade_mode == demo_mode:
                account_mode_name, account_type = "DEMO", "demo"
            elif trade_mode == contest_mode:
                account_mode_name, account_type = "CONTEST", "contest"
            elif trade_mode == real_mode:
                account_mode_name, account_type = "REAL", "real"
            else:
                account_mode_name, account_type = "UNKNOWN", "unknown"
            margin = _safe_float(getattr(info, "margin", 0.0))
            free = _safe_float(getattr(info, "margin_free", 0.0))
            daily_pnl = self.bot_history_pnl(days=1)
            risk_detail = self.open_bot_risk_details()
            open_risk = float(risk_detail["riskCash"])
            open_risk_pct = (
                100.0
                if risk_detail["unprotectedPositions"]
                else round((open_risk / equity) * 100, 2) if equity else 0.0
            )
            return {
                "source": "mt5",
                "connected": True,
                "balance": round(balance, 2),
                "equity": round(equity, 2),
                "dailyPnl": round(daily_pnl, 2),
                "dailyPnlPct": round((daily_pnl / balance) * 100, 2) if balance else 0.0,
                "openRisk": round(open_risk, 2),
                "openRiskPct": open_risk_pct,
                "openRiskKnown": not bool(risk_detail["unprotectedPositions"]),
                "unprotectedPositions": risk_detail["unprotectedPositions"],
                "riskCalculationFallbacks": risk_detail["fallbackCalculations"],
                "freeMargin": round(free, 2),
                "margin": round(margin, 2),
                "marginHealth": max(0, min(100, round((free / equity) * 100, 0))) if equity else 0,
                "currency": getattr(info, "currency", ""),
                "login": getattr(info, "login", None),
                "server": getattr(info, "server", None),
                "broker": getattr(info, "company", None),
                "leverage": getattr(info, "leverage", None),
                "accountTradeMode": trade_mode,
                "accountTradeModeName": account_mode_name,
                "accountType": account_type,
                "demo": account_type == "demo",
                "contest": account_type == "contest",
                "real": account_type == "real",
            }
        except Exception as exc:
            return self._empty_account(str(exc))

    def _empty_account(self, detail: str) -> dict[str, Any]:
        return {
            "source": "not_connected",
            "connected": False,
            "detail": detail,
            "balance": 0.0,
            "equity": 0.0,
            "dailyPnl": 0.0,
            "dailyPnlPct": 0.0,
            "openRisk": 0.0,
            "openRiskPct": 0.0,
            "openRiskKnown": False,
            "unprotectedPositions": 0,
            "riskCalculationFallbacks": 0,
            "freeMargin": 0.0,
            "margin": 0.0,
            "marginHealth": 0,
            "currency": "",
            "login": None,
            "server": None,
            "broker": None,
            "leverage": None,
            "accountTradeMode": None,
            "accountTradeModeName": "UNKNOWN",
            "accountType": "unknown",
            "demo": False,
            "contest": False,
            "real": False,
        }

    def market_snapshot(self, symbol: str | None = None, timeframe: str = "M15") -> dict[str, Any]:
        symbol = symbol or self.symbol
        key = (symbol, timeframe)
        # Serve a fresh-enough cached snapshot so a burst of polls shares one MT5 fetch.
        if self._snap_ttl > 0:
            hit = self._snap_cache.get(key)
            if hit is not None and (time.monotonic() - self._snap_cache_at.get(key, 0.0)) < self._snap_ttl:
                return hit
        ok, detail = self._ensure_initialized()
        if not ok:
            return self._empty_market(symbol, timeframe, detail)
        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return self._empty_market(symbol, timeframe, f"No live tick available for {symbol}")
            bid = _safe_float(getattr(tick, "bid", 0.0))
            ask = _safe_float(getattr(tick, "ask", 0.0))
            price = ask if ask else bid
            # Return spread in PRICE UNITS (same as max_spread in settings = 0.40 USD)
            # NOT in raw MT5 points (which would give 26 for a 0.26 USD spread)
            spread_points = round(ask - bid, 3) if ask and bid else 0.0
            # Deep history so EMA-200 is fully seeded and true HTF structure is reliable.
            # M15 500 (~5 days), H1 300 (~12 days), plus H4 + D1 for institutional bias.
            candles = self.copy_rates(symbol=symbol, timeframe=timeframe, count=500)
            h1_candles = self.copy_rates(symbol=symbol, timeframe="H1", count=300)
            h4_candles = self.copy_rates(symbol=symbol, timeframe="H4", count=200)
            d1_candles = self.copy_rates(symbol=symbol, timeframe="D1", count=200)
            atr = self._atr(candles)
            trend = self._trend_label(candles)
            snapshot = {
                "source": "mt5",
                "connected": True,
                "symbol": symbol,
                "price": round(price, 3),
                "bid": round(bid, 3),
                "ask": round(ask, 3),
                "change": 0.0,
                "changePct": 0.0,
                "timeframe": timeframe,
                "session": self.current_session(),
                "volatility": "High" if atr > 20 else "Normal" if atr else "Unknown",
                "spread": spread_points,
                "atr14": round(atr, 3),
                "regime": trend,
                "activeStrategy": "Awaiting AI confirmation" if candles else "Waiting for live candles",
                "confidence": 0,
                "side": "WAIT",
                "candles": candles,
                "h1Candles": h1_candles,
                "h4Candles": h4_candles,
                "d1Candles": d1_candles,
                "sparkline": [{"x": i, "value": c["close"]} for i, c in enumerate(candles[-40:])],
                "tickTime": int(getattr(tick, "time", 0) or 0),
                "tickTimeMsc": int(getattr(tick, "time_msc", 0) or 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._snap_cache[key] = snapshot
            self._snap_cache_at[key] = time.monotonic()
            return snapshot
        except Exception as exc:
            return self._empty_market(symbol, timeframe, str(exc))

    def _empty_market(self, symbol: str, timeframe: str, detail: str) -> dict[str, Any]:
        return {
            "source": "not_connected",
            "connected": False,
            "detail": detail,
            "symbol": symbol,
            "price": None,
            "bid": None,
            "ask": None,
            "change": 0.0,
            "changePct": 0.0,
            "timeframe": timeframe,
            "session": self.current_session(),
            "volatility": "Unknown",
            "spread": None,
            "atr14": 0.0,
            "regime": "Waiting for MT5 connection",
            "activeStrategy": "No live data",
            "confidence": 0,
            "side": "WAIT",
            "candles": [],
            "h1Candles": [],
            "h4Candles": [],
            "d1Candles": [],
            "sparkline": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _schedule_open(self) -> tuple[bool, str]:
        """Deterministic, timezone-safe WEEKEND schedule for spot gold / FX (UTC). Spot gold trades
        ~24/5, so the unambiguous 'closed for the day/week' window is the weekend. Intraday halts and
        the brief daily maintenance break are detected by live tick-staleness instead (broker-exact)."""
        now = datetime.now(timezone.utc)
        wd, hour = now.weekday(), now.hour  # Mon=0 .. Sun=6
        if wd == 5:
            return False, "Weekend — market reopens Sunday ~22:00 UTC"
        if wd == 6 and hour < 22:
            return False, "Weekend — market reopens Sunday ~22:00 UTC"
        if wd == 4 and hour >= 21:
            return False, "Weekend close — market closed Friday 21:00 UTC"
        return True, "Open"

    def market_open(self, symbol: str | None = None) -> dict[str, Any]:
        """Is the symbol's market open? The UTC weekend schedule is authoritative for the weekend;
        when connected, live tick-staleness (no new tick for 5+ minutes) additionally catches
        intraday halts and the daily break. Returns {open, reason, source}."""
        try:
            sched_open, sched_reason = self._schedule_open()
            ok, _ = self._ensure_initialized()
            if not ok or mt5 is None:
                return {"open": sched_open, "reason": sched_reason, "source": "schedule"}
            if not sched_open:
                return {"open": False, "reason": sched_reason, "source": "schedule"}
            tick = mt5.symbol_info_tick(symbol or self.symbol)
            if tick is None:
                return {
                    "open": False,
                    "reason": "Market-state probe failed closed: broker returned no current tick.",
                    "source": "error",
                    "error": True,
                }
            t = float(getattr(tick, "time", 0) or 0) if tick else 0.0
            now = time.time()
            if t and t != self._last_tick_value:
                self._last_tick_value = t
                self._last_tick_change = now
            elif self._last_tick_change == 0.0:
                self._last_tick_change = now  # first observation — start the clock
            stale = bool(self._last_tick_change) and (now - self._last_tick_change) > 300
            if stale:
                return {"open": False, "reason": "No new ticks for 5+ min — market closed or halted", "source": "tick"}
            return {"open": True, "reason": "Open", "source": "tick"}
        except Exception as exc:
            LOGGER.exception("MT5 market_open failed symbol=%s", symbol or self.symbol)
            return {
                "open": False,
                "reason": f"Market-state probe failed closed: {type(exc).__name__}: {exc}",
                "source": "error",
                "error": True,
            }

    def current_session(self) -> str:
        hour = datetime.now(timezone.utc).hour
        if 7 <= hour < 12:
            return "London"
        if 12 <= hour < 17:
            return "London / New York"
        if 17 <= hour < 22:
            return "New York"
        if 22 <= hour or hour < 7:
            return "Asia"
        return "Unknown"

    def copy_rates(self, symbol: str, timeframe: str = "M15", count: int = 120) -> list[dict[str, Any]]:
        if mt5 is None:
            return []
        tf = {
            "M1": getattr(mt5, "TIMEFRAME_M1", 1),
            "M5": getattr(mt5, "TIMEFRAME_M5", 5),
            "M15": getattr(mt5, "TIMEFRAME_M15", 15),
            "M30": getattr(mt5, "TIMEFRAME_M30", 30),
            "H1": getattr(mt5, "TIMEFRAME_H1", 60),
            "H4": getattr(mt5, "TIMEFRAME_H4", 240),
            "D1": getattr(mt5, "TIMEFRAME_D1", 1440),
        }.get(timeframe.upper(), getattr(mt5, "TIMEFRAME_M15", 15))
        try:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is None:
                return []
            out: list[dict[str, Any]] = []
            closes: list[float] = []
            for r in rates:
                close = _safe_float(r["close"])
                closes.append(close)
                out.append({
                    "time": int(r["time"]),
                    "timeLabel": datetime.fromtimestamp(int(r["time"]), timezone.utc).strftime("%H:%M"),
                    "open": round(_safe_float(r["open"]), 3),
                    "high": round(_safe_float(r["high"]), 3),
                    "low": round(_safe_float(r["low"]), 3),
                    "close": round(close, 3),
                    "tickVolume": int(r["tick_volume"]),
                })
            ema20 = self._ema(closes, 20)
            ema50 = self._ema(closes, 50)
            ema200 = self._ema(closes, min(200, max(2, len(closes))))
            for i, row in enumerate(out):
                row["ema20"] = round(ema20[i], 3) if i < len(ema20) else row["close"]
                row["ema50"] = round(ema50[i], 3) if i < len(ema50) else row["close"]
                row["ema200"] = round(ema200[i], 3) if i < len(ema200) else row["close"]
            return out
        except Exception:
            return []

    def latest_tick(self, symbol: str | None = None) -> dict[str, Any]:
        """Return one canonical live tick with millisecond precision.

        This is intentionally cheaper than a historical tick-range request and is
        used by the priority intent lane to keep the forming candle and execution
        price current between cached candle refreshes.
        """
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None:
            return {}
        selected = str(symbol or self.symbol)
        try:
            if hasattr(mt5, "symbol_select") and not mt5.symbol_select(selected, True):
                return {}
            tick = mt5.symbol_info_tick(selected)
            if tick is None:
                return {}
            epoch = int(getattr(tick, "time", 0) or 0)
            time_msc = int(getattr(tick, "time_msc", 0) or getattr(tick, "timeMsc", 0) or epoch * 1000)
            bid = _safe_float(getattr(tick, "bid", 0.0))
            ask = _safe_float(getattr(tick, "ask", 0.0))
            last = _safe_float(getattr(tick, "last", 0.0))
            return {
                "time": epoch or int(time_msc / 1000),
                "time_msc": time_msc,
                "timeMsc": time_msc,
                "bid": bid,
                "ask": ask,
                "last": last,
                "volume": _safe_float(getattr(tick, "volume", 0.0)),
                "flags": _safe_int(getattr(tick, "flags", 0)),
                "spread": round(max(0.0, ask - bid), 8) if ask > 0 and bid > 0 else 0.0,
            }
        except Exception:
            LOGGER.exception("MT5 latest-tick fetch failed symbol=%s", selected)
            return {}

    def copy_ticks_range(self, symbol: str, start_epoch: float, end_epoch: float) -> list[dict[str, Any]]:
        """Return chronological executable bid/ask ticks for deterministic replay."""
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None:
            return []
        try:
            start = datetime.fromtimestamp(float(start_epoch), timezone.utc)
            end = datetime.fromtimestamp(float(end_epoch), timezone.utc)
            rows = mt5.copy_ticks_range(symbol, start, end, getattr(mt5, "COPY_TICKS_ALL", 0))
            if rows is None:
                return []
            out: list[dict[str, Any]] = []
            for row in rows:
                if isinstance(row, dict):
                    getter = row.get
                else:
                    getter = lambda key, default=0: getattr(row, key, default)
                epoch = int(getter("time", 0) or 0)
                time_msc = int(getter("time_msc", 0) or epoch * 1000)
                out.append({
                    "time": epoch,
                    # Canonical snake_case plus the legacy camelCase alias.  The
                    # early-momentum engines require millisecond precision; falling
                    # back to integer seconds destroys velocity and acceleration.
                    "time_msc": time_msc,
                    "timeMsc": time_msc,
                    "bid": _safe_float(getter("bid", 0.0)),
                    "ask": _safe_float(getter("ask", 0.0)),
                    "last": _safe_float(getter("last", 0.0)),
                    "volume": _safe_float(getter("volume", 0.0)),
                    "flags": _safe_int(getter("flags", 0)),
                })
            out.sort(key=lambda tick: int(tick.get("timeMsc") or 0))
            return out
        except Exception:
            LOGGER.exception("MT5 tick-range fetch failed symbol=%s", symbol)
            return []

    def _ema(self, values: list[float], period: int) -> list[float]:
        if not values:
            return []
        alpha = 2 / (period + 1)
        out = [values[0]]
        for v in values[1:]:
            out.append(alpha * v + (1 - alpha) * out[-1])
        return out

    def _atr(self, candles: list[dict[str, Any]], period: int = 14) -> float:
        if len(candles) < 2:
            return 0.0
        trs = []
        prev_close = candles[0]["close"]
        for c in candles[1:]:
            high, low, close = _safe_float(c["high"]), _safe_float(c["low"]), _safe_float(c["close"])
            trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
            prev_close = close
        return sum(trs[-period:]) / max(1, min(period, len(trs)))

    def _trend_label(self, candles: list[dict[str, Any]]) -> str:
        if len(candles) < 50:
            return "Collecting live candles"
        last = candles[-1]
        close = _safe_float(last.get("close"))
        ema20 = _safe_float(last.get("ema20"))
        ema50 = _safe_float(last.get("ema50"))
        ema200 = _safe_float(last.get("ema200"))
        if close > ema20 > ema50 > ema200:
            return "Strong Bullish Trend"
        if close < ema20 < ema50 < ema200:
            return "Strong Bearish Trend"
        if close > ema50:
            return "Weak Bullish Trend"
        if close < ema50:
            return "Weak Bearish Trend"
        return "Range"

    def _open_position_entry_costs_batch(self, position_ids: list[Any], days: int = 3) -> dict[str, float]:
        """Return commission+swap for many open position ids with one cached history scan.

        V12.61 performance fix: the old per-position history_deals_get loop was the
        biggest source of UI lag when Burst mode opened several positions. This batch
        helper keeps PnL approximation available without freezing dashboard loads.
        """
        ids = [str(x) for x in position_ids if x is not None]
        if not ids:
            return {}
        now = time.monotonic()
        if self._entry_cost_cache and (now - self._entry_cost_cache_at) <= self._entry_cost_cache_ttl:
            return {pid: self._entry_cost_cache.get(pid, 0.0) for pid in ids}
        costs: dict[str, float] = {pid: 0.0 for pid in ids}
        try:
            end = datetime.now(timezone.utc) + timedelta(days=1)
            start = datetime.now(timezone.utc) - timedelta(days=days)
            deals = mt5.history_deals_get(start, end) or []
            wanted = set(ids)
            for d in deals:
                pid = str(getattr(d, "position_id", None) or getattr(d, "ticket", None) or "")
                if pid not in wanted:
                    continue
                costs[pid] = costs.get(pid, 0.0) + _safe_float(getattr(d, "commission", 0.0)) + _safe_float(getattr(d, "swap", 0.0))
            self._entry_cost_cache = costs
            self._entry_cost_cache_at = now
            return costs
        except Exception:
            return {pid: self._entry_cost_cache.get(pid, 0.0) for pid in ids}

    def _open_position_entry_costs(self, position_id: Any, days: int = 7) -> float:
        return self._open_position_entry_costs_batch([position_id], days=min(days, 3)).get(str(position_id), 0.0)

    def open_positions(self, bot_only: bool = True) -> list[dict[str, Any]]:
        ok, _ = self._ensure_initialized()
        if not ok:
            return []
        try:
            positions = mt5.positions_get() or []
            filtered = [p for p in positions if not (bot_only and not self._is_bot_record(p))]
            ids = [getattr(p, "identifier", None) or getattr(p, "ticket", None) for p in filtered]
            entry_cost_map = self._open_position_entry_costs_batch(ids)
            out: list[dict[str, Any]] = []
            for p in filtered:
                direction = "BUY" if getattr(p, "type", 0) == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL"
                price_open = _safe_float(getattr(p, "price_open", 0))
                price_current = _safe_float(getattr(p, "price_current", 0))
                profit = _safe_float(getattr(p, "profit", 0))
                pid = str(getattr(p, "identifier", None) or getattr(p, "ticket", None) or "")
                entry_costs = entry_cost_map.get(pid, 0.0)
                net_profit = profit + entry_costs
                out.append({
                    "ticket": getattr(p, "ticket", None),
                    "symbol": getattr(p, "symbol", self.symbol),
                    "name": getattr(p, "symbol", self.symbol),
                    "direction": direction,
                    "lots": _safe_float(getattr(p, "volume", 0.0)),
                    "entryPrice": round(price_open, 3),
                    "currentPrice": round(price_current, 3),
                    "sl": _safe_float(getattr(p, "sl", 0.0)),
                    "tp": _safe_float(getattr(p, "tp", 0.0)),
                    "pnlUsd": round(net_profit, 2),
                    "pnlGross": round(profit, 2),
                    "entryCosts": round(entry_costs, 2),
                    "pnlSource": "mt5_position_profit_plus_booked_costs",
                    "pnlPct": 0.0,
                    "tpProgress": 0,
                    "tpLabel": "LIVE",
                    "openTime": datetime.fromtimestamp(int(getattr(p, "time", 0)), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(p, "time", 0) else "",
                    "openTimestamp": int(getattr(p, "time", 0) or 0),
                    "openTimeMsc": int(getattr(p, "time_msc", 0) or 0),
                    "strategy": "GodMode Bot",
                    "magicNumber": getattr(p, "magic", None),
                    "comment": getattr(p, "comment", ""),
                    "source": "mt5",
                })
            return out
        except Exception:
            return []

    def place_pending_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        """V12.93 — place a BUY_STOP / SELL_STOP pending order at a structure level, so a breakout
        fills AT the level rather than chasing it with a market order after the move is extended.
        payload: {symbol, side, volume, price (trigger), sl, tp, comment, expirySeconds}."""
        side = str(payload.get("side", "")).upper()
        if side not in {"BUY", "SELL"}:
            return {"ok": False, "message": f"Invalid side '{side}' for pending stop."}
        vol = float(payload.get("volume") or 0.0)
        trigger = float(payload.get("price") or 0.0)
        protective_sl = float(payload.get("sl") or 0.0)
        if vol <= 0 or trigger <= 0:
            return {"ok": False, "message": "Pending stop needs positive volume and trigger price."}
        if protective_sl <= 0:
            return {
                "ok": False,
                "blocked": True,
                "message": "Pending entries require a broker-side protective stop.",
            }
        if (side == "BUY" and protective_sl >= trigger) or (
            side == "SELL" and protective_sl <= trigger
        ):
            return {
                "ok": False,
                "blocked": True,
                "message": "Pending-entry stop must be protective and directionally valid.",
            }
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Dry run: pending stop not sent (enable Live Trading).", "request": payload}
        if not self.auto_trading_enabled and not bool(payload.get("manualTrigger")):
            return {"ok": False, "blocked": True, "message": "Auto Trading switch is OFF."}
        symbol = str(payload.get("symbol") or self.symbol)
        cooldown = self.broker_entry_cooldown(symbol)
        if cooldown.get("active"):
            return {
                "ok": False,
                "dryRun": False,
                **self._close_only_fields(cooldown),
                "message": (
                    f"New {symbol} entry suppressed during broker close-only "
                    f"cooldown ({cooldown.get('retryAfterSeconds', 0)}s remaining)."
                ),
            }
        ok, detail = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": detail}
        market_ok, market_detail = self._entry_market_admission(symbol)
        if not market_ok:
            return {"ok": False, "dryRun": False, **market_detail}
        try:
            if not mt5.symbol_select(symbol, True):
                return {"ok": False, "message": f"Unable to select {symbol}."}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"ok": False, "message": f"No tick for {symbol}."}
            # A BUY_STOP must sit ABOVE current ask; a SELL_STOP BELOW current bid, else the broker
            # rejects it as an invalid stop (it would be an immediate market fill).
            if side == "BUY" and trigger <= tick.ask:
                return {"ok": False, "message": f"BUY_STOP trigger {trigger} must be above ask {tick.ask}."}
            if side == "SELL" and trigger >= tick.bid:
                return {"ok": False, "message": f"SELL_STOP trigger {trigger} must be below bid {tick.bid}."}
            order_type = mt5.ORDER_TYPE_BUY_STOP if side == "BUY" else mt5.ORDER_TYPE_SELL_STOP
            expiry_s = int(payload.get("expirySeconds") or 0)
            req = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": vol,
                "type": order_type,
                "price": trigger,
                "sl": float(payload.get("sl") or 0.0),
                "tp": float(payload.get("tp") or 0.0),
                "deviation": int(payload.get("deviation") or 20),
                "magic": self.magic,
                "comment": str(payload.get("comment") or "GODMODE breakout stop"),
                "type_time": mt5.ORDER_TIME_SPECIFIED if expiry_s > 0 else mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_RETURN,
            }
            if expiry_s > 0:
                req["expiration"] = int(time.time()) + expiry_s
            pf_ok, req, preflight = self._preflight(symbol, req)
            if not pf_ok:
                return {
                    "ok": False,
                    "blocked": True,
                    "dryRun": False,
                    "preflight": preflight,
                    "message": "Pre-flight blocked the pending entry: "
                    + str(preflight.get("message", "broker check failed")),
                    "request": req,
                    **self._admission_fields(preflight),
                }
            result = mt5.order_send(req)
            rd = result._asdict() if result else {}
            ok_r = bool(result and result.retcode in SUCCESS_RETCODES)
            retcode = int(rd.get("retcode") or 0) if isinstance(rd, dict) else 0
            close_only_fields: dict[str, Any] = {}
            if retcode == TRADE_RETCODE_CLOSE_ONLY:
                close_only_fields = self._close_only_fields(
                    self._activate_close_only_cooldown(
                        symbol,
                        "order_send",
                        str(rd.get("comment") or "Pending entry rejected close-only."),
                    )
                )
            return {
                "ok": ok_r,
                "message": (
                    "Pending stop placed."
                    if ok_r
                    else (
                        "Broker permits closes only; pending entry rejected and cooled down."
                        if close_only_fields
                        else "Broker rejected pending stop."
                    )
                ),
                "ticket": rd.get("order"),
                "request": req,
                "preflight": preflight,
                "result": rd if result else str(mt5.last_error()),
                **close_only_fields,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def cancel_pending(self, ticket: Any) -> dict[str, Any]:
        """Cancel a pending order by ticket (used to expire an un-triggered breakout stop)."""
        if not self.live_enabled:
            return {"ok": True, "dryRun": True}
        ok, _ = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": "MT5 not initialised."}
        try:
            result = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(ticket)})
            result_dict = result._asdict() if result else {}
            retcode = int(result_dict.get("retcode") or 0) if isinstance(result_dict, dict) else 0
            close_only_fields: dict[str, Any] = {}
            if retcode == TRADE_RETCODE_CLOSE_ONLY:
                close_only_fields = self._close_only_fields(
                    self._activate_close_only_cooldown(
                        self.symbol,
                        "cancel_order_send",
                        str(result_dict.get("comment") or "Pending cancellation returned close-only."),
                    )
                )
            return {
                "ok": bool(result and result.retcode in SUCCESS_RETCODES),
                "ticket": ticket,
                "result": result_dict if result else str(mt5.last_error()),
                **close_only_fields,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def pending_orders(self, bot_only: bool = True) -> list[dict[str, Any]]:
        ok, _ = self._ensure_initialized()
        if not ok:
            return []
        try:
            orders = mt5.orders_get() or []
            out: list[dict[str, Any]] = []
            for o in orders:
                if bot_only and not self._is_bot_record(o):
                    continue
                out.append({
                    "ticket": getattr(o, "ticket", None),
                    "symbol": getattr(o, "symbol", self.symbol),
                    "type": str(getattr(o, "type", "Pending")),
                    "direction": "BUY" if "BUY" in str(getattr(o, "type", "")).upper() else "SELL",
                    "lots": _safe_float(getattr(o, "volume_current", getattr(o, "volume_initial", 0.0))),
                    "price": _safe_float(getattr(o, "price_open", 0.0)),
                    "trigger": "Broker pending order",
                    "expiry": str(getattr(o, "time_expiration", "GTC")),
                    "status": "Active",
                    "magicNumber": getattr(o, "magic", None),
                    "comment": getattr(o, "comment", ""),
                    "source": "mt5",
                })
            return out
        except Exception:
            return []

    def active_order(self, ticket: Any) -> dict[str, Any] | None:
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None: return None
        try:
            rows = mt5.orders_get(ticket=int(ticket)) or []
            if not rows: return None
            o=rows[0]
            return {"ticket":getattr(o,"ticket",None),"symbol":getattr(o,"symbol",None),"type":getattr(o,"type",None),
                    "volumeInitial":_safe_float(getattr(o,"volume_initial",0.0)),"volumeCurrent":_safe_float(getattr(o,"volume_current",0.0)),
                    "price":_safe_float(getattr(o,"price_open",0.0)),"sl":_safe_float(getattr(o,"sl",0.0)),"tp":_safe_float(getattr(o,"tp",0.0)),
                    "state":getattr(o,"state",None),"timeSetup":getattr(o,"time_setup",None)}
        except Exception:
            return None

    def history_order(self, ticket: Any, lookback_days: int = 7) -> dict[str, Any] | None:
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None: return None
        try:
            end=datetime.now(timezone.utc)+timedelta(days=1); start=end-timedelta(days=lookback_days)
            rows=mt5.history_orders_get(start,end,ticket=int(ticket)) or []
            if not rows: return None
            o=rows[-1]
            return {"ticket":getattr(o,"ticket",None),"symbol":getattr(o,"symbol",None),"type":getattr(o,"type",None),
                    "volumeInitial":_safe_float(getattr(o,"volume_initial",0.0)),"volumeCurrent":_safe_float(getattr(o,"volume_current",0.0)),
                    "price":_safe_float(getattr(o,"price_open",0.0)),"sl":_safe_float(getattr(o,"sl",0.0)),"tp":_safe_float(getattr(o,"tp",0.0)),
                    "state":getattr(o,"state",None),"timeDone":getattr(o,"time_done",None)}
        except Exception:
            return None

    def deals_for_position(self, position_ticket: Any, since_epoch: float = 0.0) -> list[dict[str, Any]]:
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None: return []
        try:
            end=datetime.now(timezone.utc)+timedelta(days=1)
            start=datetime.fromtimestamp(max(0.0,float(since_epoch or 0.0))-300, timezone.utc) if since_epoch else end-timedelta(days=7)
            rows=mt5.history_deals_get(start,end,position=int(position_ticket)) or []
            return [{"ticket":getattr(d,"ticket",None),"order":getattr(d,"order",None),"position":getattr(d,"position_id",None),
                     "volume":_safe_float(getattr(d,"volume",0.0)),"price":_safe_float(getattr(d,"price",0.0)),
                     "entry":getattr(d,"entry",None),"type":getattr(d,"type",None),"time":getattr(d,"time",None)} for d in rows]
        except Exception:
            return []

    def closed_bot_trades(self, days: int = 30) -> list[dict[str, Any]]:
        """Return closed bot trades, newest first — reconstructed correctly.

        MT5 stores each trade as TWO+ deals: an entry deal (DEAL_ENTRY_IN) and one
        or more exit deals (DEAL_ENTRY_OUT). To report a trade the way it appears in
        the MT5 terminal we must PAIR them by position_id:

          • direction  = from the ENTRY deal type (a BUY position is opened by a buy
                          deal). NOTE: an exit deal's type is the OPPOSITE of the
                          position side, so reading direction off the exit deal — as
                          the old code did — inverted every side.
          • entryPrice = price of the entry deal
          • exitPrice  = volume-weighted price of the exit deal(s)
          • pnlUsd     = sum of profit+commission+swap across ALL deals of the trade
          • closeTime  = time of the last exit deal
          • holdTime   = last exit − entry
        """
        ok, _ = self._ensure_initialized()
        if not ok:
            return []
        try:
            # IMPORTANT: brokers stamp deals in SERVER time, which is usually ahead of
            # UTC (GMT+2/+3). Querying with end=now(UTC) silently drops just-closed deals
            # until UTC catches up — the real cause of "closed trades take hours to show".
            # We pad the end by 2 days so server-time-ahead deals are always included.
            end = datetime.now(timezone.utc) + timedelta(days=2)
            start = datetime.now(timezone.utc) - timedelta(days=days)
            deals = mt5.history_deals_get(start, end) or []
            DEAL_ENTRY_IN = getattr(mt5, "DEAL_ENTRY_IN", 0)
            DEAL_ENTRY_OUT = getattr(mt5, "DEAL_ENTRY_OUT", 1)
            DEAL_TYPE_BUY = getattr(mt5, "DEAL_TYPE_BUY", 0)

            # Group every bot deal by its position id
            groups: dict[Any, list[Any]] = {}
            for d in deals:
                if not self._is_bot_record(d):
                    continue
                # ignore balance/credit/correction deals (no symbol / type > 1)
                dtype = int(getattr(d, "type", 99))
                if dtype not in (0, 1):
                    continue
                pid = getattr(d, "position_id", None) or getattr(d, "ticket", None)
                groups.setdefault(pid, []).append(d)

            out: list[dict[str, Any]] = []
            for pid, dl in groups.items():
                dl.sort(key=lambda x: int(getattr(x, "time", 0) or 0))
                entry_deals = [d for d in dl if int(getattr(d, "entry", DEAL_ENTRY_IN)) == DEAL_ENTRY_IN]
                exit_deals = [d for d in dl if int(getattr(d, "entry", DEAL_ENTRY_OUT)) == DEAL_ENTRY_OUT]
                if not exit_deals:
                    continue  # trade still open — not closed history
                first_in = entry_deals[0] if entry_deals else dl[0]
                last_out = exit_deals[-1]

                # Direction from the ENTRY deal (buy deal => BUY position)
                direction = "BUY" if int(getattr(first_in, "type", 0)) == DEAL_TYPE_BUY else "SELL"

                entry_price = _safe_float(getattr(first_in, "price", 0.0))
                # Volume-weighted exit price across all exit deals
                ev = sum(_safe_float(getattr(d, "volume", 0.0)) for d in exit_deals) or 1.0
                exit_price = sum(_safe_float(getattr(d, "price", 0.0)) * _safe_float(getattr(d, "volume", 0.0)) for d in exit_deals) / ev

                # PnL = sum of every deal's profit + commission + swap for this position
                pnl = sum(
                    _safe_float(getattr(d, "profit", 0.0)) + _safe_float(getattr(d, "commission", 0.0)) + _safe_float(getattr(d, "swap", 0.0))
                    for d in dl
                )
                lots = sum(_safe_float(getattr(d, "volume", 0.0)) for d in exit_deals)
                t_in = int(getattr(first_in, "time", 0) or 0)
                t_out = int(getattr(last_out, "time", 0) or 0)
                close_time = datetime.fromtimestamp(t_out, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t_out else ""
                open_time = datetime.fromtimestamp(t_in, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if t_in else ""
                hold = max(0, t_out - t_in)
                if hold >= 86400:
                    hold_s = f"{hold//86400}d {(hold%86400)//3600}h"
                elif hold >= 3600:
                    hold_s = f"{hold//3600}h {(hold%3600)//60}m"
                else:
                    hold_s = f"{hold//60}m"
                pnl_pct = round((exit_price - entry_price) / entry_price * 100 * (1 if direction == "BUY" else -1), 3) if entry_price else 0.0
                comment = str(getattr(first_in, "comment", "") or getattr(last_out, "comment", "") or "")
                exit_reason = self._exit_reason_label(last_out, pnl)

                out.append({
                    "ticket": getattr(first_in, "position_id", None) or getattr(last_out, "ticket", None),
                    "positionId": pid,
                    "symbol": getattr(first_in, "symbol", self.symbol),
                    "direction": direction,
                    "lots": round(lots, 2),
                    "entryPrice": round(entry_price, 3),
                    "exitPrice": round(exit_price, 3),
                    "pnlUsd": round(pnl, 2),
                    "pnlPct": pnl_pct,
                    "holdTime": hold_s,
                    "openTime": open_time,
                    "openTimestamp": t_in,
                    "closeTime": close_time,
                    "closeTimestamp": t_out,
                    "exitReason": exit_reason,
                    # `reason` is a sensible default; app.py enriches it with the real
                    # strategy + entry rationale from the trade-context store.
                    "reason": exit_reason,
                    "magicNumber": getattr(first_in, "magic", None),
                    "comment": comment,
                    "source": "mt5",
                })
            out.sort(key=lambda x: x.get("closeTimestamp", 0), reverse=True)
            return out[:200]
        except Exception:
            return []

    def bot_history_pnl(self, days: int = 1) -> float:
        return sum(_safe_float(t.get("pnlUsd", 0.0)) for t in self.closed_bot_trades(days=days))

    def open_bot_risk_estimate(self) -> float:
        return float(self.open_bot_risk_details()["riskCash"])

    def open_bot_risk_details(self) -> dict[str, Any]:
        """Broker-currency risk plus explicit protection-quality telemetry.

        An absent SL is not zero risk. It is reported as unknown/unprotected and
        account_snapshot maps that condition to 100% open risk so new stacking
        fails closed.
        """
        risk = 0.0
        unprotected = 0
        fallbacks = 0
        for p in self.open_positions(bot_only=True):
            sl = _safe_float(p.get("sl", 0.0))
            entry = _safe_float(p.get("entryPrice", 0.0))
            lots = _safe_float(p.get("lots", 0.0))
            symbol = str(p.get("symbol") or self.symbol)
            side = str(p.get("direction") or p.get("side") or "").upper()
            if not sl or not entry or not lots:
                unprotected += 1
                continue
            broker_loss = self.order_calc_profit(side, symbol, lots, entry, sl)
            if broker_loss is not None:
                risk += max(0.0, -float(broker_loss))
                continue
            specs = self.symbol_specs(symbol)
            tick_size = _safe_float(specs.get("tradeTickSize", specs.get("tickSize", 0.0)))
            tick_value = _safe_float(specs.get("tradeTickValueLoss", specs.get("tradeTickValue", 0.0)))
            if tick_size > 0 and tick_value > 0:
                risk += abs(entry - sl) / tick_size * tick_value * lots
                fallbacks += 1
            else:
                unprotected += 1
        return {
            "riskCash": round(risk, 2),
            "unprotectedPositions": unprotected,
            "fallbackCalculations": fallbacks,
        }


    def order_calc_profit(self, side: str, symbol: str, volume: float, entry: float, exit_price: float) -> float | None:
        """Return broker-native projected P/L in account currency."""
        if mt5 is None:
            return None
        try:
            self._ensure_initialized()
            order_type = mt5.ORDER_TYPE_BUY if str(side).upper() == "BUY" else mt5.ORDER_TYPE_SELL
            result = mt5.order_calc_profit(order_type, symbol, float(volume), float(entry), float(exit_price))
            return None if result is None else float(result)
        except Exception:
            LOGGER.exception("MT5 order_calc_profit failed symbol=%s", symbol)
            return None

    def symbol_specs(self, symbol: str) -> dict[str, Any]:
        if mt5 is not None:
            try:
                self._ensure_initialized()
                info = mt5.symbol_info(symbol)
                if info:
                    point = float(info.point or 0.01)
                    tick_size = float(getattr(info, "trade_tick_size", 0.0) or point)
                    stops_level = int(getattr(info, "trade_stops_level", 0) or 0)
                    freeze_level = int(getattr(info, "trade_freeze_level", 0) or 0)
                    trade_mode = getattr(info, "trade_mode", None)
                    try:
                        trade_mode = int(trade_mode) if trade_mode is not None else None
                    except (TypeError, ValueError):
                        trade_mode = None
                    mode_names = {
                        int(getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)): "DISABLED",
                        int(getattr(mt5, "SYMBOL_TRADE_MODE_LONGONLY", 1)): "LONGONLY",
                        int(getattr(mt5, "SYMBOL_TRADE_MODE_SHORTONLY", 2)): "SHORTONLY",
                        int(getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", 3)): "CLOSEONLY",
                        int(getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4)): "FULL",
                    }
                    return {
                        "symbol": symbol,
                        "volumeMin": float(info.volume_min or 0.01),
                        "volumeStep": float(info.volume_step or 0.01),
                        "volumeMax": float(info.volume_max or 100.0),
                        "point": point,
                        "tradeTickValue": float(getattr(info, "trade_tick_value", 0.0) or 0.0),
                        "tradeTickSize": tick_size,
                        "tickSize": tick_size,
                        "digits": int(getattr(info, "digits", 2) or 2),
                        "stopsLevelPoints": stops_level,
                        "freezeLevelPoints": freeze_level,
                        "minStopDistance": max(stops_level, freeze_level) * point,
                        "tradeMode": trade_mode,
                        "tradeModeName": mode_names.get(trade_mode, "UNKNOWN"),
                        "source": "mt5",
                    }
            except Exception as exc:
                LOGGER.exception("MT5 symbol_specs failed symbol=%s", symbol)
                return {"symbol": symbol, "ok": False, "error": str(exc), "source": "error"}
        return {"symbol": symbol, "ok": False, "error": "MT5 unavailable", "source": "unavailable"}

    def _norm_volume(self, volume: float, specs: dict[str, Any]) -> float:
        minv = float(specs.get("volumeMin", 0.01) or 0.01)
        step = float(specs.get("volumeStep", 0.01) or 0.01)
        maxv = float(specs.get("volumeMax", 100.0) or 100.0)
        volume = max(0.0, min(float(volume), maxv))
        if volume < minv:
            return 0.0
        steps = math.floor((volume - minv) / step + 1e-9)
        return round(minv + steps * step, 2)

    def _cap_request_to_cash_risk(
        self,
        symbol: str,
        request: dict[str, Any],
        max_risk_cash: float,
    ) -> tuple[bool, dict[str, Any], dict[str, Any]]:
        """Recalculate risk from final broker geometry and reduce volume if needed."""
        req = dict(request)
        try:
            budget = float(max_risk_cash or 0.0)
            price = float(req.get("price") or 0.0)
            sl = float(req.get("sl") or 0.0)
            requested_volume = float(req.get("volume") or 0.0)
            if budget <= 0:
                return False, req, {"message": "A positive authoritative cash-risk budget is required."}
            if price <= 0 or sl <= 0 or requested_volume <= 0:
                return False, req, {"message": "Final live entry geometry is incomplete."}
            info = mt5.symbol_info(symbol) if mt5 is not None else None
            if info is None:
                return False, req, {"message": f"No broker symbol specification for {symbol}."}
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.0)
            tick_value = max(
                float(getattr(info, "trade_tick_value_loss", 0.0) or 0.0),
                float(getattr(info, "trade_tick_value", 0.0) or 0.0),
            )
            if tick_size <= 0 or tick_value <= 0:
                return False, req, {"message": "Authoritative broker tick size/value is unavailable."}
            loss_per_lot = abs(price - sl) / tick_size * tick_value
            if loss_per_lot <= 0:
                return False, req, {"message": "Final stop distance cannot produce a valid risk calculation."}
            raw_cap = budget / loss_per_lot
            specs = {
                "volumeMin": float(getattr(info, "volume_min", 0.01) or 0.01),
                "volumeStep": float(getattr(info, "volume_step", 0.01) or 0.01),
                "volumeMax": float(getattr(info, "volume_max", 100.0) or 100.0),
            }
            capped = self._norm_volume(min(requested_volume, raw_cap), specs)
            if capped <= 0:
                return False, req, {
                    "message": "Broker minimum volume would exceed the final cash-risk budget.",
                    "maxRiskCash": round(budget, 2),
                    "rawRiskVolumeCap": raw_cap,
                }
            req["volume"] = capped
            final_risk = capped * loss_per_lot
            return True, req, {
                "riskAdjusted": capped < requested_volume - 1e-9,
                "requestedVolume": requested_volume,
                "submittedVolume": capped,
                "maxRiskCash": round(budget, 2),
                "lossPerLot": round(loss_per_lot, 8),
                "finalRiskCash": round(final_risk, 8),
                "finalStopDistance": abs(price - sl),
            }
        except Exception as exc:
            return False, req, {"message": f"Final cash-risk validation failed closed: {exc}"}

    def _confirm_open_execution(
        self,
        symbol: str,
        side: str,
        submitted: dict[str, Any],
        result: dict[str, Any],
        before_positions: list[Any],
    ) -> dict[str, Any]:
        """Require broker position evidence for side, volume, SL and TP after an OPEN."""
        try:
            after_positions = list(mt5.positions_get(symbol=symbol) or [])
            expected_type = mt5.POSITION_TYPE_BUY if side == "BUY" else mt5.POSITION_TYPE_SELL
            candidates = [
                p
                for p in after_positions
                if int(getattr(p, "type", -1)) == int(expected_type)
                and int(getattr(p, "magic", -1)) == int(self.magic)
                and str(getattr(p, "comment", "") or "").startswith(self.comment_prefix)
            ]
            order_ticket = int(float(result.get("order") or 0))
            chosen = next(
                (p for p in candidates if int(float(getattr(p, "ticket", 0) or 0)) == order_ticket),
                None,
            )
            before_total = sum(
                float(getattr(p, "volume", 0.0) or 0.0)
                for p in before_positions
                if int(getattr(p, "type", -1)) == int(expected_type)
                and int(getattr(p, "magic", -1)) == int(self.magic)
            )
            after_total = sum(float(getattr(p, "volume", 0.0) or 0.0) for p in candidates)
            filled = float(result.get("volume") or submitted.get("volume") or 0.0)
            specs = self.symbol_specs(symbol)
            volume_step = float(specs.get("volumeStep") or 0.01)
            if chosen is None and after_total - before_total >= filled - volume_step / 2:
                chosen = max(
                    candidates,
                    key=lambda p: int(getattr(p, "time_msc", 0) or 0),
                    default=None,
                )
            if chosen is None:
                return {
                    "ok": False,
                    "message": "Broker response was not confirmed by a matching open position.",
                    "beforeVolume": before_total,
                    "afterVolume": after_total,
                }
            tick_size = max(
                float(specs.get("tradeTickSize") or specs.get("tickSize") or specs.get("point") or 0.01),
                1e-9,
            )
            expected_sl = float(submitted.get("sl") or 0.0)
            expected_tp = float(submitted.get("tp") or 0.0)
            actual_sl = float(getattr(chosen, "sl", 0.0) or 0.0)
            actual_tp = float(getattr(chosen, "tp", 0.0) or 0.0)
            sl_ok = expected_sl > 0 and abs(actual_sl - expected_sl) <= tick_size
            tp_ok = expected_tp <= 0 or abs(actual_tp - expected_tp) <= tick_size
            actual_volume = float(getattr(chosen, "volume", 0.0) or 0.0)
            volume_ok = actual_volume > 0 and (
                int(float(getattr(chosen, "ticket", 0) or 0)) == order_ticket
                or after_total - before_total >= filled - volume_step / 2
            )
            confirmed = {
                "ticket": int(float(getattr(chosen, "ticket", 0) or 0)),
                "symbol": str(getattr(chosen, "symbol", symbol) or symbol),
                "direction": side,
                "lots": actual_volume,
                "volume": actual_volume,
                "entryPrice": float(getattr(chosen, "price_open", 0.0) or 0.0),
                "sl": actual_sl,
                "tp": actual_tp,
                "magicNumber": int(getattr(chosen, "magic", 0) or 0),
                "comment": str(getattr(chosen, "comment", "") or ""),
            }
            return {
                "ok": bool(sl_ok and tp_ok and volume_ok),
                "confirmedPosition": confirmed,
                "confirmedVolumeDelta": max(0.0, after_total - before_total),
                "slConfirmed": sl_ok,
                "tpConfirmed": tp_ok,
                "volumeConfirmed": volume_ok,
                "message": (
                    "Broker position, volume and protection confirmed."
                    if sl_ok and tp_ok and volume_ok
                    else "Broker position readback did not match submitted volume/SL/TP."
                ),
            }
        except Exception as exc:
            return {"ok": False, "message": f"Broker open-position readback failed: {exc}"}

    def _order_type(self, side: str) -> int:
        if mt5 is None:
            return 0
        return mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL

    def _preflight(self, symbol: str, request: dict[str, Any]) -> tuple[bool, dict[str, Any], dict[str, Any]]:
        """Fail-closed broker preflight using current symbol, margin and order-check data."""
        info_out: dict[str, Any] = {"checks": []}
        if mt5 is None:
            return False, request, {"message": "MetaTrader5 module unavailable."}
        req = dict(request)
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return False, req, {"message": f"No broker symbol specification for {symbol}."}
            is_deal = req.get("action") == mt5.TRADE_ACTION_DEAL
            is_pending = req.get("action") == getattr(mt5, "TRADE_ACTION_PENDING", -1)
            # A DEAL carrying a position ticket is position-reducing. Trade-mode
            # restrictions apply only to risk-increasing entries; broker close-only
            # mode must never prevent the exact close that reduces exposure.
            is_reducing_deal = is_deal and int(float(req.get("position") or 0)) > 0
            is_entry = (is_deal and not is_reducing_deal) or is_pending
            is_sltp = req.get("action") == mt5.TRADE_ACTION_SLTP

            trade_mode_raw = getattr(info, "trade_mode", None)
            try:
                trade_mode = int(trade_mode_raw) if trade_mode_raw is not None else None
            except (TypeError, ValueError):
                trade_mode = None
            disabled_mode = int(getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0))
            long_only_mode = int(getattr(mt5, "SYMBOL_TRADE_MODE_LONGONLY", 1))
            short_only_mode = int(getattr(mt5, "SYMBOL_TRADE_MODE_SHORTONLY", 2))
            close_only_mode = int(getattr(mt5, "SYMBOL_TRADE_MODE_CLOSEONLY", 3))
            full_mode = int(getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4))
            mode_names = {
                disabled_mode: "DISABLED",
                long_only_mode: "LONGONLY",
                short_only_mode: "SHORTONLY",
                close_only_mode: "CLOSEONLY",
                full_mode: "FULL",
            }
            trade_mode_name = mode_names.get(trade_mode, "UNKNOWN")
            info_out.update(
                {
                    "tradeMode": trade_mode,
                    "tradeModeName": trade_mode_name,
                    "tradeModeCheckedFresh": True,
                }
            )
            if is_entry:
                if trade_mode is None or trade_mode not in mode_names:
                    return False, req, {
                        **info_out,
                        "classification": "BROKER_TRADE_MODE_UNKNOWN",
                        "message": (
                            f"Broker trade mode for {symbol} is missing or unknown; "
                            "entry failed closed."
                        ),
                    }
                buy_types = {
                    int(getattr(mt5, name))
                    for name in (
                        "ORDER_TYPE_BUY",
                        "ORDER_TYPE_BUY_LIMIT",
                        "ORDER_TYPE_BUY_STOP",
                        "ORDER_TYPE_BUY_STOP_LIMIT",
                    )
                    if hasattr(mt5, name)
                }
                sell_types = {
                    int(getattr(mt5, name))
                    for name in (
                        "ORDER_TYPE_SELL",
                        "ORDER_TYPE_SELL_LIMIT",
                        "ORDER_TYPE_SELL_STOP",
                        "ORDER_TYPE_SELL_STOP_LIMIT",
                    )
                    if hasattr(mt5, name)
                }
                order_type = req.get("type")
                side = (
                    "BUY"
                    if order_type in buy_types
                    else "SELL"
                    if order_type in sell_types
                    else "UNKNOWN"
                )
                info_out["entrySide"] = side
                allowed = (
                    trade_mode == full_mode
                    or (trade_mode == long_only_mode and side == "BUY")
                    or (trade_mode == short_only_mode and side == "SELL")
                )
                if not allowed:
                    if trade_mode == close_only_mode:
                        cooldown = self._activate_close_only_cooldown(
                            symbol,
                            "trade_mode",
                            f"{symbol} trade_mode is CLOSEONLY.",
                        )
                        return False, req, {
                            **info_out,
                            **self._close_only_fields(cooldown),
                            "message": (
                                f"Broker has {symbol} in CLOSEONLY mode; new entries "
                                "are blocked while closes and protection changes remain allowed."
                            ),
                        }
                    classification = (
                        "BROKER_TRADE_DISABLED"
                        if trade_mode == disabled_mode
                        else "BROKER_DIRECTION_RESTRICTED"
                    )
                    return False, req, {
                        **info_out,
                        "blocked": True,
                        "classification": classification,
                        "message": (
                            f"Broker trade mode {trade_mode_name} does not permit a "
                            f"{side} entry on {symbol}."
                        ),
                    }
                info_out["checks"].append("trade_mode")
            point = float(getattr(info, "point", 0.0) or 0.0)
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or point)
            if point <= 0 or tick_size <= 0:
                return False, req, {"message": f"Invalid broker point/tick size for {symbol}."}
            def quantize(value: float) -> float:
                return round(round(float(value) / tick_size) * tick_size, int(getattr(info, "digits", 5) or 5))
            if is_deal:
                fm = int(getattr(info, "filling_mode", 0) or 0)
                req["type_filling"] = (mt5.ORDER_FILLING_FOK if fm & 1 else mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_RETURN)
                info_out["fillingMode"] = int(req["type_filling"])
            lvl = max(int(getattr(info, "trade_stops_level", 0) or 0), int(getattr(info, "trade_freeze_level", 0) or 0))
            min_dist = lvl * point
            info_out.update({"point": point, "tickSize": tick_size, "minStopDistance": min_dist, "freezeLevelPoints": int(getattr(info, "trade_freeze_level", 0) or 0)})
            if "price" in req:
                req["price"] = quantize(req["price"])
            if (is_deal or is_pending) and "price" in req:
                price = float(req["price"]); is_buy = req.get("type") == mt5.ORDER_TYPE_BUY
                if is_pending:
                    is_buy = req.get("type") in {
                        getattr(mt5, "ORDER_TYPE_BUY_LIMIT", -1001),
                        getattr(mt5, "ORDER_TYPE_BUY_STOP", -1002),
                        getattr(mt5, "ORDER_TYPE_BUY_STOP_LIMIT", -1003),
                    }
                sl, tp = float(req.get("sl") or 0.0), float(req.get("tp") or 0.0)
                if sl > 0:
                    if is_buy and price-sl < min_dist: sl = price-min_dist
                    elif (not is_buy) and sl-price < min_dist: sl = price+min_dist
                    req["sl"] = quantize(sl)
                if tp > 0:
                    if is_buy and tp-price < min_dist: tp = price+min_dist
                    elif (not is_buy) and price-tp < min_dist: tp = price-min_dist
                    req["tp"] = quantize(tp)
                if is_entry:
                    margin = mt5.order_calc_margin(req["type"], symbol, req["volume"], req["price"])
                    acct = mt5.account_info()
                    if margin is None or acct is None:
                        return False, req, {**info_out, "message": "Broker margin pre-check unavailable."}
                    info_out["marginRequired"] = round(float(margin), 2)
                    info_out["freeMargin"] = round(float(acct.margin_free), 2)
                    if float(acct.margin_free) < float(margin):
                        return False, req, {**info_out, "message": f"Insufficient free margin: need {float(margin):.2f}, free {float(acct.margin_free):.2f}."}
                else:
                    info_out["marginCheck"] = "bypassed_position_reduction"
            if is_sltp:
                ticket = int(float(req.get("position") or 0))
                positions = mt5.positions_get(ticket=ticket) or []
                if not positions:
                    return False, req, {**info_out, "message": f"No open position found for SL/TP preflight ticket {ticket}."}
                pos = positions[0]
                cur = float(getattr(pos, "price_current", 0.0) or 0.0)
                is_buy = getattr(pos, "type", 0) == getattr(mt5, "POSITION_TYPE_BUY", 0)
                old_sl = float(getattr(pos, "sl", 0.0) or 0.0)
                old_tp = float(getattr(pos, "tp", 0.0) or 0.0)
                adjustments: dict[str, dict[str, float]] = {}
                sl = float(req.get("sl") or 0.0)
                tp = float(req.get("tp") or 0.0)
                if sl > 0:
                    requested_sl = sl
                    if abs(sl - old_sl) > tick_size / 2:
                        if is_buy and cur - sl < min_dist:
                            sl = cur - min_dist
                        elif (not is_buy) and sl - cur < min_dist:
                            sl = cur + min_dist
                    req["sl"] = quantize(sl)
                    requested_tightens = (
                        old_sl <= 0
                        or (is_buy and requested_sl >= old_sl - tick_size / 2)
                        or ((not is_buy) and requested_sl <= old_sl + tick_size / 2)
                    )
                    adjusted_weakens = (
                        old_sl > 0
                        and (
                            (is_buy and req["sl"] < old_sl - tick_size / 2)
                            or ((not is_buy) and req["sl"] > old_sl + tick_size / 2)
                        )
                    )
                    if requested_tightens and adjusted_weakens:
                        req["sl"] = quantize(old_sl)
                        return False, req, {
                            **info_out,
                            "protectionDirectionViolation": True,
                            "message": (
                                "Broker minimum-distance adjustment would weaken the existing "
                                "stop; the modification was blocked without changing protection."
                            ),
                        }
                    if abs(req["sl"] - requested_sl) > tick_size / 2:
                        adjustments["sl"] = {"requested": requested_sl, "submitted": req["sl"]}
                if tp > 0:
                    requested_tp = tp
                    if abs(tp - old_tp) > tick_size / 2:
                        if is_buy and tp - cur < min_dist:
                            tp = cur + min_dist
                        elif (not is_buy) and cur - tp < min_dist:
                            tp = cur - min_dist
                    req["tp"] = quantize(tp)
                    if abs(req["tp"] - requested_tp) > tick_size / 2:
                        adjustments["tp"] = {"requested": requested_tp, "submitted": req["tp"]}
                if adjustments:
                    info_out["adjustments"] = adjustments
            chk = mt5.order_check(req)
            if chk is None:
                return False, req, {**info_out, "message": f"Broker order_check unavailable: {mt5.last_error()}"}
            rc = int(getattr(chk, "retcode", 0) or 0)
            info_out["orderCheckRetcode"] = rc
            info_out["orderCheckComment"] = str(getattr(chk, "comment", ""))
            if rc and rc not in {0, 10008, 10009, 10010}:
                if rc == TRADE_RETCODE_CLOSE_ONLY:
                    cooldown = self._activate_close_only_cooldown(
                        symbol,
                        "order_check",
                        str(getattr(chk, "comment", "") or "Broker order_check returned close-only."),
                    )
                    return False, req, {
                        **info_out,
                        **self._close_only_fields(cooldown),
                        "message": (
                            "Broker pre-check rejected the entry because only position "
                            "closing is allowed (retcode 10044)."
                        ),
                    }
                return False, req, {**info_out, "message": f"Broker pre-check rejected order (retcode {rc}: {getattr(chk, 'comment', '')})."}
            return True, req, info_out
        except Exception as exc:
            LOGGER.exception("MT5 preflight failed symbol=%s request=%r", symbol, request)
            return False, req, {**info_out, "message": f"Broker preflight failed closed: {exc}"}

    def _build_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", self.symbol))
        side = str(payload.get("side", payload.get("direction", "BUY"))).upper()
        specs = self.symbol_specs(symbol)
        volume = self._norm_volume(float(payload.get("volume", payload.get("lot", 0.01)) or 0.01), specs)
        comment_raw = str(payload.get("comment", "GodMode order"))
        comment = comment_raw if comment_raw.startswith(self.comment_prefix) else f"{self.comment_prefix}{comment_raw}"
        request: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "sl": payload.get("sl"),
            "tp": payload.get("tp"),
            "deviation": int(payload.get("deviation", self.max_deviation) or self.max_deviation),
            "magic": int(payload.get("magic", self.magic) or self.magic),
            "comment": comment[:31],
            "source": "godmode_bot",
        }
        return request


    def close_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        ticket = int(float(payload.get("ticket") or payload.get("position") or 0))
        if ticket <= 0:
            return {"ok": False, "message": "A valid MT5 position ticket is required to close a trade."}
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Dry run only. Close request validated but not sent to MT5.", "request": payload}
        ok, detail = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": detail}
        try:
            positions = mt5.positions_get(ticket=ticket) or []
            if not positions:
                return {"ok": False, "message": f"No open position found for ticket {ticket}."}
            pos = positions[0]
            symbol = getattr(pos, "symbol", self.symbol)
            if not mt5.symbol_select(symbol, True):
                return {"ok": False, "message": f"Unable to select symbol {symbol}: {mt5.last_error()}"}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"ok": False, "message": f"No tick available for {symbol}."}
            volume = float(payload.get("volume") or getattr(pos, "volume", 0.0) or 0.0)
            specs = self.symbol_specs(symbol)
            volume = self._norm_volume(volume, specs)
            pos_type = getattr(pos, "type", 0)
            close_type = mt5.ORDER_TYPE_SELL if pos_type == getattr(mt5, "POSITION_TYPE_BUY", 0) else mt5.ORDER_TYPE_BUY
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": symbol,
                "volume": volume,
                "type": close_type,
                "price": price,
                "deviation": int(payload.get("deviation", self.max_deviation) or self.max_deviation),
                "magic": self.magic,
                "comment": f"{self.comment_prefix}close"[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            pf_ok, request, preflight = self._preflight(symbol, request)
            if not pf_ok:
                return {"ok": False, "blocked": True, "dryRun": False, "preflight": preflight, "message": "Pre-flight blocked the close: " + str(preflight.get("message", "broker check failed")), "mt5Request": request,
                        **self._admission_fields(preflight)}
            t0 = time.perf_counter()
            result = mt5.order_send(request)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            result_dict = result._asdict() if result else {}
            retcode = int(result_dict.get("retcode") or 0) if isinstance(result_dict, dict) else 0
            close_only_fields: dict[str, Any] = {}
            if retcode == TRADE_RETCODE_CLOSE_ONLY:
                close_only_fields = self._close_only_fields(
                    self._activate_close_only_cooldown(
                        symbol,
                        "close_order_send",
                        str(result_dict.get("comment") or "Close request returned close-only."),
                    )
                )
            filled_price = _safe_float(result_dict.get("price"), price) if isinstance(result_dict, dict) else price
            slip = (price - filled_price) if close_type == mt5.ORDER_TYPE_SELL else (filled_price - price)
            metrics = {"requestedPrice": round(float(price), 5), "filledPrice": round(float(filled_price), 5),
                       "slippagePrice": round(float(slip), 5), "latencyMs": latency_ms,
                       "retcode": result_dict.get("retcode") if isinstance(result_dict, dict) else None}
            return {"ok": ok_result, "dryRun": False, "message": "Close order sent." if ok_result else "MT5 close rejected.", "mt5Request": request, "preflight": preflight, "executionMetrics": metrics, "result": result_dict if result else str(mt5.last_error()),
                    **close_only_fields}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "request": payload}

    def modify_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        ticket = int(float(payload.get("ticket") or payload.get("position") or 0))
        if ticket <= 0:
            return {"ok": False, "message": "A valid MT5 position ticket is required to modify a trade."}
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Dry run only. Modify request validated but not sent to MT5.", "request": payload}
        ok, detail = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": detail}
        try:
            positions = mt5.positions_get(ticket=ticket) or []
            if not positions:
                return {"ok": False, "message": f"No open position found for ticket {ticket}."}
            pos = positions[0]
            sl = float(payload.get("sl", getattr(pos, "sl", 0.0)) or 0.0)
            tp = float(payload.get("tp", getattr(pos, "tp", 0.0)) or 0.0)
            request = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": getattr(pos, "symbol", self.symbol), "sl": sl, "tp": tp, "magic": self.magic, "comment": f"{self.comment_prefix}modify"[:31]}
            pf_ok, request, preflight = self._preflight(getattr(pos, "symbol", self.symbol), request)
            if not pf_ok:
                return {"ok": False, "blocked": True, "dryRun": False, "preflight": preflight, "message": "Pre-flight blocked the modify: " + str(preflight.get("message", "broker check failed")), "mt5Request": request,
                        **self._admission_fields(preflight)}
            t0 = time.perf_counter()
            result = mt5.order_send(request)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            result_dict = result._asdict() if result else {}
            symbol = str(getattr(pos, "symbol", self.symbol))
            retcode = int(result_dict.get("retcode") or 0) if isinstance(result_dict, dict) else 0
            close_only_fields: dict[str, Any] = {}
            if retcode == TRADE_RETCODE_CLOSE_ONLY:
                close_only_fields = self._close_only_fields(
                    self._activate_close_only_cooldown(
                        symbol,
                        "modify_order_send",
                        str(result_dict.get("comment") or "Protection modification returned close-only."),
                    )
                )
            metrics = {"latencyMs": latency_ms, "retcode": result_dict.get("retcode") if isinstance(result_dict, dict) else None}
            return {"ok": ok_result, "dryRun": False, "message": "Modify request sent." if ok_result else "MT5 modify rejected.", "mt5Request": request, "executionMetrics": metrics, "result": result_dict if result else str(mt5.last_error()),
                    **close_only_fields}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "request": payload}

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._build_request(payload)
        if request["side"] not in {"BUY", "SELL"}:
            return {"ok": False, "blocked": True, "message": f"Invalid order side '{request['side']}'. Expected BUY or SELL.", "request": request}
        if request["volume"] <= 0:
            return {"ok": False, "message": "Requested volume is below broker minimum volume.", "request": request}
        if float(request.get("sl") or 0.0) <= 0:
            return {
                "ok": False,
                "blocked": True,
                "message": "Live and dry-run entries require a broker-side protective stop.",
                "request": request,
            }
        if not self.live_enabled:
            return {
                "ok": True,
                "dryRun": True,
                "message": "Dry run only. Use Settings > MT5 Connection > Live Trading to enable live MT5 order sending.",
                "request": request,
            }
        manual_trigger = bool(payload.get("manualTrigger") or payload.get("manualOverride") or payload.get("manualExecution"))
        if not self.auto_trading_enabled and not manual_trigger:
            return {"ok": False, "blocked": True, "dryRun": False, "message": "Auto Trading switch is OFF in GodMode settings.", "request": request}
        symbol = request["symbol"]
        cooldown = self.broker_entry_cooldown(symbol)
        if cooldown.get("active"):
            return {
                "ok": False,
                "dryRun": False,
                "request": request,
                **self._close_only_fields(cooldown),
                "message": (
                    f"New {symbol} entry suppressed during broker close-only "
                    f"cooldown ({cooldown.get('retryAfterSeconds', 0)}s remaining)."
                ),
            }
        ok, detail = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": detail, "request": request}
        market_ok, market_detail = self._entry_market_admission(symbol)
        if not market_ok:
            return {
                "ok": False,
                "dryRun": False,
                "request": request,
                **market_detail,
            }
        try:
            if not mt5.symbol_select(symbol, True):
                return {"ok": False, "message": f"Unable to select symbol {symbol}: {mt5.last_error()}", "request": request}
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"ok": False, "message": f"No tick available for {symbol}", "request": request}
            order_type = self._order_type(request["side"])
            price = tick.ask if request["side"] == "BUY" else tick.bid
            mt5_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": request["volume"],
                "type": order_type,
                "price": price,
                "sl": float(request["sl"]) if request.get("sl") is not None else 0.0,
                "tp": float(request["tp"]) if request.get("tp") is not None else 0.0,
                "deviation": request["deviation"],
                "magic": request["magic"],
                "comment": request["comment"],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            pf_ok, mt5_request, preflight = self._preflight(symbol, mt5_request)
            if not pf_ok:
                return {"ok": False, "blocked": True, "dryRun": False, "preflight": preflight,
                        "message": "Pre-flight blocked the order: " + str(preflight.get("message", "broker check failed")), "request": request, "mt5Request": mt5_request,
                        **self._admission_fields(preflight)}
            risk_ok, mt5_request, final_risk = self._cap_request_to_cash_risk(
                symbol,
                mt5_request,
                float(payload.get("maxRiskCash") or 0.0),
            )
            preflight["finalRisk"] = final_risk
            if not risk_ok:
                return {
                    "ok": False,
                    "blocked": True,
                    "dryRun": False,
                    "preflight": preflight,
                    "message": "Final live risk validation blocked the order: " + str(final_risk.get("message", "risk budget exceeded")),
                    "request": request,
                    "mt5Request": mt5_request,
                }
            if final_risk.get("riskAdjusted"):
                pf_ok, mt5_request, adjusted_preflight = self._preflight(symbol, mt5_request)
                preflight["riskAdjustedPreflight"] = adjusted_preflight
                if not pf_ok:
                    return {
                        "ok": False,
                        "blocked": True,
                        "dryRun": False,
                        "preflight": preflight,
                        "message": "Broker rejected the risk-adjusted order.",
                        "request": request,
                        "mt5Request": mt5_request,
                        **self._admission_fields(adjusted_preflight),
                    }
            before_positions = list(mt5.positions_get(symbol=symbol) or [])
            t0 = time.perf_counter()
            result = mt5.order_send(mt5_request)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            result_dict = result._asdict() if result else {}
            retcode = int(result_dict.get("retcode") or 0) if isinstance(result_dict, dict) else 0
            close_only_fields: dict[str, Any] = {}
            if retcode == TRADE_RETCODE_CLOSE_ONLY:
                close_only_fields = self._close_only_fields(
                    self._activate_close_only_cooldown(
                        symbol,
                        "order_send",
                        str(result_dict.get("comment") or "Entry rejected close-only."),
                    )
                )
            filled_price = _safe_float(result_dict.get("price"), price) if isinstance(result_dict, dict) else price
            slip = (filled_price - price) if request["side"] == "BUY" else (price - filled_price)
            metrics = {"requestedPrice": round(float(price), 5), "filledPrice": round(float(filled_price), 5),
                       "slippagePrice": round(float(slip), 5), "latencyMs": latency_ms,
                       "retcode": result_dict.get("retcode") if isinstance(result_dict, dict) else None}
            readback = (
                self._confirm_open_execution(symbol, request["side"], mt5_request, result_dict, before_positions)
                if ok_result
                else {"ok": False, "message": "MT5 rejected the order."}
            )
            confirmed = bool(readback.get("ok"))
            return {
                "ok": bool(ok_result and confirmed),
                "unknown": bool(ok_result and not confirmed),
                "readbackConfirmed": confirmed,
                "confirmedPosition": readback.get("confirmedPosition"),
                "readback": readback,
                "dryRun": False,
                "message": (
                    "Order filled with broker-confirmed protection."
                    if ok_result and confirmed
                    else (
                        "Broker accepted the order, but exact protected-position readback is inconclusive."
                        if ok_result
                        else (
                            "Broker permits closes only; entry rejected and cooled down."
                            if close_only_fields
                            else "MT5 order rejected."
                        )
                    )
                ),
                "request": request,
                "mt5Request": mt5_request,
                "preflight": preflight,
                "executionMetrics": metrics,
                "result": result_dict if result else str(mt5.last_error()),
                **close_only_fields,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "request": request}

    def split_target_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", self.symbol))
        side = str(payload.get("side", "BUY")).upper()
        if side not in {"BUY", "SELL"}:
            return {"ok": False, "message": f"Invalid split-order side '{side}'. Expected BUY or SELL.", "legs": [], "totalVolume": 0.0}
        requested_volume = float(payload.get("volume", 0.01) or 0.01)
        specs = self.symbol_specs(symbol)
        minv = float(specs.get("volumeMin", 0.01) or 0.01)
        step = float(specs.get("volumeStep", 0.01) or 0.01)
        volume = self._norm_volume(requested_volume, specs)
        targets = [payload.get("tp1"), payload.get("tp2"), payload.get("tp3"), payload.get("tp4")]
        targets = [float(t) for t in targets if t is not None]
        if not targets:
            return {"ok": False, "message": "At least one TP target is required.", "legs": [], "totalVolume": 0.0}
        if volume <= 0:
            return {"ok": False, "message": "Requested volume is below broker minimum volume.", "legs": [], "totalVolume": 0.0}

        max_legs_by_volume = max(1, int(math.floor(volume / minv + 1e-9)))
        leg_count = min(len(targets), max_legs_by_volume)
        selected_targets = targets[:leg_count]
        remaining = volume
        legs: list[dict[str, Any]] = []
        for idx, target in enumerate(selected_targets):
            if idx < leg_count - 1:
                leg_volume = minv
            else:
                leg_volume = self._norm_volume(remaining, specs)
            remaining = round(max(0.0, remaining - leg_volume), 2)
            if leg_volume <= 0:
                continue
            legs.append({
                "symbol": symbol,
                "side": side,
                "volume": leg_volume,
                "sl": payload.get("sl"),
                "tp": target,
                "comment": f"{self.comment_prefix}TP{idx + 1}",
                "magic": int(payload.get("magic", self.magic) or self.magic),
                "source": "godmode_bot",
            })
        total = round(sum(float(x["volume"]) for x in legs), 2)
        warnings: list[str] = []
        if len(legs) < len(targets):
            warnings.append("Volume is too small to split across all TP1-TP4 targets at broker minimum lot; reduced child-order count to prevent over-allocation.")
        if total > volume + 1e-9:
            return {"ok": False, "message": "Safety block: split volume exceeds requested volume.", "legs": legs, "totalVolume": total, "requestedVolume": volume}
        return {"ok": True, "legs": legs, "totalVolume": total, "requestedVolume": volume, "warnings": warnings, "volumeStep": step, "volumeMin": minv}

    def execute_multi_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self.split_target_plan(payload)
        if not plan.get("ok"):
            return {"ok": False, "message": plan.get("message"), "plan": plan}
        if not self.live_enabled:
            return {"ok": True, "dryRun": True, "message": "Multi-target dry run; split plan validated without over-allocation.", "plan": plan}
        results = [self.execute(leg) for leg in plan["legs"]]
        return {"ok": all(r.get("ok") for r in results), "dryRun": False, "plan": plan, "results": results}


# V12.58 MT5 IPC serialization wrapper
# ----------------------------------
# The MT5 Python package talks to the terminal process over a local IPC channel. When the
# dashboard, auto-manager, signal watchdog and Telegram controls all call MT5 at the same
# time, that channel can stall. Wrapping all broker-facing methods with one re-entrant lock
# keeps requests ordered and prevents UI freezes/deadlocks. Pure math helpers are left alone.
def _godmode_ipc_guard(fn):
    def _wrapped(self, *args, **kwargs):
        lock = getattr(self, "_ipc_lock", None)
        if lock is None:
            return fn(self, *args, **kwargs)
        started = time.monotonic()
        with lock:
            result = fn(self, *args, **kwargs)
        elapsed = time.monotonic() - started
        # Preserve behaviour; just annotate dictionaries when a call was slow enough to be useful in diagnostics.
        if isinstance(result, dict) and elapsed > 2.5:
            result.setdefault("slowMt5Call", True)
            result.setdefault("slowMt5Seconds", round(elapsed, 2))
        return result
    _wrapped.__name__ = getattr(fn, "__name__", "wrapped")
    _wrapped.__doc__ = getattr(fn, "__doc__", None)
    return _wrapped

for _name in [
    "configure", "connect", "disconnect", "status", "is_hedging", "account_snapshot",
    "market_snapshot", "market_open", "copy_rates", "copy_ticks_range", "open_positions", "pending_orders", "active_order", "history_order", "deals_for_position",
    "closed_bot_trades", "bot_history_pnl", "open_bot_risk_estimate", "symbol_specs",
    "latest_tick", "close_position", "modify_position", "place_pending_stop", "cancel_pending", "execute", "execute_multi_target",
]:
    _fn = getattr(MT5Bridge, _name, None)
    if callable(_fn) and not getattr(_fn, "_godmode_ipc_guarded", False):
        _wrapped = _godmode_ipc_guard(_fn)
        setattr(_wrapped, "_godmode_ipc_guarded", True)
        setattr(MT5Bridge, _name, _wrapped)
