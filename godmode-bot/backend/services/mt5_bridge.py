from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - MT5 is Windows/terminal dependent
    mt5 = None


SUCCESS_RETCODES = {10008, 10009, 10010}


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
        if "liveTradingEnabled" in payload:
            self.live_enabled = bool(payload.get("liveTradingEnabled"))
        if "dryRun" in payload:
            self.live_enabled = not bool(payload.get("dryRun"))
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
        now = __import__("time").time()
        # Use cached result if fresh — avoids hammering mt5.initialize() on every API call
        if self._init_ok and (now - self._init_at) < self._init_ttl:
            return True, self._init_detail
        try:
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
                    return False, msg
            if ok:
                self.last_connect_message = "initialized"
                self._init_ok, self._init_detail, self._init_at = True, "initialized", now
                return True, "initialized"
            msg = f"MT5 initialize failed: {mt5.last_error()}"
            self.last_connect_message = msg
            self._init_ok, self._init_detail, self._init_at = False, msg, now
            return False, msg
        except Exception as exc:
            self._init_ok, self._init_detail, self._init_at = False, str(exc), now
            self.last_connect_message = str(exc)
            return False, str(exc)

    def connect(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.configure(payload or {})
        ok, detail = self._ensure_initialized()
        return {"ok": ok, "detail": detail, "status": self.status()}

    def disconnect(self) -> dict[str, Any]:
        if mt5 is not None:
            try:
                mt5.shutdown()
            except Exception:
                pass
        self.last_connect_message = "MT5 shutdown requested from UI."
        return {"ok": True, "status": self.status()}

    def _is_bot_record(self, item: Any) -> bool:
        magic = getattr(item, "magic", None)
        comment = str(getattr(item, "comment", "") or "")
        return _safe_int(magic, -1) == self.magic or comment.startswith(self.comment_prefix)

    def _exit_reason_label(self, deal: Any) -> str:
        """Map an MT5 closing-deal reason code to a human label (TP/SL/manual/etc.)."""
        if mt5 is None:
            return "Closed"
        code = _safe_int(getattr(deal, "reason", -1), -1)
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
            }
        try:
            terminal = mt5.terminal_info()
            account = mt5.account_info()
            connected = bool(terminal and getattr(terminal, "connected", False))
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
            margin = _safe_float(getattr(info, "margin", 0.0))
            free = _safe_float(getattr(info, "margin_free", 0.0))
            daily_pnl = self.bot_history_pnl(days=1)
            open_risk = self.open_bot_risk_estimate()
            return {
                "source": "mt5",
                "connected": True,
                "balance": round(balance, 2),
                "equity": round(equity, 2),
                "dailyPnl": round(daily_pnl, 2),
                "dailyPnlPct": round((daily_pnl / balance) * 100, 2) if balance else 0.0,
                "openRisk": round(open_risk, 2),
                "openRiskPct": round((open_risk / equity) * 100, 2) if equity else 0.0,
                "freeMargin": round(free, 2),
                "margin": round(margin, 2),
                "marginHealth": max(0, min(100, round((free / equity) * 100, 0))) if equity else 0,
                "currency": getattr(info, "currency", ""),
                "login": getattr(info, "login", None),
                "server": getattr(info, "server", None),
                "broker": getattr(info, "company", None),
                "leverage": getattr(info, "leverage", None),
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
            "freeMargin": 0.0,
            "margin": 0.0,
            "marginHealth": 0,
            "currency": "",
            "login": None,
            "server": None,
            "broker": None,
            "leverage": None,
        }

    def market_snapshot(self, symbol: str | None = None, timeframe: str = "M15") -> dict[str, Any]:
        symbol = symbol or self.symbol
        ok, detail = self._ensure_initialized()
        if not ok:
            return self._empty_market(symbol, timeframe, detail)
        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if tick is None:
                return self._empty_market(symbol, timeframe, f"No live tick available for {symbol}")
            bid = _safe_float(getattr(tick, "bid", 0.0))
            ask = _safe_float(getattr(tick, "ask", 0.0))
            price = ask if ask else bid
            point = _safe_float(getattr(info, "point", 0.01), 0.01) if info else 0.01
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
            return {
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
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

    def market_open(self) -> dict[str, Any]:
        """Is the symbol's market open? The UTC weekend schedule is authoritative for the weekend;
        when connected, live tick-staleness (no new tick for 5+ minutes) additionally catches
        intraday halts and the daily break. Returns {open, reason, source}."""
        sched_open, sched_reason = self._schedule_open()
        ok, _ = self._ensure_initialized()
        if not ok or mt5 is None:
            return {"open": sched_open, "reason": sched_reason, "source": "schedule"}
        if not sched_open:
            return {"open": False, "reason": sched_reason, "source": "schedule"}
        try:
            tick = mt5.symbol_info_tick(self.symbol)
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
        except Exception:
            return {"open": sched_open, "reason": sched_reason, "source": "schedule"}

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

    def open_positions(self, bot_only: bool = True) -> list[dict[str, Any]]:
        ok, _ = self._ensure_initialized()
        if not ok:
            return []
        try:
            positions = mt5.positions_get() or []
            out: list[dict[str, Any]] = []
            for p in positions:
                if bot_only and not self._is_bot_record(p):
                    continue
                direction = "BUY" if getattr(p, "type", 0) == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL"
                price_open = _safe_float(getattr(p, "price_open", 0))
                price_current = _safe_float(getattr(p, "price_current", 0))
                profit = _safe_float(getattr(p, "profit", 0))
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
                    "pnlUsd": round(profit, 2),
                    "pnlPct": 0.0,
                    "tpProgress": 0,
                    "tpLabel": "LIVE",
                    "openTime": datetime.fromtimestamp(int(getattr(p, "time", 0)), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(p, "time", 0) else "",
                    "strategy": "GodMode Bot",
                    "magicNumber": getattr(p, "magic", None),
                    "comment": getattr(p, "comment", ""),
                    "source": "mt5",
                })
            return out
        except Exception:
            return []

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
                exit_reason = self._exit_reason_label(last_out)

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
        risk = 0.0
        for p in self.open_positions(bot_only=True):
            sl = _safe_float(p.get("sl", 0.0))
            entry = _safe_float(p.get("entryPrice", 0.0))
            lots = _safe_float(p.get("lots", 0.0))
            if sl and entry and lots:
                risk += abs(entry - sl) * lots * 100
        return risk

    def symbol_specs(self, symbol: str) -> dict[str, Any]:
        if mt5 is not None:
            try:
                self._ensure_initialized()
                info = mt5.symbol_info(symbol)
                if info:
                    return {
                        "symbol": symbol,
                        "volumeMin": float(info.volume_min or 0.01),
                        "volumeStep": float(info.volume_step or 0.01),
                        "volumeMax": float(info.volume_max or 100.0),
                        "point": float(info.point or 0.01),
                        "tradeTickValue": float(getattr(info, "trade_tick_value", 0.0) or 0.0),
                        "tradeTickSize": float(getattr(info, "trade_tick_size", 0.0) or 0.0),
                        "source": "mt5",
                    }
            except Exception:
                pass
        return {"symbol": symbol, "volumeMin": 0.01, "volumeStep": 0.01, "volumeMax": 100.0, "source": "fallback"}

    def _norm_volume(self, volume: float, specs: dict[str, Any]) -> float:
        minv = float(specs.get("volumeMin", 0.01) or 0.01)
        step = float(specs.get("volumeStep", 0.01) or 0.01)
        maxv = float(specs.get("volumeMax", 100.0) or 100.0)
        volume = max(0.0, min(float(volume), maxv))
        if volume < minv:
            return 0.0
        steps = math.floor((volume - minv) / step + 1e-9)
        return round(minv + steps * step, 2)

    def _order_type(self, side: str) -> int:
        if mt5 is None:
            return 0
        return mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL

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
            result = mt5.order_send(request)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            return {"ok": ok_result, "dryRun": False, "message": "Close order sent." if ok_result else "MT5 close rejected.", "mt5Request": request, "result": result._asdict() if result else str(mt5.last_error())}
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
            result = mt5.order_send(request)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            return {"ok": ok_result, "dryRun": False, "message": "Modify request sent." if ok_result else "MT5 modify rejected.", "mt5Request": request, "result": result._asdict() if result else str(mt5.last_error())}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "request": payload}

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._build_request(payload)
        if request["volume"] <= 0:
            return {"ok": False, "message": "Requested volume is below broker minimum volume.", "request": request}
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
        ok, detail = self._ensure_initialized()
        if not ok:
            return {"ok": False, "message": detail, "request": request}
        try:
            symbol = request["symbol"]
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
            result = mt5.order_send(mt5_request)
            ok_result = bool(result and result.retcode in SUCCESS_RETCODES)
            return {"ok": ok_result, "dryRun": False, "request": request, "mt5Request": mt5_request, "result": result._asdict() if result else str(mt5.last_error())}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "request": request}

    def split_target_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = str(payload.get("symbol", self.symbol))
        side = str(payload.get("side", "BUY")).upper()
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
