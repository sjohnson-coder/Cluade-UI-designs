from __future__ import annotations

import os
import asyncio
import time
import threading
import json
import urllib.parse
import urllib.request
from copy import deepcopy
from pathlib import Path
from collections import defaultdict, deque
from typing import Any

from fastapi import Body, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from services.backtesting import MonteCarloTester, TradeReplayEngine, WalkForwardBacktester
from services.backtest_engine import CostAwareBacktester
from services.strategy_lab import StrategyLab
from services import ai_strategy_gen
from services.decision_engine import GoldDecisionEngine
from services.live_execution import BrokerSpecificLotSizer, ExposureValidator, LiveExecutionManager
from services.live_market_feeds import EconomicCalendarAPI, MacroFeed, TickDataBacktester
from services.market_intelligence import EconomicCalendar, GoldVolatilityRegime, MacroAwareness, MarketCleanliness
from services.mt5_bridge import MT5Bridge
from services.performance_memory import PerformanceMemory
from services.pyramiding import AIPyramidingEngine
from services.reporting_versioning import ForwardTestReporter, TradeReplayStorage, VersionRegistry
from services.risk_controls import BrokerExecutionScorer, EmergencyKillSwitch, OverfittingGuard
from services.strategy_catalog import INSTITUTIONAL_STRATEGIES
from services.super_intelligence import SuperIntelligenceSummary
from services.trade_management import MultiTargetTradeManager
from services.trade_context import TradeContextStore, comment_for, strategy_from_comment, entry_type_label
from services.ai_reviewer import AITradeReviewer
from services.ai_monitor import assess_recovery, compute_widened_sl
from services import chart_render
from services import demo_data


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [x.strip() for x in value.split(",") if x.strip()]


app = FastAPI(title="GodMode Gold Trading Bot API", version="3.2.0-functional-mt5-controls")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

allowed_origins = _csv_env("GODMODE_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
allowed_hosts = _csv_env("GODMODE_ALLOWED_HOSTS", "127.0.0.1,localhost,*.localhost,testserver")
rate_limit_per_minute = int(os.getenv("GODMODE_RATE_LIMIT_PER_MINUTE", "240"))
api_key = os.getenv("GODMODE_API_KEY", "").strip()

app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "X-GodMode-Key"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend_assets")

_rate_bucket: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client = request.client.host if request.client else "local"
    now = time.time()
    q = _rate_bucket[client]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= rate_limit_per_minute:
        return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    q.append(now)

    if api_key and request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-GodMode-Key") != api_key:
            return JSONResponse({"detail": "Invalid or missing GodMode API key"}, status_code=401)

    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


mt5_bridge = MT5Bridge()
decision_engine = GoldDecisionEngine()
memory = PerformanceMemory()
walk_forward = WalkForwardBacktester()
monte_carlo = MonteCarloTester()
backtester = CostAwareBacktester()
strategy_lab = StrategyLab()
LAB_STATE: dict[str, Any] = {"lastRun": 0.0, "lastResult": None, "lastRecSig": None, "installedProfile": None}
# Last Backtest / Validate result — persisted in memory so the result is still viewable after you
# click away to another tab (or come back later), exactly like the Strategy Lab. Served by
# /api/backtest/last and reloaded by the Backtest tab on mount.
BACKTEST_STATE: dict[str, Any] = {"lastRun": 0.0, "lastResult": None, "lastValidation": None}
# The AI strictness keys a Strategy-Lab install is allowed to change. Snapshotting these before an
# install is what makes the install REVERSIBLE (see /api/lab/install + /api/lab/uninstall).
_LAB_GATE_KEYS = ("strictnessMode", "scoutConfidence", "standardConfidence", "sniperConfidence",
                  "minRiskReward", "maxSpread", "minEfficiencyRatio", "minConfluence", "allowScoutEntries")
replay_engine = TradeReplayEngine()
calendar = EconomicCalendar()
macro = MacroAwareness()
volatility = GoldVolatilityRegime()
cleanliness = MarketCleanliness()
kill_switch = EmergencyKillSwitch()
broker_scorer = BrokerExecutionScorer()
overfitting_guard = OverfittingGuard()
trade_manager = MultiTargetTradeManager()
pyramiding_engine = AIPyramidingEngine()
super_summary = SuperIntelligenceSummary()
live_calendar = EconomicCalendarAPI()
macro_feed = MacroFeed()
tick_backtester = TickDataBacktester()
lot_sizer = BrokerSpecificLotSizer()
live_execution = LiveExecutionManager(lot_sizer)
exposure_validator = ExposureValidator()
replay_storage = TradeReplayStorage()
version_registry = VersionRegistry()
forward_reporter = ForwardTestReporter()

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

# Strategy-attribution + AI learning state.
trade_context = TradeContextStore(str(DATA_DIR / "trade_context.json"))
ai_reviewer = AITradeReviewer()
TRADE_REVIEWS: dict[str, dict[str, Any]] = {}   # ticket -> AI post-trade review
RECORDED_TICKETS: set[str] = set()               # tickets already learned into memory
OUTCOME_REGISTERED: set[str] = set()             # tickets already counted toward loss-streak

# Learned confidence-factor weights (from the cost-aware backtest optimizer).
FACTOR_WEIGHTS_FILE = DATA_DIR / "factor_weights.json"

# ── Decision & Management Journal ────────────────────────────────────────────────────────
# A persisted, queryable log of WHY the bot did (or did not) trade and every management action
# it took, so the recurring "why didn't it trade X?" question is always answerable after the fact.
DECISION_JOURNAL_FILE = DATA_DIR / "decision_journal.jsonl"
DECISION_JOURNAL: list[dict[str, Any]] = []
_LAST_ENTRY_SIG: dict[str, Any] = {"sig": None}

# Manual journal entries the user writes (reflections / lessons), separate from auto bot-trade entries.
MANUAL_JOURNAL_FILE = DATA_DIR / "manual_journal.jsonl"
MANUAL_JOURNAL: list[dict[str, Any]] = []
try:
    if MANUAL_JOURNAL_FILE.exists():
        for _line in MANUAL_JOURNAL_FILE.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line:
                MANUAL_JOURNAL.append(json.loads(_line))
except Exception:
    MANUAL_JOURNAL = []

def _journal_record(category: str, **fields: Any) -> dict[str, Any]:
    evt = {"id": int(time.time() * 1000000) % 1_000_000_000,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "epoch": round(time.time(), 3), "category": category, **fields}
    DECISION_JOURNAL.insert(0, evt)
    del DECISION_JOURNAL[5000:]
    try:
        with DECISION_JOURNAL_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evt, default=str) + "\n")
    except Exception:
        pass
    return evt

def _journal_entry_decision(result: dict[str, Any], heartbeat: dict[str, Any]) -> None:
    """Record an ENTRY decision — but only on a TAKE or when the SKIP reason CHANGES, so the
    log shows meaningful transitions instead of thousands of identical 3-second 'waiting' ticks."""
    matrix = result.get("actionMatrix") or {}
    mdec = matrix.get("decision") or {}
    took = bool(result.get("ok")) and not result.get("blocked")
    blocks = list(heartbeat.get("blockedReasons") or [])
    primary = str(blocks[0]) if blocks else (result.get("reason") or "")
    sig = ("TAKE" if took else "SKIP") + "|" + (str(mdec.get("computedSide") or mdec.get("side") or "")) + "|" + primary[:60]
    if not took and sig == _LAST_ENTRY_SIG.get("sig"):
        return  # same waiting state as last tick — don't spam the journal
    _LAST_ENTRY_SIG["sig"] = sig
    _journal_record("entry",
                    decision="TAKE_TRADE" if took else "SKIP_OR_WAIT",
                    side=mdec.get("computedSide") or mdec.get("side"),
                    confidence=heartbeat.get("confidence"),
                    quality=heartbeat.get("quality"),
                    strategy=(mdec.get("selectedStrategy") or {}).get("name") or mdec.get("strategy"),
                    reason=(result.get("message") or result.get("reason") or "")[:240],
                    blocks=blocks[:4], softBlocks=list(heartbeat.get("softBlocks") or [])[:3],
                    opened=took)

def _load_decision_journal() -> None:
    try:
        if DECISION_JOURNAL_FILE.exists():
            for ln in DECISION_JOURNAL_FILE.read_text(encoding="utf-8").splitlines()[-5000:]:
                try:
                    DECISION_JOURNAL.append(json.loads(ln))
                except Exception:
                    pass
            DECISION_JOURNAL.sort(key=lambda e: e.get("epoch", 0), reverse=True)
            del DECISION_JOURNAL[5000:]
    except Exception:
        pass

def _load_factor_weights() -> None:
    if FACTOR_WEIGHTS_FILE.exists():
        try:
            w = json.loads(FACTOR_WEIGHTS_FILE.read_text(encoding="utf-8"))
            if isinstance(w, dict) and w:
                decision_engine.set_factor_weights(w)
        except Exception:
            pass

def _save_factor_weights(weights: dict[str, Any]) -> None:
    try:
        FACTOR_WEIGHTS_FILE.write_text(json.dumps(weights, indent=2), encoding="utf-8")
    except Exception:
        pass

_load_factor_weights()
_load_decision_journal()

def _tf_default_bars(tf: str) -> int:
    """A sensible ~2-3 year sample size per timeframe (so Validate uses comparable history)."""
    return {"M1": 120000, "M5": 100000, "M15": 70000, "H1": 14000, "H4": 4200, "D1": 1500}.get(str(tf).upper(), 70000)


def _backtest_candles(count: int, timeframe: str | None = None) -> list[dict[str, Any]]:
    """Candles for backtesting at the requested timeframe (falls back to your configured
    trading timeframe, else M15): real MT5 history when connected, else a synthetic series so the
    harness still runs (results on synthetic data are illustrative only)."""
    tf = str(timeframe or (SETTINGS_STATE.get("trading") or {}).get("timeframe") or "M15").upper()
    if tf not in {"M1", "M5", "M15", "H1", "H4", "D1"}:
        tf = "M15"
    count = max(300, min(int(count or 4000), 120000))   # up to ~3.4 years of M15 for real validation
    if mt5_bridge.status().get("connected"):
        sym = str((SETTINGS_STATE.get("trading") or {}).get("symbol", mt5_bridge.symbol))
        rows = mt5_bridge.copy_rates(symbol=sym, timeframe=tf, count=count)
        if rows:
            return rows
    try:
        return demo_data._candles(count, tf)
    except Exception:
        return []

def _default_settings() -> dict[str, Any]:
    return {
        "appearance": {"theme": "light", "accentColor": "gold", "density": "comfortable"},
        "trading": {"symbol": os.getenv("MT5_SYMBOL", "XAUUSD"), "timeframe": "M15", "orderType": "Market", "riskPerTrade": 0.5, "slippageTolerance": 0.5, "magicNumber": mt5_bridge.magic, "commentPrefix": mt5_bridge.comment_prefix, "autoRefreshData": True, "autoResumeOnStart": False, "allowedSessions": ["Asia", "London", "London / New York", "New York"], "tradeManagement": {"autoBreakEven": True, "breakEvenAtRR": 0.4, "autoTrailing": True, "trailStartRR": 0.5, "trailAtrMult": 1.0, "trailStructure": "M15", "fastFailEnabled": True, "fastFailLossR": -0.5, "fastFailNoProgressCandles": 3, "partialTakeProfit": True, "tpPushEnabled": True, "protectStartAtr": 0.4, "profitLockFraction": 0.35, "trailStartAtr": 0.7, "smartRecoveryRoom": True, "recoveryRoomAtr": 0.3}},
        "execution": {"dryRun": not mt5_bridge.live_enabled, "liveTradingEnabled": mt5_bridge.live_enabled, "autoTradingEnabled": mt5_bridge.auto_trading_enabled, "requireAiApproval": True, "manualExecutionEnabled": False},
        "ai": {"strictnessMode": "balanced", "allowScoutEntries": True, "scoutConfidence": 72.0, "standardConfidence": 78.0, "sniperConfidence": 90.0, "minRiskReward": 1.5, "maxSpread": 0.40, "showBlockedReasons": True, "heartbeatEnabled": True, "firstEntryLotMode": "base_lot_only", "respectAllowedSessions": True, "rangeAwareness": True, "rangeFade": False, "rangeTopPos": 0.78, "rangeBottomPos": 0.22, "costDiscipline": True, "maxSpreadAtrFrac": 0.05, "commissionPrice": 0.0, "confluenceByMode": {"relaxed": 2, "balanced": 3, "strict": 4, "sniper": 5}},
        # Automation discipline: stop revenge-stacking and run the AI recovery monitor.
        "automation": {
            "postLossCooldownMinutes": 10.0,     # forced reanalysis pause after any loss
            "lossStreakPause": 3,                # consecutive losses that trigger a hard pause
            "lossStreakPauseMinutes": 60.0,      # length of that hard pause
            "blockRepeatFailedSetup": True,      # don't re-enter the same losing idea
            "repeatBlockMinutes": 20.0,
            "recoveryMonitorEnabled": True,      # AI decides hold-vs-cut instead of a blunt counter
            "recoveryHoldThreshold": 62.0,       # score >= hold → keep the trade
            "recoveryCutThreshold": 38.0,        # score <= cut  → close now
            "dynamicSlEnabled": False,           # allow AI to widen SL toward structure (OFF by default)
            "dynamicSlMaxRiskPct": 1.0,          # HARD cap: widened SL can never risk more than this % equity
            "mql5ControlFilePath": "",           # MT5 \MQL5\Files path -> writes godmode_control.csv for the tick EA
            # Hedge/scalp mode: on a RETAIL_HEDGING account, allow an extra independent
            # high-quality scalp alongside an open trade (instead of a pyramid add),
            # with the same strict BE/trail/fast-fail protection.
            "scalpHedgeEnabled": False,
            "scalpMaxConcurrent": 2,
            "scalpMinQuality": "STANDARD",       # STANDARD or SNIPER only
            "winStreakLotScaling": True,         # scale each NEW trade's lot on a win streak
            "volNormalizedSizing": True,         # size BASE lot to risk ~trading.riskPerTrade% per trade (constant $ risk)
        },
        "mt5Connection": {"terminalPath": mt5_bridge.terminal_path, "login": mt5_bridge.login, "password": "", "server": mt5_bridge.server, "autoConnect": True},
        "risk": {"maxDailyLossPct": 5.0, "maxOpenTrades": 3, "maxCorrelatedTrades": 1, "equityStopLossPct": 20.0, "useEquityProtection": True},
        "pyramiding": pyramiding_engine.settings_dict(camel=True),
        "notifications": {"tradeExecutions": True, "strategyAlerts": True, "riskAlerts": True, "dailySummary": True, "systemUpdates": True, "promotionsTips": False, "soundPreset": "chime", "soundEnabled": True},
        "telegram": {"enabled": False, "botToken": "", "chatId": "", "sendCharts": True, "sendWaitForecast": False, "waitForecastMinutes": 30.0, "dailyRecap": True, "weeklyRecap": True, "recapHourUtc": 21},
        "mobile": {"lanAccessEnabled": False, "bindHost": "127.0.0.1", "port": 8000},
        "dataFeeds": {"dxyUrl": os.getenv("DXY_FEED_URL", "") or os.getenv("GODMODE_DXY_URL", ""),
                      "us10yUrl": os.getenv("US10Y_FEED_URL", "") or os.getenv("GODMODE_US10Y_URL", ""),
                      "economicCalendarUrl": os.getenv("ECONOMIC_CALENDAR_URL", "") or os.getenv("GODMODE_ECONOMIC_CALENDAR_URL", ""),
                      "dxyKey": "", "us10yKey": "", "economicCalendarKey": ""},
        "aiProvider": {"enabled": False, "provider": "claude", "apiKey": "",
                       "model": "", "candidatesPerRun": 3},
        "strategyLab": {"feedUrl": "", "feedKey": "", "autoRunDaily": False,
                        "autoRunHourUtc": 22, "improveMarginR": 0.05,
                        # Auto-pilot (opt-in): when NO enabled strategy fits the current market, the bot
                        # runs the Lab, auto-installs the best candidate that beats your edge out-of-sample,
                        # and alerts Telegram with Uninstall/Keep buttons. Off by default.
                        "autoDiscover": False, "autoDiscoverCooldownMin": 60},
        "security": {"requireApiKey": bool(api_key), "maskAccountBalance": False, "autoLogoutMinutes": 30},
        "meta": {"lastSaved": None, "source": "persistent_json"},
    }

def _first_number(text: str) -> float | None:
    import re
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base

def _load_settings() -> dict[str, Any]:
    base = _default_settings()
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                _deep_merge(base, saved)
        except Exception:
            pass
    return base

def _save_settings() -> None:
    SETTINGS_FILE.write_text(json.dumps(SETTINGS_STATE, indent=2, default=str), encoding="utf-8")

SETTINGS_STATE = _load_settings()


def _apply_data_feed_env() -> dict[str, Any]:
    """Push the Settings → Data Feeds URLs/keys into os.environ under BOTH naming conventions
    (``*_FEED_URL`` for the decision engine and ``GODMODE_*_URL`` for the display feeds) so a
    single config drives everything, then clear the feed caches so it takes effect immediately."""
    df = SETTINGS_STATE.get("dataFeeds", {}) if isinstance(SETTINGS_STATE.get("dataFeeds"), dict) else {}
    mapping = {
        "dxyUrl": ("DXY_FEED_URL", "GODMODE_DXY_URL"),
        "us10yUrl": ("US10Y_FEED_URL", "GODMODE_US10Y_URL"),
        "economicCalendarUrl": ("ECONOMIC_CALENDAR_URL", "GODMODE_ECONOMIC_CALENDAR_URL"),
        "dxyKey": ("DXY_FEED_KEY", "GODMODE_DXY_KEY"),
        "us10yKey": ("US10Y_FEED_KEY", "GODMODE_US10Y_KEY"),
        "economicCalendarKey": ("ECONOMIC_CALENDAR_KEY", "GODMODE_ECONOMIC_CALENDAR_KEY"),
    }
    for skey, envs in mapping.items():
        val = str(df.get(skey, "") or "").strip()
        for env in envs:
            if val:
                os.environ[env] = val
            else:
                os.environ.pop(env, None)
    for obj in (calendar, macro, getattr(decision_engine, "calendar", None), getattr(decision_engine, "macro", None)):
        try:
            if obj is not None and hasattr(obj, "force_refresh"):
                obj.force_refresh()
        except Exception:
            pass
    return {"dxyConfigured": bool(str(df.get("dxyUrl", "")).strip()),
            "us10yConfigured": bool(str(df.get("us10yUrl", "")).strip()),
            "calendarConfigured": bool(str(df.get("economicCalendarUrl", "")).strip())}


_apply_data_feed_env()  # sync env <- persisted Data Feeds settings at startup

AUTO_TRADE_STATE: dict[str, Any] = {"enabled": False, "lastFire": 0.0, "lastResult": None, "cooldownSeconds": 15,
                                    "lossStreak": 0, "winStreak": 0, "postLossUntil": 0.0, "pausedUntil": 0.0, "lastLoser": None}
AUTO_TRADE_HEARTBEAT: list[dict[str, Any]] = []

NOTIFICATIONS: list[dict[str, Any]] = []
RECENT_CLOSED_TRADE_CACHE: list[dict[str, Any]] = []

# Decision cache: shared across /dashboard, /signals, /ai/decision so all pages show the same signal
_DECISION_CACHE: dict[str, Any] = {}
_DECISION_CACHE_TS: float = 0.0
_DECISION_CACHE_TTL: float = 4.0  # seconds


def _market_state() -> dict[str, Any]:
    """Is the market open? {open: bool, reason: str, source: str}. Weekend schedule (UTC) confirmed
    by live tick-staleness when MT5 is connected (see mt5_bridge.market_open)."""
    try:
        return mt5_bridge.market_open()
    except Exception:
        return {"open": True, "reason": "Open", "source": "unknown"}


def _cached_decision() -> dict[str, Any]:
    global _DECISION_CACHE, _DECISION_CACHE_TS
    if time.time() - _DECISION_CACHE_TS < _DECISION_CACHE_TTL and _DECISION_CACHE:
        return _DECISION_CACHE
    market = _live_market()
    # Let the engine honour the user's enabled sessions (so e.g. Asia trades when ON).
    _tcfg = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    _aicfg = SETTINGS_STATE.get("ai", {}) if isinstance(SETTINGS_STATE.get("ai"), dict) else {}
    market = {**market, "allowedSessions": _tcfg.get("allowedSessions"), "respectAllowedSessions": _aicfg.get("respectAllowedSessions", True)}
    # STRATEGIES_STATE is defined at module level after _apply_runtime_settings()
    strats = list(globals().get("STRATEGIES_STATE", {}).values())
    result = decision_engine.evaluate(market, strats, memory.stats()) if market.get("connected") else {"action": "WAIT", "confidence": 0, "quality": "NO_DATA", "reasons": ["MT5 not connected."]}
    mkt_state = _market_state()
    if not mkt_state.get("open", True):
        # Market is closed — surface it clearly and stand down (no entries while closed).
        result = {**result, "action": "MARKET_CLOSED", "quality": "MARKET_CLOSED",
                  "reason": f"Market closed — {mkt_state.get('reason', 'outside trading hours')}."}
    _DECISION_CACHE = {**result, "_market": market,
                       "marketOpen": bool(mkt_state.get("open", True)),
                       "marketStatus": mkt_state.get("reason", "")}
    _DECISION_CACHE_TS = time.time()
    return _DECISION_CACHE


def _push_notification(title: str, message: str, kind: str = "info", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item = {
        "id": int(time.time() * 1000),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": title,
        "message": message,
        "kind": kind,
        "payload": payload or {},
        "read": False,
    }
    NOTIFICATIONS.insert(0, item)
    del NOTIFICATIONS[50:]
    return item



def _merge_recent_closed(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge immediately-closed trades into the MT5 history for instant display.

    When a trade closes through the bot UI, it's added to RECENT_CLOSED_TRADE_CACHE
    so it appears instantly in the Trades page without waiting for MT5 history
    propagation (which can take minutes to hours). Once MT5 history has the deal,
    the cached version is excluded to avoid duplicates.
    """
    seen = {str(x.get("ticket")) for x in history if x.get("ticket") is not None}
    # Also prune cache entries older than 24 hours to avoid indefinite accumulation
    cutoff = time.time() - 86400
    fresh = [
        x for x in RECENT_CLOSED_TRADE_CACHE
        if str(x.get("ticket")) not in seen and float(x.get("_cacheTs", time.time())) > cutoff
    ]
    combined = fresh + history
    return combined[:250]


def _cache_close_event_with_ts(payload: dict[str, Any], result: dict[str, Any]) -> None:
    """Cache a just-closed trade for immediate display (bypasses MT5 history delay)."""
    if not result.get("ok"):
        return
    item = {
        "ticket": payload.get("ticket") or payload.get("position") or (result.get("request") or {}).get("position"),
        "symbol": payload.get("symbol") or (result.get("request") or {}).get("symbol") or mt5_bridge.symbol,
        "direction": payload.get("direction") or payload.get("side") or "—",
        "lots": payload.get("volume") or payload.get("lots") or (result.get("request") or {}).get("volume") or "—",
        "entryPrice": payload.get("entryPrice") or "—",
        "exitPrice": payload.get("exitPrice") or payload.get("currentPrice") or "—",
        "pnlUsd": payload.get("pnlUsd", 0.0),
        "pnlPct": payload.get("pnlPct", 0.0),
        "holdTime": payload.get("holdTime", "Just closed"),
        "closeTime": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "closeTimestamp": time.time(),
        "reason": result.get("message") or "Close request confirmed",
        "magicNumber": mt5_bridge.magic,
        "comment": f"{mt5_bridge.comment_prefix}recent_close",
        "source": "recent_close_cache",
        "_cacheTs": time.time(),
    }
    RECENT_CLOSED_TRADE_CACHE.insert(0, item)
    del RECENT_CLOSED_TRADE_CACHE[30:]


# (replaced by _cache_close_event_with_ts above)


# ── Strategy attribution + AI learning loop ──────────────────────────────────
def _capture_entry_context(result: dict[str, Any], decision: dict[str, Any] | None, payload: dict[str, Any], entry_type: str, strategy_name: str | None = None) -> None:
    """Persist the real strategy + entry rationale for a just-opened trade, keyed by
    every plausible MT5 identifier so closed-trade history can be attributed later."""
    if not result.get("ok"):
        return
    res = result.get("result") if isinstance(result.get("result"), dict) else {}
    req = result.get("request") if isinstance(result.get("request"), dict) else {}
    tickets = [result.get("ticket"), res.get("order"), res.get("deal"), res.get("position"), req.get("position")]
    decision = decision or {}
    plan = decision.get("tradePlan", {}) if isinstance(decision.get("tradePlan"), dict) else {}
    strat = strategy_name or (decision.get("selectedStrategy", {}) or {}).get("name") or "GodMode Bot"
    ctx = {
        "strategy": strat,
        "entryType": entry_type,
        "side": str(payload.get("side") or payload.get("direction") or decision.get("side") or "").upper() or None,
        "symbol": payload.get("symbol") or decision.get("symbol") or mt5_bridge.symbol,
        "entry": _to_float(plan.get("entry") or payload.get("price") or 0) or None,
        "sl": _to_float(plan.get("sl") or payload.get("sl") or 0) or None,
        "tp1": _to_float(plan.get("tp1") or 0) or None,
        "tp2": _to_float(plan.get("tp2") or 0) or None,
        "tp3": _to_float(plan.get("tp3") or 0) or None,
        "tp4": _to_float(plan.get("tp4") or 0) or None,
        "confidence": decision.get("confidence"),
        "session": decision.get("sessionName") or _live_market().get("session"),
        "regime": decision.get("marketRegime"),
        "reason": decision.get("reason"),
        "quality": decision.get("quality"),
        "partialsTaken": 0,
    }
    trade_context.record_entry(tickets, ctx)


def _trade_r_multiple(t: dict[str, Any], ctx: dict[str, Any] | None) -> float | None:
    """Best-effort realised R from the planned stop distance (needs entry context)."""
    ctx = ctx or {}
    entry = _to_float(ctx.get("entry") or t.get("entryPrice"))
    sl = _to_float(ctx.get("sl"))
    lots = _to_float(t.get("lots") or t.get("volume"))
    pnl = _to_float(t.get("pnlUsd"))
    if entry and sl and lots:
        risk_usd = abs(entry - sl) * lots * 100  # XAUUSD: ~$100 per $1 move per lot
        if risk_usd > 0:
            return round(pnl / risk_usd, 2)
    return None


def _enrich_closed_trade(t: dict[str, Any]) -> dict[str, Any]:
    """Attach real strategy, human reason, R-multiple and any AI review to a trade."""
    ctx = trade_context.match(
        t.get("ticket"), t.get("positionId"), t.get("symbol"),
        t.get("direction") or t.get("side"), _to_float(t.get("entryPrice")), _to_float(t.get("openTimestamp")),
    )
    comment = str(t.get("comment") or "")
    strategy = (ctx or {}).get("strategy") or strategy_from_comment(comment) or "GodMode Bot"
    entry_label = (ctx or {}).get("entryType") or entry_type_label(comment)
    exit_reason = t.get("exitReason") or t.get("reason") or "Closed"
    r_mult = t.get("rMultiple")
    if r_mult is None:
        r_mult = _trade_r_multiple(t, ctx)
    bits = [strategy] + ([entry_label] if entry_label else [])
    reason = f"{' · '.join(bits)} → {exit_reason}"
    if r_mult is not None:
        reason += f" ({r_mult:+.2f}R)"
    out = {
        **t,
        "strategy": strategy,
        "entryReason": (ctx or {}).get("reason"),
        "exitReason": exit_reason,
        "reason": reason,
        "rMultiple": r_mult,
        "confidence": (ctx or {}).get("confidence", t.get("confidence", 0)) or 0,
        "session": (ctx or {}).get("session") or t.get("session"),
        "marketRegime": (ctx or {}).get("regime") or t.get("marketRegime"),
    }
    review = TRADE_REVIEWS.get(str(t.get("ticket")))
    if review:
        out["aiReview"] = review
        out["aiScore"] = review.get("aiScore")
        out["aiNotes"] = review.get("summary")
        out["lessons"] = review.get("lesson")
        out["improvement"] = review.get("improvement")
        out["aiAdjustment"] = review.get("adjustment")
    return out


def _maybe_learn(t: dict[str, Any]) -> None:
    """Record a closed bot trade into performance memory + run the AI reviewer once.
    Idempotent per ticket; skipped for demo data so the learning DB stays real."""
    if not mt5_bridge.status().get("connected"):
        return  # never learn from demo / offline data
    tk = str(t.get("ticket") or "")
    if not tk or tk == "None" or tk in RECORDED_TICKETS:
        return
    enriched = _enrich_closed_trade(t)
    pnl = _to_float(enriched.get("pnlUsd"))
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"
    record = {
        "symbol": enriched.get("symbol", "XAUUSD"),
        "strategy": enriched.get("strategy"),
        "session": enriched.get("session"),
        "side": enriched.get("direction") or enriched.get("side"),
        "confidence": enriched.get("confidence"),
        "spread": None,
        "slippage": None,
        "pnl": pnl,
        "rMultiple": enriched.get("rMultiple"),
        "outcome": outcome,
        "source": "godmode_bot",
        "magic": t.get("magicNumber") or mt5_bridge.magic,
        "comment": t.get("comment"),
    }
    res = memory.record_trade(record)
    if res.get("recorded"):
        RECORDED_TICKETS.add(tk)
        try:
            review = ai_reviewer.review(enriched)
            TRADE_REVIEWS[tk] = review
            memory.auto_journal("TRADE_REVIEW", f"{enriched.get('strategy')} {outcome} {pnl:+.2f} USD", json.dumps(review, default=str))
        except Exception:
            pass


def _enrich_history(history: list[dict[str, Any]], learn: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in history:
        if learn:
            _maybe_learn(t)
        out.append(_enrich_closed_trade(t))
    return out


def _register_close_outcome(ticket: Any, pnl: float, side: Any, price: Any, session: Any = None) -> None:
    """Drive the post-loss cooldown + loss-streak circuit breaker after every close.
    A loss starts a reanalysis cooldown; a run of losses pauses auto-entry entirely;
    a win resets the streak. Deduped per ticket so one trade counts once. This is what
    stops the bot revenge-stacking entries."""
    tk = str(ticket or "")
    if tk and tk in OUTCOME_REGISTERED:
        return
    if tk:
        OUTCOME_REGISTERED.add(tk)
    auto = SETTINGS_STATE.get("automation", {}) if isinstance(SETTINGS_STATE.get("automation"), dict) else {}
    now = time.time()
    pnl = _to_float(pnl)
    try:
        _journal_record("close", ticket=tk, side=str(side or "").upper(), pnlUsd=round(pnl, 2),
                        price=_to_float(price), session=session,
                        outcome="WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT")
    except Exception:
        pass
    # Daily realized P&L (drives the daily-loss circuit breaker), reset per UTC day.
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if AUTO_TRADE_STATE.get("dayKey") != day:
        AUTO_TRADE_STATE["dayKey"] = day
        AUTO_TRADE_STATE["dailyRealizedPnl"] = 0.0
        AUTO_TRADE_STATE["dailyHaltAlerted"] = False
    AUTO_TRADE_STATE["dailyRealizedPnl"] = round(float(AUTO_TRADE_STATE.get("dailyRealizedPnl", 0.0)) + pnl, 2)
    if pnl < 0:
        streak = int(AUTO_TRADE_STATE.get("lossStreak", 0)) + 1
        AUTO_TRADE_STATE["lossStreak"] = streak
        AUTO_TRADE_STATE["postLossUntil"] = now + float(auto.get("postLossCooldownMinutes", 10)) * 60
        AUTO_TRADE_STATE["lastLoser"] = {"side": str(side or "").upper(), "price": _to_float(price), "ts": now, "session": session}
        AUTO_TRADE_STATE["winStreak"] = 0
        limit = int(auto.get("lossStreakPause", 3))
        if limit and streak >= limit:
            pause_min = float(auto.get("lossStreakPauseMinutes", 60))
            AUTO_TRADE_STATE["pausedUntil"] = now + pause_min * 60
            _management_alert("Auto-entry paused", f"{streak} consecutive losses — auto-entry paused {pause_min:.0f} min for re-analysis. Manually review the market before resuming.", "danger")
    elif pnl > 0:
        AUTO_TRADE_STATE["lossStreak"] = 0
        AUTO_TRADE_STATE["winStreak"] = int(AUTO_TRADE_STATE.get("winStreak", 0)) + 1


def _write_mql5_control(lines: list[str]) -> None:
    """Write HOLD/CUT directives for the GodModeTickGuard MT5 EA, when a path is set.
    The EA reads this each second so the AI's recovery verdict is enforced at ~tick
    speed (CUT closes next tick; HOLD stops the EA cutting a recovering trade early)."""
    auto = SETTINGS_STATE.get("automation", {}) if isinstance(SETTINGS_STATE.get("automation"), dict) else {}
    path = str(auto.get("mql5ControlFilePath", "") or "").strip()
    if not path:
        return
    try:
        p = Path(path)
        if p.is_dir() or not p.suffix:
            p = p / "godmode_control.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(("\n".join(lines) + "\n") if lines else "", encoding="ascii", errors="ignore")
    except Exception:
        pass


def _telegram_creds() -> tuple[str, str]:
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    return (str(tg.get("botToken") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip(),
            str(tg.get("chatId") or os.getenv("TELEGRAM_CHAT_ID", "")).strip())


def _telegram_send_text(text: str, buttons: list[list[dict[str, str]]] | None = None) -> dict[str, Any]:
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    enabled = bool(tg.get("enabled") or os.getenv("TELEGRAM_ENABLED", "").lower() in {"1", "true", "yes"})
    token, chat_id = _telegram_creds()
    if not enabled:
        return {"ok": False, "skipped": True, "message": "Telegram is disabled in Settings."}
    if not token or not chat_id:
        return {"ok": False, "message": "Telegram Bot Token and Chat ID are required."}
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if buttons:   # inline keyboard: [[{"text":..,"callback_data":..}], ...]
            payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        return {"ok": True, "message": "Telegram notification sent.", "telegramResponse": raw[:500]}
    except Exception as exc:
        return {"ok": False, "message": f"Telegram send failed: {exc}"}


def _telegram_send_photo(image: bytes | None, caption: str = "") -> dict[str, Any]:
    """Send a PNG chart to Telegram (multipart/form-data, stdlib only)."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not bool(tg.get("enabled")) or not tg.get("sendCharts", True) or not image:
        return {"ok": False, "skipped": True}
    token = str(tg.get("botToken") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(tg.get("chatId") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return {"ok": False, "message": "Telegram credentials required."}
    try:
        boundary = "----GodMode" + str(int(time.time() * 1000))
        def field(name: str, value: str) -> bytes:
            return (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode()
        body = field("chat_id", chat_id) + field("caption", caption[:1024]) + field("parse_mode", "Markdown")
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="chart.png"\r\nContent-Type: image/png\r\n\r\n').encode()
        body += image + b"\r\n" + (f"--{boundary}--\r\n").encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "message": f"Telegram photo failed: {exc}"}


def _trade_chart_image(side: str, entry: Any, sl: Any, tps: list[Any], subtitle: str = "") -> bytes | None:
    """Render the current XAUUSD chart with entry/SL/TP annotated for an alert."""
    if not chart_render.available():
        return None
    try:
        trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
        symbol = str(trading.get("symbol", mt5_bridge.symbol))
        tf = str(trading.get("timeframe", "M15"))
        # Use the RAW MT5 snapshot — never the demo/synthetic fallback. A live alert must show
        # the user's REAL broker candles or no chart at all; a synthetic chart is exactly what
        # "the candles don't match" was. If MT5 isn't connected we skip the image (text still sends).
        snap = mt5_bridge.market_snapshot(symbol, tf)
        candles = snap.get("candles") or []
        if not snap.get("connected") or not candles:
            return None
        clean_tps = [float(t) for t in (tps or []) if t]
        last = candles[-1]
        try:
            ohlc = f"O{float(last['open']):.2f} H{float(last['high']):.2f} L{float(last['low']):.2f} C{float(last['close']):.2f}"
        except Exception:
            ohlc = ""
        sub = ((subtitle + " · ") if subtitle else "") + f"{tf} • {ohlc} • {last.get('timeLabel','')} server time"
        return chart_render.render_trade_chart(
            candles, side=str(side), entry=float(entry) if entry else None,
            sl=float(sl) if sl else None, tps=clean_tps,
            title=str(snap.get("symbol", symbol)), subtitle=sub, timeframe=tf, live=True,
        )
    except Exception:
        return None


def _telegram_rich_trade_alert(headline: str, side: str, symbol: str, volume: Any,
                               entry: Any, sl: Any, tps: list[Any], confidence: Any,
                               strategy: str, reason: str, kind: str = "info",
                               confidence_label: str = "Confidence") -> None:
    """Send a full Telegram alert: side/entry/SL/TP/confidence/strategy/reason + chart."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return
    emoji = {"success": "🟢", "warning": "🟡", "danger": "🔴", "info": "🔵"}.get(kind, "🔵")
    tp_line = ""
    clean_tps = [t for t in (tps or []) if t]
    if clean_tps:
        tp_line = "\n".join(f"  TP{i+1}: `{float(t):.2f}`" for i, t in enumerate(clean_tps[:4]))
    lines = [f"{emoji} *GodMode — {headline}*", f"*{side} {symbol}*  ·  {volume} lots"]
    if entry:
        lines.append(f"Entry: `{float(entry):.2f}`")
    if sl:
        lines.append(f"SL: `{float(sl):.2f}`")
    if tp_line:
        lines.append(tp_line)
    if confidence:
        lines.append(f"{confidence_label}: *{int(float(confidence))}%*")
    if strategy:
        lines.append(f"Strategy: _{strategy}_")
    if reason:
        lines.append(f"\n📋 {str(reason)[:380]}")
    _ctf = str((SETTINGS_STATE.get("trading", {}) or {}).get("timeframe", "M15"))
    lines.append(f"\n📊 _Chart = real MT5 {_ctf} candles, server-time axis (matches your platform). Set your chart to {_ctf}; the O/H/L/C printed on it should equal your last {_ctf} candle. No chart = MT5 not connected._")
    text = "\n".join(lines)
    img = _trade_chart_image(side, entry, sl, clean_tps, subtitle=f"{strategy} · conf {int(float(confidence or 0))}%")
    if img:
        photo = _telegram_send_photo(img, text)
        if photo.get("ok"):
            return
    _telegram_send_text(text)  # fallback to text if no chart / send failed


def _telegram_rich_close_alert(direction: str, symbol: str, ticket: Any, exit_price: Any,
                               pnl: float, r_mult: Any, reason: str, kind: str = "success") -> None:
    """Send a full Telegram close alert: PnL, R, reason + a chart of the exit."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return
    emoji = "🟢" if pnl >= 0 else "🔴"
    lines = [f"{emoji} *GodMode — Trade closed*", f"*{direction} {symbol}*  #{ticket}"]
    if exit_price:
        lines.append(f"Exit: `{float(exit_price):.2f}`")
    lines.append(f"PnL: *{pnl:+.2f} USD*" + (f"  ({float(r_mult):+.2f}R)" if r_mult not in (None, "") else ""))
    if reason:
        lines.append(f"\n📋 {str(reason)[:300]}")
    text = "\n".join(lines)
    img = _trade_chart_image(direction, exit_price, None, [], subtitle=f"Closed {pnl:+.2f} USD")
    if img and _telegram_send_photo(img, text).get("ok"):
        return
    _telegram_send_text(text)


def _notify_trade_event(kind: str, result: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or result.get("request") or {}
    symbol = payload.get("symbol") or "XAUUSD"
    side = payload.get("side") or payload.get("direction") or "TRADE"
    volume = payload.get("volume") or payload.get("lots") or ""
    live = bool(result.get("ok")) and not bool(result.get("dryRun"))
    title = "Live trade sent" if live else "Trade request checked"
    message = result.get("message") or f"{side} {symbol} {volume}"
    safe_result = {"ok": bool(result.get("ok")), "dryRun": bool(result.get("dryRun")), "message": message, "retcode": (result.get("result") or {}).get("retcode") if isinstance(result.get("result"), dict) else None}
    safe_payload = {"symbol": symbol, "side": side, "volume": volume, "comment": payload.get("comment"), "magic": payload.get("magic")}
    notification = _push_notification(title, message, "success" if result.get("ok") else "danger", {"kind": kind, "result": safe_result, "payload": safe_payload})
    telegram = None
    side_u = str(side).upper()
    # Only send a Telegram trade alert for a REAL directional fill — never spam a
    # meaningless "WAIT" message. Entry alerts now carry entry/SL/TP/reason + chart.
    if live and SETTINGS_STATE.get("telegram", {}).get("enabled") and side_u in {"BUY", "SELL"}:
        dec = _decision()
        plan = dec.get("tradePlan", {}) if isinstance(dec.get("tradePlan"), dict) else {}
        strat = (dec.get("selectedStrategy", {}) or {}).get("name") or "GodMode Bot"
        entry = payload.get("price") or plan.get("entry")
        sl = payload.get("sl") or plan.get("sl")
        tps = [plan.get("tp1"), plan.get("tp2"), plan.get("tp3"), plan.get("tp4")]
        if not any(tps):
            tps = [payload.get("tp")]
        _telegram_rich_trade_alert("Trade fired", side_u, symbol, volume, entry, sl, tps, dec.get("confidence"), strat, dec.get("reason"), "success")
        telegram = {"ok": True, "rich": True}
    return {"notification": notification, "telegram": telegram}


def _auto_connect_mt5_on_startup() -> dict[str, Any]:
    """Attempt to attach to a running/logged-in MT5 terminal when the backend starts.

    This is intentionally safe: it does not enable live trading by itself. It only
    initializes the MetaTrader5 Python bridge so the UI can read real account/tick
    data immediately when MT5 is already open.
    """
    mt5_cfg = SETTINGS_STATE.get("mt5Connection", {}) if isinstance(SETTINGS_STATE.get("mt5Connection"), dict) else {}
    if mt5_cfg.get("autoConnect", True) is False:
        return {"ok": False, "detail": "Auto-connect disabled in settings."}
    trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    payload = {
        **mt5_cfg,
        "symbol": trading.get("symbol", mt5_bridge.symbol),
        "magicNumber": trading.get("magicNumber", mt5_bridge.magic),
        "commentPrefix": trading.get("commentPrefix", mt5_bridge.comment_prefix),
    }
    result = mt5_bridge.connect(payload)
    SETTINGS_STATE["mt5"] = result.get("status", mt5_bridge.status())
    return result


@app.on_event("startup")
async def startup_mt5_autoconnect() -> None:
    _apply_runtime_settings()
    try:
        _auto_connect_mt5_on_startup()
        _save_settings()
    except Exception as exc:
        SETTINGS_STATE["mt5"] = {"connected": False, "detail": f"Startup MT5 auto-connect failed: {exc}"}


async def _auto_trading_loop() -> None:
    # Local guarded auto-trading loop. It never enables live trading by itself.
    while True:
        try:
            execution = SETTINGS_STATE.get("execution", {}) if isinstance(SETTINGS_STATE.get("execution"), dict) else {}
            live_on = execution.get("liveTradingEnabled") and not execution.get("dryRun", True)
            # Auto ENTRY only when auto-trading is on
            if execution.get("autoTradingEnabled") and live_on:
                result = _auto_trade_tick(reason="background_loop")
                AUTO_TRADE_STATE["lastResult"] = result
            # Auto PROTECTION runs whenever live trading is on, regardless of auto-entry,
            # so manual or pyramided trades are always protected.
            if live_on and mt5_bridge.status().get("connected"):
                _auto_manage_open_trades()
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            AUTO_TRADE_STATE["lastResult"] = {"ok": False, "message": f"Auto loop error: {exc}"}
            await asyncio.sleep(3)


# Per-ticket protection state so we only act/alert once per transition.
POSITION_PROTECTION_STATE: dict[str, dict[str, Any]] = {}
PROTECTION_STATE_FILE = DATA_DIR / "protection_state.json"


def _save_protection_state() -> None:
    """Persist the per-trade protection state + safety counters so a restart resumes mid-trade
    (keeps the locked peak/floor, partials already taken, break-even flag) instead of re-arming
    from scratch or re-taking partials. Best-effort; throttled by the caller."""
    try:
        payload = {"positions": POSITION_PROTECTION_STATE,
                   "safety": {k: AUTO_TRADE_STATE.get(k) for k in
                              ("equityHwm", "dayKey", "dailyRealizedPnl", "pausedUntil",
                               "postLossUntil", "lossStreak", "winStreak")}}
        PROTECTION_STATE_FILE.write_text(json.dumps(payload, default=str), encoding="utf-8")
    except Exception:
        pass


def _load_protection_state() -> None:
    try:
        if PROTECTION_STATE_FILE.exists():
            data = json.loads(PROTECTION_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data.get("positions"), dict):
                POSITION_PROTECTION_STATE.update(data["positions"])
            saf = data.get("safety") or {}
            for k, v in saf.items():
                if v is not None:
                    AUTO_TRADE_STATE[k] = v
    except Exception:
        pass


def _capital_circuit_breaker(blocked) -> dict[str, Any] | None:
    """Daily-loss + equity-drawdown circuit breakers. Returns a blocked() result if a breaker
    has tripped (so the gate stops the entry), else None. Gated by risk.useEquityProtection."""
    risk_cfg = SETTINGS_STATE.get("risk", {}) if isinstance(SETTINGS_STATE.get("risk"), dict) else {}
    if not risk_cfg.get("useEquityProtection", True):
        return None
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if AUTO_TRADE_STATE.get("dayKey") != day:        # new UTC day → reset the daily tally
        AUTO_TRADE_STATE["dayKey"] = day
        AUTO_TRADE_STATE["dailyRealizedPnl"] = 0.0
        AUTO_TRADE_STATE["dailyHaltAlerted"] = False
    equity = float(_live_account().get("equity") or 0)
    if equity <= 0:
        return None
    # 1) Daily realized-loss limit
    daily_pnl = float(AUTO_TRADE_STATE.get("dailyRealizedPnl", 0.0))
    max_daily_loss_pct = float(risk_cfg.get("maxDailyLossPct", 5.0) or 5.0)
    if daily_pnl < 0 and abs(daily_pnl) >= equity * max_daily_loss_pct / 100.0:
        if not AUTO_TRADE_STATE.get("dailyHaltAlerted"):
            AUTO_TRADE_STATE["dailyHaltAlerted"] = True
            _management_alert("Daily loss limit hit", f"Realized {daily_pnl:.2f} today ≥ {max_daily_loss_pct:.1f}% of equity ({equity:.2f}). Auto-entry halted until the next UTC day.", "danger")
        return blocked(f"Daily loss limit reached ({daily_pnl:.2f} ≥ {max_daily_loss_pct:.1f}% of equity). Auto-entry halts until next UTC day.", {"dailyPnl": daily_pnl, "breaker": "daily_loss"})
    # 2) Equity drawdown stop (high-water mark) → engage the kill switch
    hwm = float(AUTO_TRADE_STATE.get("equityHwm", 0.0) or 0.0)
    if equity > hwm:
        AUTO_TRADE_STATE["equityHwm"] = hwm = equity
    eq_stop_pct = float(risk_cfg.get("equityStopLossPct", 20.0) or 20.0)
    if hwm > 0 and equity <= hwm * (1.0 - eq_stop_pct / 100.0):
        kill_switch.activate(f"Equity protection: drawdown ≥ {eq_stop_pct:.0f}% from peak {hwm:.2f} (now {equity:.2f}).")
        _management_alert("Equity stop — kill switch engaged", f"Equity {equity:.2f} fell ≥ {eq_stop_pct:.0f}% below the peak {hwm:.2f}. Trading halted; review before resetting the kill switch.", "danger")
        return blocked("Equity drawdown stop hit — kill switch engaged.", {"equity": equity, "peak": hwm, "breaker": "equity_stop"})
    return None


_load_protection_state()   # crash recovery: resume mid-trade protection + safety counters on startup


def _management_alert(title: str, body: str, kind: str = "success") -> None:
    """Push a UI notification AND send Telegram for a trade-management event."""
    _push_notification(title, body, kind)
    try:
        _journal_record("management", title=title, detail=str(body)[:240], kind=kind)
    except Exception:
        pass
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if tg.get("enabled"):
        emoji = {"success": "🟢", "warning": "🟡", "danger": "🔴", "info": "🔵"}.get(kind, "🔔")
        _telegram_send_text(f"{emoji} *GodMode — {title}*\n{body}")


def _auto_manage_open_trades() -> None:
    """Automatically protect every open bot trade: break-even, structure trailing,
    fast-fail close, and pyramid-add cut. Fires UI + Telegram alerts on each action."""
    try:
        tm_cfg = (SETTINGS_STATE.get("trading") or {}).get("tradeManagement") or {}
        auto_be = tm_cfg.get("autoBreakEven", True)
        auto_trail = tm_cfg.get("autoTrailing", True)
        be_at_rr = float(tm_cfg.get("breakEvenAtRR", 0.8))
        trail_start_rr = float(tm_cfg.get("trailStartRR", 1.0))
        trail_atr_mult = float(tm_cfg.get("trailAtrMult", 1.2))
        fast_fail_on = tm_cfg.get("fastFailEnabled", True)
        fast_fail_r = float(tm_cfg.get("fastFailLossR", -0.5))
        fast_fail_candles = int(tm_cfg.get("fastFailNoProgressCandles", 3))
        open_trades = mt5_bridge.open_positions(bot_only=True)
        live_tickets = {str(p.get("ticket")) for p in open_trades if p.get("ticket")}
        # A tracked ticket that vanished was closed at the broker (SL/TP hit).
        # Fetch its closing deal and cache it so it shows in history INSTANTLY.
        for gone in [t for t in POSITION_PROTECTION_STATE if t not in live_tickets]:
            try:
                closed = mt5_bridge.closed_bot_trades(days=2)
                match = next((c for c in closed if str(c.get("positionId")) == gone or str(c.get("ticket")) == gone), None)
                already = any(str(x.get("ticket")) == gone or str(x.get("positionId")) == gone for x in RECENT_CLOSED_TRADE_CACHE)
                if match and not already:
                    _cache_close_event_with_ts(
                        {"ticket": match.get("ticket"), "symbol": match.get("symbol"), "direction": match.get("direction"),
                         "volume": match.get("lots"), "entryPrice": match.get("entryPrice"),
                         "exitPrice": match.get("exitPrice"), "pnlUsd": match.get("pnlUsd")},
                        {"ok": True, "message": "Closed at broker (SL/TP)"})
                    pnl = float(match.get("pnlUsd", 0) or 0)
                    em = _enrich_closed_trade(match)
                    _push_notification("Trade closed", f"{match.get('direction')} {match.get('symbol')} #{gone} closed. PnL {pnl:+.2f} USD.", "success" if pnl >= 0 else "warning")
                    _telegram_rich_close_alert(match.get("direction"), match.get("symbol"), gone, match.get("exitPrice"), pnl, em.get("rMultiple"), em.get("reason") or match.get("exitReason") or "Closed at broker", "success" if pnl >= 0 else "warning")
                    _register_close_outcome(match.get("ticket") or gone, pnl, match.get("direction"), match.get("exitPrice"), None)
                    _maybe_learn(match)  # feed the AI learning loop + run post-trade review
            except Exception:
                pass
            POSITION_PROTECTION_STATE.pop(gone, None)
        # Reconcile any RECENT close the loop never tracked (e.g. a scalp that opened and
        # closed between two polls) so it appears in history instantly and is learned/counted.
        try:
            for c in mt5_bridge.closed_bot_trades(days=1):
                tkc = str(c.get("ticket"))
                if not tkc or tkc == "None":
                    continue
                if float(c.get("closeTimestamp", 0) or 0) < time.time() - 900:
                    continue  # only the last ~15 minutes
                if any(str(x.get("ticket")) == tkc for x in RECENT_CLOSED_TRADE_CACHE):
                    continue
                _cache_close_event_with_ts(
                    {"ticket": c.get("ticket"), "symbol": c.get("symbol"), "direction": c.get("direction"),
                     "volume": c.get("lots"), "entryPrice": c.get("entryPrice"), "exitPrice": c.get("exitPrice"),
                     "pnlUsd": c.get("pnlUsd")}, {"ok": True, "message": c.get("exitReason", "Closed")})
                _register_close_outcome(c.get("ticket"), c.get("pnlUsd"), c.get("direction"), c.get("exitPrice"), None)
                _maybe_learn(c)
        except Exception:
            pass
        market = _live_market()
        current_price = float(market.get("price") or 0)
        atr = float(market.get("atr14") or 8) or 8
        if not current_price:
            return
        symbol = market.get("symbol", "XAUUSD")
        control_lines: list[str] = []  # HOLD/CUT directives for the tick-level EA
        for pos in open_trades:
            ticket = pos.get("ticket")
            if not ticket:
                continue
            tkey = str(ticket)
            st = POSITION_PROTECTION_STATE.setdefault(tkey, {"beMoved": False, "trailLevel": 0.0, "alertedOpen": False})
            entry = float(pos.get("entryPrice") or 0)
            sl = float(pos.get("sl") or 0)
            direction = str(pos.get("direction") or "").upper()
            lots = pos.get("lots") or pos.get("volume") or 0.01
            if not entry:
                continue
            # Stable risk basis: distance entry->ORIGINAL SL, captured once so R stays
            # correct even after the stop is moved to break-even (was a real bug).
            init_risk = abs(entry - sl) if sl else atr
            if not init_risk:
                init_risk = atr
            rb = float(st.setdefault("riskBasis", init_risk)) or atr
            profit_r = (current_price - entry) / rb if direction == "BUY" else (entry - current_price) / rb
            # TP1-TP4 levels from the risk basis (matches the engine's 1.0/1.8/2.7/4.0 R plan)
            tp_mult = (1.0, 1.8, 2.7, 4.0)
            tps = [round(entry + (m if direction == "BUY" else -m) * rb, 2) for m in tp_mult]
            ctx_store = trade_context.get(ticket, pos.get("positionId")) or {}

            # Announce the open ONCE, with full entry/SL/TP1-4 + reason + chart.
            if not st["alertedOpen"]:
                st["alertedOpen"] = True
                st["origLot"] = float(lots)
                _push_notification("Trade open", f"{direction} {symbol} {lots} @ {entry:.2f} · SL {sl:.2f}", "info")
                _telegram_rich_trade_alert(
                    "Trade open", direction, symbol, lots, entry, sl, tps,
                    ctx_store.get("confidence"),
                    ctx_store.get("strategy") or strategy_from_comment(str(pos.get("comment", ""))) or "GodMode Bot",
                    ctx_store.get("reason") or _decision().get("reason"), "info")

            # Track best-R reached to detect give-backs / stalls
            st["peakR"] = max(float(st.get("peakR", 0.0)), profit_r)
            st["candlesSeen"] = int(st.get("candlesSeen", 0)) + 1

            # Build management context for the rich decision helper
            ctx = {**pos, "profitR": round(profit_r, 3), "floatingR": round(profit_r, 3),
                   "dirtyConditions": bool(market.get("newsBlackout") or market.get("dirtyConditions")),
                   "spreadSpike": float(market.get("spread") or 0) > 0.45,
                   "beMoved": st["beMoved"]}
            decision = trade_manager.live_management_decision(ctx)
            action = decision.get("action")

            # ── AI RECOVERY MONITOR — gates the fast-fail ──────────────────────
            # Instead of a blunt candle counter, the AI assesses (every cycle) whether
            # an underwater trade is likely to RECOVER or is genuinely invalidated.
            #   RECOVER  → hold; optionally give structural room (dynamic SL, risk-capped)
            #   CUT      → close now, even before the candle counter
            #   NEUTRAL  → fall back to the classic fast-fail rule
            auto_cfg = SETTINGS_STATE.get("automation", {}) if isinstance(SETTINGS_STATE.get("automation"), dict) else {}
            recovery_on = auto_cfg.get("recoveryMonitorEnabled", True)
            dyn_sl_on = auto_cfg.get("dynamicSlEnabled", False)
            recovery = {"verdict": "NEUTRAL", "recoveryScore": 50.0, "invalidated": False, "reasons": []}
            if recovery_on:
                try:
                    recovery = assess_recovery({**pos, "currentPrice": current_price}, _cached_decision(), atr,
                                               float(auto_cfg.get("recoveryHoldThreshold", 62)),
                                               float(auto_cfg.get("recoveryCutThreshold", 38)))
                except Exception:
                    recovery = {"verdict": "NEUTRAL", "recoveryScore": 50.0, "invalidated": False, "reasons": []}
            st["recoveryScore"] = recovery["recoveryScore"]
            # Hand the verdict to the tick-level EA: HOLD protects a recovering trade
            # from the EA's hard floor; CUT closes it next tick.
            if recovery_on and profit_r < 0 and recovery["verdict"] in ("RECOVER", "CUT"):
                control_lines.append(f"{ticket},{'HOLD' if recovery['verdict']=='RECOVER' else 'CUT'}")

            fast_fail_hit = False
            fail_reason = ""
            if fast_fail_on and profit_r < 0:
                hard_floor_hit = profit_r <= fast_fail_r
                invalidated = bool(recovery.get("invalidated"))
                if recovery_on and (recovery["verdict"] == "CUT" or invalidated):
                    # AI says it cannot recover (or structure invalidated) → cut now.
                    fast_fail_hit = True
                    fail_reason = f"AI: cannot recover (score {recovery['recoveryScore']:.0f}/100). " + "; ".join(recovery["reasons"][:2])
                elif st.get("slWidened"):
                    # Already committed to a risk-capped widened SL — let the broker SL
                    # protect it; don't fast-fail a trade we deliberately gave room.
                    pass
                elif recovery_on and recovery["verdict"] == "RECOVER" and dyn_sl_on and not hard_floor_hit:
                    # AI expects recovery AND dynamic SL is enabled → widen the stop ONCE to
                    # the structural invalidation, HARD-CAPPED by max risk %. From then on the
                    # (capped) broker SL is the protection.
                    try:
                        max_risk_pct = float(auto_cfg.get("dynamicSlMaxRiskPct", 1.0))
                        equity = float(_live_account().get("equity") or 0)
                        max_dist = (equity * max_risk_pct / 100.0) / max(float(lots) * 100.0, 1e-6) if equity else atr * 2.5
                        new_wide = compute_widened_sl({**pos, "currentPrice": current_price}, _cached_decision(), atr, max_dist)
                        if new_wide and abs(new_wide - sl) > 0.01:
                            if mt5_bridge.modify_position({"ticket": ticket, "sl": new_wide}).get("ok"):
                                st["slWidened"] = True
                                _management_alert("AI widened SL", f"{direction} {symbol} #{ticket}: SL → {new_wide:.2f}. Recovery {recovery['recoveryScore']:.0f}/100, capped at {max_risk_pct:.2f}% risk.", "info")
                    except Exception:
                        pass
                elif hard_floor_hit:
                    # HARD floor ALWAYS cuts here — RECOVER cannot hold past it without a
                    # capped widened SL. This is the fix for losers bleeding past -0.5R.
                    note = " (AI wanted to hold but dynamic SL is OFF — floor enforced)" if recovery.get("verdict") == "RECOVER" else ""
                    fast_fail_hit = True
                    fail_reason = f"reached {profit_r:.2f}R (fast-fail floor {fast_fail_r:.2f}R){note}"
                elif st["candlesSeen"] >= fast_fail_candles and st["peakR"] < 0.2:
                    fast_fail_hit = True
                    fail_reason = f"no progress in {st['candlesSeen']} checks (AI recovery {recovery['recoveryScore']:.0f}/100)"

            # FAST-FAIL / dirty / cut pyramid → close the position immediately to protect capital
            if fast_fail_hit or action in {"FAST_FAIL_CLOSE", "STOP_TRADING_DIRTY_CONDITIONS", "CUT_NEWEST_PYRAMID_ADD"}:
                close_res = mt5_bridge.close_position({"ticket": ticket, "symbol": symbol, "volume": lots})
                if close_res.get("ok"):
                    pnl_est = round((current_price - entry) * (100 if direction == "BUY" else -100) * float(lots) / 0.01 * 0.01, 2)
                    why = fail_reason or decision.get("reason", action)
                    _cache_close_event_with_ts(
                        {"ticket": ticket, "symbol": symbol, "direction": direction, "volume": lots,
                         "entryPrice": entry, "exitPrice": current_price, "pnlUsd": pnl_est},
                        {"ok": True, "message": why})
                    _register_close_outcome(ticket, pnl_est, direction, current_price, market.get("session"))
                    _push_notification("Fast-fail close" if fast_fail_hit else "Protective close", f"{direction} {symbol} #{ticket} closed @ {current_price:.2f}. {why}", "warning")
                    _telegram_rich_close_alert(direction, symbol, ticket, current_price, pnl_est, round(profit_r, 2), why, "warning")
                continue

            # ── SMART PROFIT PROTECTION: ratcheting floor + tight trail + recovery room ──
            # Locks a growing fraction of the BEST profit reached (a winner can never fall
            # back to a loss/scratch), trails tightly to ride trends, and — when price is
            # about to be stopped but the AI sees a high-probability recovery — relaxes to
            # the protected floor to let a shakeout breathe and win bigger.
            new_sl = sl
            give_room = False
            prof_dist = (current_price - entry) if direction == "BUY" else (entry - current_price)
            profit_atr = prof_dist / atr if atr else 0.0
            protect_start_atr = float(tm_cfg.get("protectStartAtr", 0.4))
            lock_frac = float(tm_cfg.get("profitLockFraction", 0.35))
            trail_start_atr = float(tm_cfg.get("trailStartAtr", 0.7))
            room_on = tm_cfg.get("smartRecoveryRoom", True)
            room_trigger_atr = float(tm_cfg.get("recoveryRoomAtr", 0.3))
            if auto_be and prof_dist > 0 and (profit_atr >= protect_start_atr or profit_r >= be_at_rr):
                # Peak-ratcheting locked floor — never decreases, always in profit.
                st["peakDist"] = max(float(st.get("peakDist", 0.0)), prof_dist)
                floor_dist = lock_frac * st["peakDist"]
                floor_sl = round(entry + (floor_dist if direction == "BUY" else -floor_dist), 2)
                # Tight dynamic trail (tightens as the move extends).
                if auto_trail and (profit_atr >= trail_start_atr or profit_r >= trail_start_rr):
                    dyn_mult = max(0.5, trail_atr_mult - max(0.0, profit_atr - 1.0) * 0.1)
                    trail_raw = (current_price - dyn_mult * atr) if direction == "BUY" else (current_price + dyn_mult * atr)
                    tight_sl = round(max(floor_sl, trail_raw) if direction == "BUY" else min(floor_sl, trail_raw), 2)
                else:
                    tight_sl = floor_sl
                # Trail ratchets the in-market stop toward profit only (never down on its own).
                if (direction == "BUY" and (not sl or tight_sl > sl + 0.01)) or \
                   (direction == "SELL" and (not sl or tight_sl < sl - 0.01)):
                    target_sl = tight_sl
                else:
                    target_sl = sl or tight_sl
                # SMART RECOVERY ROOM — price about to hit the EXISTING in-market stop (already
                # trailed up above the floor) + high recovery probability → loosen the stop DOWN to
                # the protected in-profit floor so a shakeout can breathe and the trade win bigger.
                room_above_floor = bool(sl) and ((direction == "BUY" and sl > floor_sl + 0.01) or (direction == "SELL" and sl < floor_sl - 0.01))
                if room_on and room_above_floor:
                    dist_to_stop = (current_price - sl) if direction == "BUY" else (sl - current_price)
                    if 0 <= dist_to_stop <= room_trigger_atr * atr:
                        try:
                            rec = assess_recovery({**pos, "currentPrice": current_price}, _cached_decision(), atr,
                                                  float(auto_cfg.get("recoveryHoldThreshold", 62)),
                                                  float(auto_cfg.get("recoveryCutThreshold", 38)))
                        except Exception:
                            rec = {"verdict": "NEUTRAL", "invalidated": False, "recoveryScore": 50.0}
                        st["recoveryScore"] = rec["recoveryScore"]
                        if rec["verdict"] == "RECOVER" and not rec["invalidated"]:
                            target_sl = floor_sl   # give room down to the protected (in-profit) floor
                            give_room = True
                # SL can never sit below the ratcheting floor → a winner stays a winner.
                target_sl = max(target_sl, floor_sl) if direction == "BUY" else min(target_sl, floor_sl)
                if give_room:
                    if abs(target_sl - sl) > 0.01:
                        new_sl = target_sl   # deliberate, bounded loosening to the floor
                elif (direction == "BUY" and (not sl or target_sl > sl + 0.01)) or (direction == "SELL" and (not sl or target_sl < sl - 0.01)):
                    new_sl = target_sl

            if new_sl and abs(new_sl - sl) > 0.01:
                mod = mt5_bridge.modify_position({"ticket": ticket, "sl": new_sl})
                if mod.get("ok"):
                    locked_r = (((new_sl - entry) if direction == "BUY" else (entry - new_sl)) / rb) if rb else 0.0
                    if give_room:
                        _management_alert("Recovery room", f"{direction} {symbol} #{ticket}: gave room to {new_sl:.2f} (+{locked_r:.2f}R still locked) — high recovery, letting the pullback breathe.", "info")
                    elif not st.get("beMoved"):
                        st["beMoved"] = True
                        st["lastAlertR"] = locked_r
                        _management_alert("Profit locked", f"{direction} {symbol} #{ticket}: SL → {new_sl:.2f}, locking +{locked_r:.2f}R (+{profit_atr:.1f} ATR).", "success")
                    elif locked_r - float(st.get("lastAlertR", 0.0)) >= 0.5:  # throttle trail alerts
                        st["lastAlertR"] = locked_r
                        st["trailLevel"] = new_sl
                        _management_alert("Trailing up", f"{direction} {symbol} #{ticket}: SL → {new_sl:.2f} (+{locked_r:.2f}R locked, +{profit_r:.1f}R open).", "success")

            # ── TP1-TP4 partial profit-taking (real partial closes when lot allows) ──
            if tm_cfg.get("partialTakeProfit", True) and float(lots) > 0:
                specs = mt5_bridge.symbol_specs(symbol)
                minlot = float(specs.get("volumeMin", 0.01) or 0.01)
                orig_lot = float(st.get("origLot", lots))
                taken = int(st.get("partialsTaken", 0))
                hit = 0
                for idx, tp in enumerate(tps):
                    if (direction == "BUY" and current_price >= tp) or (direction == "SELL" and current_price <= tp):
                        hit = idx + 1
                if hit > taken:
                    can_slice = orig_lot >= round(4 * minlot, 2) - 1e-9 and float(lots) - round(orig_lot * 0.25, 2) >= minlot - 1e-9 and hit < 4
                    if can_slice:
                        close_vol = max(minlot, round(orig_lot * 0.25, 2))
                        pc = mt5_bridge.close_position({"ticket": ticket, "symbol": symbol, "volume": close_vol})
                        if pc.get("ok"):
                            st["partialsTaken"] = hit
                            _management_alert(f"TP{hit} hit", f"{direction} {symbol} #{ticket}: TP{hit} @ {tps[hit-1]:.2f} — closed {close_vol} lots (+{profit_r:.1f}R). Runner trailing.", "success")
                    elif not st.get(f"tpNote{hit}"):
                        # lot too small to slice (e.g. 0.01) — note it; BE/trailing manage the single position
                        st["partialsTaken"] = hit
                        st[f"tpNote{hit}"] = True
                        _management_alert(f"TP{hit} reached", f"{direction} {symbol} #{ticket}: TP{hit} @ {tps[hit-1]:.2f} (+{profit_r:.1f}R). Lot too small to partial — SL at break-even, trailing the runner.", "success")

            # ── TP PUSH: actually extend the broker TP so a clean runner reaches TP3/TP4 ──
            pos_tp = float(pos.get("tp") or 0)
            if tm_cfg.get("tpPushEnabled", True) and pos_tp > 0 and profit_r >= 1.3 and not st.get("tpPushed"):
                far_tp = tps[3]
                strong = float(st.get("recoveryScore", 60)) >= 55 or profit_r >= 1.8
                if strong and ((direction == "BUY" and pos_tp < far_tp - 0.01) or (direction == "SELL" and pos_tp > far_tp + 0.01)):
                    if mt5_bridge.modify_position({"ticket": ticket, "tp": round(far_tp, 2)}).get("ok"):
                        st["tpPushed"] = True
                        _management_alert("TP pushed", f"{direction} {symbol} #{ticket}: TP extended to {far_tp:.2f} (TP4) — clean runner at +{profit_r:.1f}R.", "success")
        # Publish AI directives for the tick-level EA (writes only if a path is set;
        # empty file when no open trades clears any stale directives).
        _write_mql5_control(control_lines)
        # Persist protection + safety state (throttled) for crash recovery.
        if time.time() - float(RECAP_STATE.get("lastProtSave", 0.0)) > 20:
            RECAP_STATE["lastProtSave"] = time.time()
            _save_protection_state()
    except Exception as exc:
        _push_notification("Protection loop error", str(exc), "danger")

RECAP_STATE: dict[str, Any] = {"lastDaily": "", "lastWeekly": "", "lastWaitForecast": 0.0}


def _send_recap(weekly: bool = False) -> None:
    """Send a daily/weekly Telegram recap with KPIs + an equity-curve image."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return
    a = _live_analytics()
    k = a.get("kpis", {})
    cur = a.get("currency", "")
    title = "Weekly Recap" if weekly else "Daily Recap"
    caption = (f"📊 *GodMode {title}*\n"
               f"Net PnL: *{k.get('netProfit', 0)} {cur}*  ({k.get('returnPct', 0)}%)\n"
               f"Win rate: *{k.get('winRate', 0)}%*  ·  PF: *{k.get('profitFactor', 0)}*\n"
               f"Trades: *{k.get('totalTrades', 0)}*  ·  Max DD: *{k.get('maxDrawdown', 0)}%*\n"
               f"Expectancy: *{k.get('expectancy', 0)} {cur}*/trade")
    kpis = {"Net": k.get("netProfit", 0), "Win%": k.get("winRate", 0), "PF": k.get("profitFactor", 0), "Trades": k.get("totalTrades", 0)}
    img = chart_render.render_equity_recap(a.get("equityCurve", []), title=f"GodMode {title}", kpis=kpis) if chart_render.available() else None
    if img and _telegram_send_photo(img, caption).get("ok"):
        return
    _telegram_send_text(caption)


def _send_wait_forecast() -> None:
    """Throttled forecast while WAITING: projected entry/SL/TP + why + chart, so the
    'WAIT' alert is actionable instead of a bare 'WAIT symbol lot'."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled") or not tg.get("sendWaitForecast"):
        return
    if not _market_state().get("open", True):
        return  # market closed — never send WAIT / forecast signals while closed
    now = time.time()
    if now - float(RECAP_STATE.get("lastWaitForecast", 0)) < float(tg.get("waitForecastMinutes", 30)) * 60:
        return
    if mt5_bridge.open_positions(bot_only=True):
        return  # a trade is open — not waiting
    dec = _decision()
    if str(dec.get("action")) == "TAKE_TRADE":
        return
    plan = dec.get("tradePlan", {}) if isinstance(dec.get("tradePlan"), dict) else {}
    bias = str(dec.get("computedSide") or dec.get("side") or "WAIT").upper()
    regime = dec.get("marketRegime") or "—"
    blocks = dec.get("decisionBlocks") or []
    # Make it unmistakable that this is a PREVIEW of a setup the bot is watching — NOT a trade signal,
    # and NOT a missed trade. Confidence here is signal quality; the blocks below are why it's held.
    why = "; ".join(str(b) for b in blocks[:2]) if blocks else (dec.get("reason") or "no clean setup yet")
    reason = (f"🚫 NOT TRADING — preview only. The bot has a {bias} *bias* here but is standing aside "
              f"({regime}). Blocked by: {why}")
    strat = f"Standing aside · {regime}"
    RECAP_STATE["lastWaitForecast"] = now
    base_lot = (SETTINGS_STATE.get("pyramiding", {}) or {}).get("baseLot", 0.01)
    _telegram_rich_trade_alert("Forecast — BLOCKED (preview only, not a trade)", bias if bias in {"BUY", "SELL"} else "WAIT",
                               dec.get("symbol", "XAUUSD"), base_lot, plan.get("entry"), plan.get("sl"),
                               [plan.get("tp1"), plan.get("tp2"), plan.get("tp3"), plan.get("tp4")],
                               dec.get("confidence"), strat, reason, "info",
                               confidence_label="Signal quality (not a trade signal)")


def _send_market_closed_update(reason: str) -> None:
    """Telegram 'Market Closed' update that carries the DAILY TRADE SUMMARY (KPIs + equity image).
    Sent once when the market transitions to closed (e.g. the Friday weekend close)."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return
    a = _live_analytics(); k = a.get("kpis", {}); cur = a.get("currency", "")
    caption = (f"🔴 *GodMode — Market Closed*\n{reason}\n\n"
               f"📊 *Daily Trade Summary*\n"
               f"Net PnL: *{k.get('netProfit', 0)} {cur}*  ({k.get('returnPct', 0)}%)\n"
               f"Win rate: *{k.get('winRate', 0)}%*  ·  PF: *{k.get('profitFactor', 0)}*\n"
               f"Trades: *{k.get('totalTrades', 0)}*  ·  Max DD: *{k.get('maxDrawdown', 0)}%*\n"
               f"Expectancy: *{k.get('expectancy', 0)} {cur}*/trade\n\n"
               f"_No WAIT/forecast signals will be sent until the market reopens._")
    kpis = {"Net": k.get("netProfit", 0), "Win%": k.get("winRate", 0), "PF": k.get("profitFactor", 0), "Trades": k.get("totalTrades", 0)}
    img = chart_render.render_equity_recap(a.get("equityCurve", []), title="GodMode — Market Closed (Daily Summary)", kpis=kpis) if chart_render.available() else None
    if img and _telegram_send_photo(img, caption).get("ok"):
        return
    _telegram_send_text(caption)


def _send_market_open_update(reason: str = "") -> None:
    """Telegram 'Market Open' update when the market reopens."""
    tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
    if not tg.get("enabled"):
        return
    _telegram_send_text("🟢 *GodMode — Market Open*\nXAUUSD is trading again. The bot is live and scanning for valid setups.")


def _check_market_transition() -> None:
    """Detect open↔closed transitions and fire the matching Telegram update. The closed update
    includes the daily trade summary; while closed, WAIT/forecast signals are suppressed."""
    mkt = _market_state()
    is_open = bool(mkt.get("open", True))
    prev = RECAP_STATE.get("marketOpen")
    if prev is None:
        RECAP_STATE["marketOpen"] = is_open   # initialise silently — never alert on startup
        return
    if is_open == prev:
        return
    RECAP_STATE["marketOpen"] = is_open
    if is_open:
        _send_market_open_update(mkt.get("reason", ""))
    else:
        _send_market_closed_update(mkt.get("reason", "Market closed for the day"))


async def _recap_loop() -> None:
    while True:
        try:
            tm = time.gmtime()
            today = time.strftime("%Y-%m-%d", tm)
            tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
            _check_market_transition()   # market open/closed Telegram updates (any time, throttled by state)
            if tg.get("enabled"):
                week = time.strftime("%Y-W%U", tm)
                hour = int(tg.get("recapHourUtc", 21))
                if tm.tm_hour == hour and tg.get("dailyRecap", True) and RECAP_STATE.get("lastDaily") != today:
                    _send_recap(False); RECAP_STATE["lastDaily"] = today
                if tm.tm_wday == 6 and tm.tm_hour == hour and tg.get("weeklyRecap", True) and RECAP_STATE.get("lastWeekly") != week:
                    _send_recap(True); RECAP_STATE["lastWeekly"] = week
                _send_wait_forecast()
            # Daily AI Strategy Lab auto-run (independent of Telegram). Runs once/day at the set UTC
            # hour when connected, in a thread so the heavy backtest never blocks the event loop.
            lab_cfg = SETTINGS_STATE.get("strategyLab", {}) if isinstance(SETTINGS_STATE.get("strategyLab"), dict) else {}
            if lab_cfg.get("autoRunDaily") and mt5_bridge.status().get("connected") \
                    and tm.tm_hour == int(lab_cfg.get("autoRunHourUtc", 22)) and RECAP_STATE.get("lastLabRun") != today:
                RECAP_STATE["lastLabRun"] = today
                res = await asyncio.get_event_loop().run_in_executor(None, _run_strategy_lab, 60000)
                _alert_lab_recommendation(res)
            # Auto-pilot: discover & install a fitting strategy when nothing else fits (opt-in, guarded).
            if lab_cfg.get("autoDiscover"):
                await asyncio.get_event_loop().run_in_executor(None, _auto_discover_strategy)
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(60)


@app.on_event("startup")
async def startup_auto_trader() -> None:
    asyncio.create_task(_auto_trading_loop())
    asyncio.create_task(_recap_loop())
    asyncio.create_task(_telegram_command_loop())   # listen for Telegram Uninstall/Keep button taps


def _apply_runtime_settings() -> None:
    trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    execution = SETTINGS_STATE.get("execution", {}) if isinstance(SETTINGS_STATE.get("execution"), dict) else {}
    mt5_cfg = SETTINGS_STATE.get("mt5Connection", {}) if isinstance(SETTINGS_STATE.get("mt5Connection"), dict) else {}
    payload = {
        "symbol": trading.get("symbol", mt5_bridge.symbol),
        "magicNumber": trading.get("magicNumber", mt5_bridge.magic),
        "commentPrefix": trading.get("commentPrefix", mt5_bridge.comment_prefix),
        "terminalPath": mt5_cfg.get("terminalPath", mt5_bridge.terminal_path),
        "login": mt5_cfg.get("login", mt5_bridge.login),
        "password": mt5_cfg.get("password", "") or mt5_bridge.password,
        "server": mt5_cfg.get("server", mt5_bridge.server),
        "dryRun": execution.get("dryRun", not mt5_bridge.live_enabled),
        "liveTradingEnabled": execution.get("liveTradingEnabled", mt5_bridge.live_enabled),
        "autoTradingEnabled": execution.get("autoTradingEnabled", mt5_bridge.auto_trading_enabled),
    }
    mt5_bridge.configure(payload)
    ai_cfg = SETTINGS_STATE.get("ai", {}) if isinstance(SETTINGS_STATE.get("ai"), dict) else {}
    decision_engine.configure_strictness(ai_cfg)

_apply_runtime_settings()
STRATEGIES_STATE = {s["id"]: dict(s) for s in INSTITUTIONAL_STRATEGIES}


def _profile_to_gate(prof: dict[str, Any]) -> dict[str, Any]:
    """Translate a Lab candidate's strictness profile into per-strategy ENTRY GATES, so an installed
    strategy judges its OWN entries by its OWN rules (efficiency / R-R / confidence) instead of
    rewriting the GLOBAL strictness. This is what makes an install additive rather than destructive."""
    gp: dict[str, Any] = {}
    if prof.get("minEfficiencyRatio") is not None:
        gp["minEfficiency"] = float(prof["minEfficiencyRatio"])
    if prof.get("minRiskReward") is not None:
        gp["minRiskReward"] = float(prof["minRiskReward"])
    allow_scout = bool(prof.get("allowScoutEntries", True))
    take = prof.get("scoutConfidence") if allow_scout else prof.get("standardConfidence")
    if take is None:
        take = prof.get("standardConfidence", prof.get("scoutConfidence"))
    if take is not None:
        gp["minTakeScore"] = float(take)
    return gp


def _register_installed_strategy(cand: dict[str, Any], evidence: dict[str, Any] | None = None) -> str:
    """Make a Strategy-Lab install VISIBLE in the Strategies page and active in the engine. Adds an
    entry to STRATEGIES_STATE (so it shows alongside your other strategies) carrying the installed
    tuning profile, and removes any prior Lab-installed entry so only one 'active tuning' exists."""
    for k in [k for k, v in STRATEGIES_STATE.items() if v.get("source") == "strategy_lab"]:
        STRATEGIES_STATE.pop(k, None)
    prof = cand.get("profile", {}) if isinstance(cand.get("profile"), dict) else {}
    sid = f"lab-{cand.get('id', 'installed')}"[:48]
    ev = evidence or {}
    try:
        wr = round(float(ev.get("winRate")), 1) if ev.get("winRate") not in (None, "") else 64.0
    except Exception:
        wr = 64.0
    STRATEGIES_STATE[sid] = {
        "id": sid, "name": cand.get("name", sid), "category": "ai-lab",
        "description": cand.get("thesis") or "Installed from the AI Strategy Lab — competes in the rotation with its own entry gates (it does NOT change your global strictness).",
        "bestSessions": prof.get("allowedSessions") or ["London", "New York"],
        "idealRegimes": prof.get("idealRegimes") or ["Strong Bullish Trend", "Strong Bearish Trend", "Volatility Expansion"],
        "requiredEvidence": ["passes this strategy's own entry gates"],
        "minConfidence": prof.get("standardConfidence", decision_engine.min_standard_score),
        "sniperConfidence": prof.get("sniperConfidence", decision_engine.min_sniper_score),
        "gateProfile": _profile_to_gate(prof),
        "enabled": True, "installed": True, "source": "strategy_lab",
        "candidateSource": cand.get("source", "library"), "profile": prof,
        "winRate": wr, "expectancy": (f"{ev.get('expectancyR')}R" if ev.get("expectancyR") is not None else "—"),
        "maxDrawdown": (f"{ev.get('maxDrawdownR')}R" if ev.get("maxDrawdownR") is not None else "—"),
    }
    return sid


def _restore_installed_strategy() -> None:
    rec = (SETTINGS_STATE.get("strategyLab", {}) or {}).get("installed")
    if isinstance(rec, dict) and rec.get("id"):
        try:
            _register_installed_strategy(rec, rec.get("evidence"))
        except Exception:
            pass


_restore_installed_strategy()   # re-show a previously installed Lab tuning on startup

# Persistent, structured risk limit overrides. Defaults match the mockup so the
# Risk Management Center always shows real, editable numbers that survive saves.
RISK_DEFAULTS: dict[str, Any] = {
    "maxDailyLossPct": 5.0,
    "maxDrawdownPct": 10.0,
    "maxRiskPerTradePct": 1.0,
    "maxOpenRiskPct": 2.0,
    "maxExposurePct": 35.0,
    "lossStreakLimit": 5,
    "newsFilterMinutes": 15,
    "circuitBreakerPct": 6.0,
    "maxSpreadXau": 0.40,
    "sessionCaps": {"London": 1.5, "New York": 2.0, "Asia": 1.0, "Overlap": 2.5},
    "rules": {},
}
RISK_STATE: dict[str, Any] = deepcopy(RISK_DEFAULTS)
RISK_FILE = DATA_DIR / "risk_overrides.json"
if RISK_FILE.exists():
    try:
        saved_risk = json.loads(RISK_FILE.read_text(encoding="utf-8"))
        if isinstance(saved_risk, dict):
            _deep_merge(RISK_STATE, saved_risk)
    except Exception:
        pass


def _save_risk() -> None:
    try:
        RISK_FILE.write_text(json.dumps(RISK_STATE, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _demo_enabled() -> bool:
    """Demo data fills the UI whenever MT5 is not actually connected.

    Controlled by GODMODE_DEMO_DATA (default 'auto'): 'auto' = use demo only when
    MT5 is offline; 'off' = never; 'on' = always.
    """
    mode = os.getenv("GODMODE_DEMO_DATA", "auto").strip().lower()
    if mode == "off":
        return False
    if mode == "on":
        return True
    return not bool(mt5_bridge.status().get("connected"))


def _safe_public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(settings)
    mt5_cfg = out.get("mt5Connection")
    if isinstance(mt5_cfg, dict) and mt5_cfg.get("password"):
        mt5_cfg["password"] = ""
    return out

def _live_market() -> dict[str, Any]:
    trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    snap = mt5_bridge.market_snapshot(str(trading.get("symbol", mt5_bridge.symbol)), str(trading.get("timeframe", "M15")))
    if not snap.get("connected") and _demo_enabled():
        return demo_data.market_snapshot(str(trading.get("symbol", mt5_bridge.symbol)), str(trading.get("timeframe", "M15")))
    return snap

def _live_account() -> dict[str, Any]:
    acc = mt5_bridge.account_snapshot()
    if not acc.get("connected") and _demo_enabled():
        return demo_data.account_snapshot()
    return acc

def _trades_kpis(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute win rate, profit factor, expectancy from a trade history list."""
    total = len(history)
    if total == 0:
        return {"winRate": 0.0, "profitFactor": 0.0, "expectancy": 0.0, "totalClosed": 0}
    wins   = [t for t in history if float(t.get("pnlUsd", 0) or 0) > 0]
    losses = [t for t in history if float(t.get("pnlUsd", 0) or 0) < 0]
    gross_profit = sum(float(t.get("pnlUsd", 0) or 0) for t in wins)
    gross_loss   = abs(sum(float(t.get("pnlUsd", 0) or 0) for t in losses))
    net = gross_profit - gross_loss
    return {
        "winRate": round((len(wins) / total) * 100, 1),
        "profitFactor": round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
        "expectancy": round(net / total, 2),
        "netPnlToday": 0.0,
        "totalClosed": total,
    }


def _live_trades() -> dict[str, Any]:
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        return demo_data.trades()
    history = _merge_recent_closed(mt5_bridge.closed_bot_trades(days=90))
    # Attribute each closed trade to its real strategy + reason AND feed the AI
    # learning loop (idempotent, real-data only). This is what lets the AI analyse.
    history = _enrich_history(history, learn=True)
    kpis = _trades_kpis(history)
    return {
        "active": mt5_bridge.open_positions(bot_only=True),
        "pending": mt5_bridge.pending_orders(bot_only=True),
        "history": history,
        "memoryScope": "bot_only",
        "source": "mt5" if mt5_bridge.status().get("connected") else "not_connected",
        "message": "Only positions/deals stamped with the GodMode magic number or comment prefix are shown.",
        **kpis,
    }

def _live_signals() -> list[dict[str, Any]]:
    decision_cached = _cached_decision()
    market = decision_cached.get("_market") or _live_market()
    if not market.get("connected"):
        return []
    if market.get("source") == "demo":
        return demo_data.signals()
    decision = {k: v for k, v in decision_cached.items() if k != "_market"}
    action = str(decision.get("action", "WAIT")).upper()
    side = str(decision.get("side", market.get("side", "WAIT"))).upper()
    if action not in {"TAKE_TRADE", "WAIT", "SKIP", "BLOCK"}:
        action = "WAIT"
    plan = decision.get("tradePlan", {}) if isinstance(decision.get("tradePlan"), dict) else {}
    selected_strategy = decision.get("selectedStrategy", {}) if isinstance(decision.get("selectedStrategy"), dict) else {}
    price = market.get("price")
    session = market.get("session", "Unknown")
    primary = {
        "id": f"live-{int(time.time())}",
        "time": time.strftime("%H:%M:%S"),
        "date": time.strftime("%Y-%m-%d"),
        "pair": market.get("symbol", "XAUUSD"),
        "symbol": market.get("symbol", "XAUUSD"),
        "side": side if action == "TAKE_TRADE" else "WAIT",
        "strategy": selected_strategy.get("name") or decision.get("strategy") or market.get("activeStrategy", "AI Evaluation"),
        "timeframe": market.get("timeframe", "M15"),
        "entry": plan.get("entry") or price,
        "entryPrice": plan.get("entry") or price,
        "sl": plan.get("sl"),
        "tp1": plan.get("tp1"),
        "tp2": plan.get("tp2"),
        "tp3": plan.get("tp3"),
        "tp4": plan.get("tp4"),
        "rr": plan.get("rrToTP1") or plan.get("rrToTP2"),
        "confidence": int(float(decision.get("confidence", 0) or 0)),
        "status": action,
        "result": "—",
        "price": price,
        "change": "0.00%",
        "session": session,
        "reason": decision.get("reason"),
        "source": "live_ai",
        "isPrimary": True,
    }
    signals = [primary]
    # Ensemble leaderboard: surface the next-best candidate strategies for THIS bar so
    # the "Featured High-Confidence Signals" cards show multiple real strategies, not one.
    candidates = decision.get("strategyCandidates") or []
    for c in candidates[1:4]:
        signals.append({
            "id": f"cand-{c.get('name','')[:6]}-{int(time.time())}",
            "time": time.strftime("%H:%M:%S"),
            "date": time.strftime("%Y-%m-%d"),
            "pair": market.get("symbol", "XAUUSD"),
            "symbol": market.get("symbol", "XAUUSD"),
            "side": side if side in {"BUY", "SELL"} else "WAIT",
            "strategy": c.get("name"),
            "timeframe": market.get("timeframe", "M15"),
            "entry": price,
            "entryPrice": price,
            "rr": plan.get("rrToTP2"),
            "confidence": int(float(c.get("score", 0) or 0)),
            "status": "CANDIDATE",
            "result": "—",
            "price": price,
            "session": session,
            "reason": f"Ensemble candidate · regime fit {c.get('fit')}, live win-rate {c.get('liveWinRate')}% over {c.get('trades',0)} samples ({c.get('source')}).",
            "source": "live_ai_candidate",
        })
    return signals

def _live_dashboard() -> dict[str, Any]:
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        d = demo_data.dashboard()
        d["status"] = status()
        # Reflect real market hours even on demo data so 'Market Closed' is honest on weekends.
        mkt = _market_state()
        if isinstance(d.get("decision"), dict):
            d["decision"]["marketOpen"] = bool(mkt.get("open", True))
            d["decision"]["marketStatus"] = mkt.get("reason", "")
            if not mkt.get("open", True):
                d["decision"]["action"] = "MARKET_CLOSED"
                d["decision"]["reason"] = f"Market closed — {mkt.get('reason', 'outside trading hours')}."
        return d
    account_data = _live_account()
    decision_cached = _cached_decision()
    market = decision_cached.get("_market") or _live_market()
    trades_data = _live_trades()
    decision = {k: v for k, v in decision_cached.items() if k != "_market"}
    return {
        "status": status(),
        "account": account_data,
        "market": market,
        "decision": decision,
        "trades": trades_data,
        "why": decision.get("reasons", ["Waiting for live MT5 data."]),
        "equityCurve": _live_analytics().get("equityCurve", []),
        "topStrategies": _live_analytics().get("topStrategies", []),
        "source": "mt5" if market.get("connected") else "not_connected",
    }

def _risk_limits_view() -> dict[str, Any]:
    """Structured, persisted risk limits the Risk page renders and edits."""
    return {
        "maxDailyLossPct": RISK_STATE.get("maxDailyLossPct", RISK_DEFAULTS["maxDailyLossPct"]),
        "maxDrawdownPct": RISK_STATE.get("maxDrawdownPct", RISK_DEFAULTS["maxDrawdownPct"]),
        "maxRiskPerTradePct": RISK_STATE.get("maxRiskPerTradePct", RISK_DEFAULTS["maxRiskPerTradePct"]),
        "maxOpenRiskPct": RISK_STATE.get("maxOpenRiskPct", RISK_DEFAULTS["maxOpenRiskPct"]),
        "maxExposurePct": RISK_STATE.get("maxExposurePct", RISK_DEFAULTS["maxExposurePct"]),
        "lossStreakLimit": RISK_STATE.get("lossStreakLimit", RISK_DEFAULTS["lossStreakLimit"]),
        "newsFilterMinutes": RISK_STATE.get("newsFilterMinutes", RISK_DEFAULTS["newsFilterMinutes"]),
        "circuitBreakerPct": RISK_STATE.get("circuitBreakerPct", RISK_DEFAULTS["circuitBreakerPct"]),
        "maxSpreadXau": RISK_STATE.get("maxSpreadXau", RISK_DEFAULTS["maxSpreadXau"]),
        "sessionCaps": RISK_STATE.get("sessionCaps", RISK_DEFAULTS["sessionCaps"]),
        "rules": RISK_STATE.get("rules", {}),
    }

def _live_risk() -> dict[str, Any]:
    account_data = _live_account()
    trades_data = _live_trades()
    market = _live_market()
    warnings: list[dict[str, Any]] = []
    if not account_data.get("connected"):
        warnings.append({"type": "warning", "title": "MT5 Not Connected", "detail": account_data.get("detail", "Open MT5 and log in to a broker account."), "time": "now"})
    if account_data.get("source") == "demo":
        warnings = [
            {"type": "warning", "title": "Max Daily Loss Approaching", "detail": "Used 88% of daily loss limit", "time": "2m ago"},
            {"type": "warning", "title": "High Exposure: XAUUSD", "detail": "Exposure 28% above recommended", "time": "5m ago"},
            {"type": "warning", "title": "News Event in 15m", "detail": "High-impact news approaching", "time": "13m ago"},
            {"type": "success", "title": "Spread Normalized", "detail": "Spread back to normal levels", "time": "17m ago"},
        ]
    if kill_switch.status().get("active"):
        warnings.insert(0, {"type": "danger", "title": "Emergency Kill Switch Active", "detail": kill_switch.status().get("reason", "Trading blocked."), "time": "now"})
    return {
        "account": account_data,
        "trades": trades_data,
        "market": market,
        "warnings": warnings,
        "limits": _risk_limits_view(),
        "overrides": RISK_STATE,
        "strategies": list(STRATEGIES_STATE.values()),
        "source": account_data.get("source", "not_connected"),
    }

def _day_insight(day_trades: list[dict[str, Any]]) -> dict[str, str]:
    """From a single day's REAL closed trades, derive (1) what the AI effectively detected that day
    and (2) the best optimisation for the FOLLOWING day. Everything here is computed from that day's
    own outcomes — it's guidance grounded in real results, not a generic tip."""
    n = len(day_trades)
    if not n:
        return {"detected": "No trades — the tape never cleared the bot's entry gates (low efficiency / "
                            "insufficient confluence / wide spread).",
                "optimization": "Keep your settings. Wait for a clean London–NY trend setup; quiet days are "
                                "correctly skipped, not forced."}
    pnls = [float(t.get("pnlUsd", 0) or 0) for t in day_trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    net = round(sum(pnls), 2)
    confs = [float(t.get("confidence", 0) or 0) for t in day_trades if t.get("confidence") is not None]
    avg_conf = round(sum(confs) / len(confs), 0) if confs else 0
    wr = round(wins / n * 100)
    sess_counts: dict[str, int] = {}
    for t in day_trades:
        s = str(t.get("session") or "Unknown")
        sess_counts[s] = sess_counts.get(s, 0) + 1
    top_sess = max(sess_counts, key=sess_counts.get) if sess_counts else "—"
    # What the AI detected (framed by the day's realised behaviour)
    if net > 0 and wr >= 50:
        detected = (f"Clean, tradeable tape — {n} trade(s), {wins}W/{losses}L, net {net:+}, "
                    f"avg confidence {avg_conf:.0f}%. Best activity in {top_sess}. Signals followed through.")
    elif net < 0 and wr < 50:
        detected = (f"Choppy / low follow-through — {n} trade(s), {wins}W/{losses}L, net {net:+}. "
                    f"Entries triggered (avg conf {avg_conf:.0f}%) but price reversed before target — classic chop.")
    else:
        detected = (f"Mixed tape — {n} trade(s), {wins}W/{losses}L, net {net:+}, avg confidence "
                    f"{avg_conf:.0f}%. Some setups worked, some faded; no decisive regime.")
    # Best optimisation for the FOLLOWING day
    if net < 0:
        if avg_conf and avg_conf < 75:
            optimization = ("Raise Standard Confidence and require 5/12 confluence tomorrow — most losers were "
                            "marginal signals that wouldn't pass a stricter gate.")
        else:
            optimization = ("Signal quality was OK but costs/timing bled it — tighten Max Spread and trade "
                            "London–NY only tomorrow so cost drag can't turn break-even into a loss.")
    elif net > 0 and wr >= 60:
        optimization = ("Keep the current config — it matched the regime. On A+ continuations consider letting "
                        "the prove/confirm/press pyramid scale the winners.")
    elif net > 0:
        optimization = "Hold settings; the edge showed but the sample is small. Let it prove out before changing anything."
    else:
        optimization = ("Stay defensive tomorrow: keep range-awareness on and confluence high until a clean "
                        "trend re-establishes — don't loosen gates chasing a flat day.")
    return {"detected": detected, "optimization": optimization}


def _build_returns_calendar(history: list[dict[str, Any]], starting_balance: float) -> list[dict[str, Any]]:
    """Per-DAY calendar cells (Mon–Fri grid the UI groups by ISO week) with PnL, trade counts and a
    clickable AI insight for each day. Built from the same real closed-trade history as the heatmap."""
    import datetime as _dt
    _wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_map: dict[str, dict[str, Any]] = {}
    for t in history:
        cts = int(t.get("closeTimestamp", 0) or 0)
        if not cts:
            continue
        try:
            dd = _dt.datetime.utcfromtimestamp(cts)
        except Exception:
            continue
        iso_year, iso_week, iso_wd = dd.isocalendar()
        if iso_wd > 5:   # weekend (XAUUSD closed) — skip
            continue
        key = dd.strftime("%Y-%m-%d")
        cell = day_map.setdefault(key, {"date": key, "week": f"W{iso_week:02d}", "dow": _wd[iso_wd - 1],
                                        "pnl": 0.0, "trades": 0, "wins": 0, "losses": 0, "_t": []})
        cell["pnl"] = round(cell["pnl"] + float(t.get("pnlUsd", 0) or 0), 2)
        cell["trades"] += 1
        p = float(t.get("pnlUsd", 0) or 0)
        if p > 0:
            cell["wins"] += 1
        elif p < 0:
            cell["losses"] += 1
        cell["_t"].append(t)
    base = max(starting_balance, 1.0)
    out: list[dict[str, Any]] = []
    for key in sorted(day_map.keys()):
        cell = day_map[key]
        cell["pct"] = round(cell["pnl"] / base * 100, 2)
        cell.update(_day_insight(cell.pop("_t")))
        out.append(cell)
    return out[-40:]   # last ~8 trading weeks


def _live_analytics(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        return demo_data.analytics(date_from, date_to)
    account_data = _live_account()
    currency = account_data.get("currency") or ""
    starting_balance = float(account_data.get("balance", 10000) or 10000)
    history = _enrich_history(_merge_recent_closed(mt5_bridge.closed_bot_trades(days=365)))
    if date_from or date_to:
        def _in(t):
            d = str(t.get("closeTime") or t.get("date") or "")[:10]
            return (not date_from or d >= date_from) and (not date_to or d <= date_to)
        history = [t for t in history if _in(t)]
    total = len(history)
    wins = [t for t in history if float(t.get("pnlUsd", 0) or 0) > 0]
    losses = [t for t in history if float(t.get("pnlUsd", 0) or 0) < 0]
    gross_profit = sum(float(t.get("pnlUsd", 0) or 0) for t in wins)
    gross_loss = abs(sum(float(t.get("pnlUsd", 0) or 0) for t in losses))
    net = gross_profit - gross_loss

    # Build equity curve from cumulative PnL.
    # Chart components read: EquityCurve -> {date, equity, benchmark}; DrawdownChart -> {date, value}
    equity_curve: list[dict[str, Any]] = []
    running = starting_balance - net  # reconstruct starting balance
    base = running
    for i, t in enumerate(reversed(history)):
        running += float(t.get("pnlUsd", 0) or 0)
        equity_curve.append({"x": i, "value": round(running, 2), "equity": round(running, 2),
                             "benchmark": round(base, 2),
                             "date": str(t.get("closeTime", ""))[:10] or f"#{i+1}"})

    # Max drawdown from equity curve
    peak, max_dd = 0.0, 0.0
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak else 0.0
        if dd > max_dd:
            max_dd = dd

    # Drawdown series — DrawdownChart reads {date, value}
    drawdown_series: list[dict[str, Any]] = []
    peak2 = 0.0
    for pt in equity_curve:
        v = pt["value"]
        if v > peak2:
            peak2 = v
        drawdown_series.append({"x": pt["x"], "date": pt["date"], "value": -round((peak2 - v) / peak2 * 100, 2) if peak2 else 0.0})

    # Session performance
    session_map: dict[str, dict[str, Any]] = {}
    for t in history:
        sess = str(t.get("session") or "Unknown")
        pnl = float(t.get("pnlUsd", 0) or 0)
        s = session_map.setdefault(sess, {"Session": sess, "Net PnL": 0.0, "Wins": 0, "Trades": 0, "Expectancy": 0.0})
        s["Net PnL"] = round(s["Net PnL"] + pnl, 2)
        s["Trades"] += 1
        if pnl > 0:
            s["Wins"] += 1
    sessions = []
    for s in session_map.values():
        t2 = s["Trades"]
        sessions.append({**s, "Win Rate": f"{round(s['Wins']/t2*100,1) if t2 else 0}%", "Expectancy": round(s["Net PnL"]/t2, 2) if t2 else 0})

    # Top strategies grouped by the REAL strategy name (from the trade-context store /
    # stamped comment), not the raw entry-type comment. Each row carries BOTH the
    # capitalised keys the Analytics table reads AND the lowercase name/winRate keys
    # the Dashboard card reads, so both surfaces render correctly.
    strat_map: dict[str, dict[str, Any]] = {}
    for t in history:
        name = str(t.get("strategy") or strategy_from_comment(str(t.get("comment") or "")) or "GodMode Bot")
        pnl = float(t.get("pnlUsd", 0) or 0)
        s = strat_map.setdefault(name, {"Strategy": name, "name": name, "Net PnL": 0.0, "netPnl": 0.0, "Wins": 0, "Trades": 0})
        s["Net PnL"] = round(s["Net PnL"] + pnl, 2)
        s["netPnl"] = s["Net PnL"]
        s["Trades"] += 1
        if pnl > 0:
            s["Wins"] += 1
    top_strategies = sorted(strat_map.values(), key=lambda x: x["Net PnL"], reverse=True)[:8]
    for s in top_strategies:
        t3 = s["Trades"]
        wr = round(s["Wins"] / t3 * 100, 1) if t3 else 0
        s["Win Rate"] = f"{wr}%"
        s["winRate"] = wr
        s["trades"] = s["Trades"]
        s["enabled"] = True

    # Returns heatmap — ReturnsHeatmap reads rows of {week, Mon, Tue, Wed, Thu, Fri}
    # Build a per-ISO-week, per-weekday PnL grid from close timestamps.
    import datetime as _dt
    _wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week_grid: dict[str, dict[str, float]] = {}
    for t in history:
        cts = int(t.get("closeTimestamp", 0) or 0)
        if not cts:
            continue
        try:
            d = _dt.datetime.utcfromtimestamp(cts)
        except Exception:
            continue
        iso_year, iso_week, iso_wd = d.isocalendar()
        wk = f"W{iso_week:02d}"
        day = _wd[iso_wd - 1]
        row = week_grid.setdefault(wk, {})
        row[day] = round(row.get(day, 0.0) + float(t.get("pnlUsd", 0) or 0), 2)
    returns = [{"week": wk, **{d: round(week_grid[wk].get(d, 0.0), 1) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]}}
               for wk in sorted(week_grid.keys())][-8:]
    # Monthly bars for the market-heatmap card — BarDistribution reads {x, v}
    month_map: dict[str, float] = {}
    for t in history:
        d = str(t.get("closeTime") or "")[:7]
        if d:
            month_map[d] = round(month_map.get(d, 0.0) + float(t.get("pnlUsd", 0) or 0), 2)
    market_heatmap = [{"x": k, "v": v} for k, v in sorted(month_map.items())]

    # Execution quality histogram (hold time in hours)
    exec_map: dict[str, int] = {"<1h": 0, "1-4h": 0, "4-24h": 0, "1-3d": 0, ">3d": 0}
    for t in history:
        ht = str(t.get("holdTime", "") or "")
        if "m" in ht.lower() or not ht:
            exec_map["<1h"] += 1
        elif "h" in ht.lower():
            try:
                h = float(ht.lower().replace("h", "").strip().split()[0])
                if h < 1:
                    exec_map["<1h"] += 1
                elif h < 4:
                    exec_map["1-4h"] += 1
                else:
                    exec_map["4-24h"] += 1
            except Exception:
                exec_map["4-24h"] += 1
        else:
            exec_map[">3d"] += 1
    # BarDistribution reads {x, v}
    execution_quality = [{"x": k, "v": v} for k, v in exec_map.items()]

    # ScatterPerformance reads {confidence, result}
    confidence_result = [{"confidence": float(t.get("confidence", 50) or 50), "result": float(t.get("pnlUsd", 0) or 0)} for t in history]
    # Expectancy vs win rate scatter (per strategy) — reuse confidence/result keys
    expectancy_scatter = [{"confidence": float(str(s.get("Win Rate","0%")).replace("%","")), "result": round(s["Net PnL"] / s["Trades"], 2) if s["Trades"] else 0, "name": s["Strategy"]} for s in top_strategies]
    buy_wins = sum(1 for t in history if float(t.get("pnlUsd",0)or 0)>0 and str(t.get("direction","")).upper()=="BUY")
    sell_wins = sum(1 for t in history if float(t.get("pnlUsd",0)or 0)>0 and str(t.get("direction","")).upper()=="SELL")
    buy_total = sum(1 for t in history if str(t.get("direction","")).upper()=="BUY") or 1
    sell_total = sum(1 for t in history if str(t.get("direction","")).upper()=="SELL") or 1

    return {
        "source": "mt5_bot_history" if total else "no_bot_history",
        "kpis": {
            "netProfit": round(net, 2),
            "returnPct": round(net / (starting_balance - net) * 100, 2) if (starting_balance - net) > 0 else 0.0,
            "totalTrades": total,
            "winRate": round((len(wins) / total) * 100, 2) if total else 0.0,
            "profitFactor": round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
            "expectancy": round(net / total, 2) if total else 0.0,
            "maxDrawdown": round(max_dd, 2),
        },
        "equityCurve": equity_curve,
        "drawdown": drawdown_series,
        "returns": returns,
        "returnsCalendar": _build_returns_calendar(history, starting_balance - net),
        "topStrategies": top_strategies,
        "sessions": sessions,
        "executionQuality": execution_quality,
        "confidenceResult": confidence_result,
        "expectancyScatter": expectancy_scatter,
        "marketHeatmap": market_heatmap,
        "buyWinRate": round(buy_wins / buy_total * 100, 1),
        "sellWinRate": round(sell_wins / sell_total * 100, 1),
        "breakEvenRate": 0.0,
        "lossRate": round((len(losses) / total * 100), 1) if total else 0.0,
        "startingBalance": round(starting_balance - net, 2),
        "endingBalance": round(starting_balance, 2),
        "avgSlippage": "< 0.5 pts",
        "fillQuality": "Good" if total > 0 else "Waiting",
        "history": history,
        "currency": currency,
        "account": account_data,
    }

def _manual_to_entry(m: dict[str, Any]) -> dict[str, Any]:
    """Map a user-written manual entry onto the journal-entry shape the UI renders."""
    pnl = float(m.get("pnl", 0) or 0)
    side = str(m.get("side") or m.get("direction") or "—").upper()
    return {
        "manual": True, "id": m.get("id"), "symbol": m.get("symbol") or "XAUUSD",
        "direction": side, "side": side, "outcome": m.get("outcome") or ("WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK_EVEN"),
        "pnl": pnl, "pnlUsd": pnl, "time": m.get("time") or m.get("date") or "", "date": str(m.get("date") or m.get("time") or "")[:10],
        "strategy": m.get("strategy") or "Manual note", "session": m.get("session") or "—",
        "marketRegime": m.get("marketRegime") or "Manual entry", "confidence": m.get("confidence", 0),
        "entryPrice": m.get("entryPrice") or "—", "exitPrice": m.get("exitPrice") or "—",
        "sl": m.get("sl") or "—", "tp": m.get("tp") or "—",
        "lessons": m.get("lessons") or "", "improvement": m.get("improvement") or "",
        "aiNotes": m.get("notes") or m.get("aiNotes") or "", "aiScore": "—",
        "tags": (m.get("tags") or ["manual"]), "candles": [], "currency": m.get("currency", ""),
    }


def _merge_manual_journal(entries: list[dict[str, Any]], date_from: str | None, date_to: str | None) -> list[dict[str, Any]]:
    out = list(entries) + [_manual_to_entry(m) for m in MANUAL_JOURNAL]
    if date_from:
        out = [e for e in out if str(e.get("date", "")) >= date_from]
    if date_to:
        out = [e for e in out if str(e.get("date", "")) <= date_to]
    out.sort(key=lambda e: str(e.get("time") or e.get("date") or ""), reverse=True)
    return out


def _live_journal(date_from: str | None = None, date_to: str | None = None) -> list[dict[str, Any]]:
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        return _merge_manual_journal(demo_data.journal(date_from, date_to), date_from, date_to)
    raw = _enrich_history(_merge_recent_closed(mt5_bridge.closed_bot_trades(days=90)))
    entries = []
    for t in raw:
        pnl = float(t.get("pnlUsd", 0) or 0)
        comment = str(t.get("comment") or "")
        # Strategy + reason now come from the enriched trade (context store / stamped comment).
        strategy = t.get("strategy") or "GodMode Bot"
        # Session: prefer the entry-context session; else derive from close-time hour.
        session = t.get("session") or "Unknown"
        if session in (None, "", "Unknown"):
            ct = str(t.get("closeTime") or "")
            try:
                h = int(ct[11:13]) if len(ct) > 12 else 12
                session = "Asian" if (22 <= h or h < 7) else "London" if h < 12 else "New York" if h < 17 else "London/NY Overlap"
            except Exception:
                session = "Unknown"
        r_multiple = t.get("rMultiple")
        review = t.get("aiReview") or {}
        ai_notes = t.get("aiNotes") or review.get("summary") or f"{strategy} · {t.get('exitReason','closed')}. PnL {pnl:+.2f} USD."
        entries.append({
            **t,
            "outcome": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAK_EVEN"),
            "rMultiple": r_multiple if r_multiple is not None else 0.0,
            "pnl": pnl,
            "time": t.get("closeTime", ""),
            "date": str(t.get("closeTime", ""))[:10],
            "strategy": strategy,
            "session": session,
            "marketRegime": t.get("marketRegime") or "Live MT5 Bot Trade",
            "htfTrend": "—",
            "newsImpact": "Filtered",
            "structure": "—",
            "confidence": t.get("confidence", 0),
            "aiScore": t.get("aiScore", "—"),
            "aiNotes": ai_notes,
            "entryReason": t.get("entryReason") or "",
            "lessons": t.get("lessons") or review.get("lesson") or "",
            "improvement": t.get("improvement") or review.get("improvement") or "",
            "tags": ["bot-only", "mt5", str(session).lower().replace("/", "-").replace(" ", "-")],
            "candles": [],
            "currency": t.get("currency", ""),
        })
    return _merge_manual_journal(entries, date_from, date_to)

def _strategies_with_live_stats() -> list[dict[str, Any]]:
    """Catalog strategies enriched with LIVE win-rate / sample size computed from the
    bot's own recorded trades. The catalog numbers remain as a labelled fallback so
    the Strategy page reflects what is actually working, not just static placeholders."""
    stats = memory.stats()
    by_name = {r.get("name"): r for r in stats.get("strategyPerformance", [])}
    out: list[dict[str, Any]] = []
    for s in STRATEGIES_STATE.values():
        row = dict(s)
        m = by_name.get(s.get("name"))
        trades = int(m.get("trades", 0)) if m else 0
        row["liveTrades"] = trades
        row["catalogWinRate"] = s.get("winRate")
        if m and trades > 0:
            row["liveWinRate"] = m.get("winRate")
            row["liveNetPnl"] = m.get("pnl")
            row["totalTrades"] = trades
            if trades >= 5:  # only let a real sample override the headline number
                row["winRate"] = m.get("winRate")
                row["statsSource"] = "live_memory"
            else:
                row["statsSource"] = "catalog_small_sample"
        else:
            row["statsSource"] = "catalog"
        out.append(row)
    return out


class StrategyToggle(BaseModel):
    id: str


def _decision() -> dict[str, Any]:
    return _cached_decision()


def _action_matrix(decision: dict[str, Any] | None = None, position: dict[str, Any] | None = None, market: dict[str, Any] | None = None) -> dict[str, Any]:
    decision = decision or _decision()
    market = market or _live_market()
    position = position or {}
    management = trade_manager.live_management_decision(position or {"profitR": 0.0})
    pyramid = pyramiding_engine.evaluate(decision, position=position or None, market=market, broker_quality=broker_scorer.score(), kill_switch=kill_switch.status())
    action = str(decision.get("action", "WAIT")).upper()
    quality = str(decision.get("quality", "WAIT")).upper()
    confidence = float(decision.get("confidence", 0) or 0)
    dirty = bool(kill_switch.status().get("active") or market.get("newsBlackout") or market.get("dirtyConditions"))
    take = action == "TAKE_TRADE" and quality in {"SCOUT", "STANDARD", "HIGH", "SNIPER"} and confidence >= decision_engine.min_take_score and not dirty
    wait = not take and not dirty and action not in {"SKIP", "BLOCK", "MARKET_CLOSED"}
    return {
        "takeThisTrade": take,
        "skipThisTrade": not take and not wait,
        "waitForBetterEntry": wait,
        "holdWinner": management.get("action") in {"HOLD_WINNER", "HOLD", "PUSH_TP", "TRAIL_STRUCTURE"},
        "moveToBreakEven": management.get("action") == "MOVE_TO_BREAKEVEN",
        "trailStructure": management.get("action") == "TRAIL_STRUCTURE",
        "pushTP": management.get("action") == "PUSH_TP",
        "pyramidOnlyIfProven": bool(pyramid.get("allowed")),
        "stopTradingDirtyConditions": dirty or management.get("action") == "STOP_TRADING_DIRTY_CONDITIONS",
        "decision": decision,
        "management": management,
        "pyramiding": pyramid,
        "safety": {"killSwitch": kill_switch.status(), "botOnlyMemory": True, "liveTradingEnabled": mt5_bridge.live_enabled},
        "strictness": decision_engine.strictness_dict(),
        "blockedReasons": decision.get("decisionBlocks", []),
        "softBlocks": decision.get("softBlocks", []),
    }


@app.get("/", include_in_schema=False)
def root():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"ok": True, "message": "GodMode API running", "docs": "/docs", "ui": "frontend/dist not found"}


@app.get("/api/root")
def api_root():
    return {"ok": True, "message": "GodMode API running", "docs": "/docs"}


@app.get("/api/status")
def status():
    mt5 = mt5_bridge.status()
    demo = _demo_enabled()
    mkt = _market_state()
    return {
        "app": "GodMode Gold Trading Bot",
        "liveConnection": bool(mt5.get("connected")) or demo,
        "mt5Connected": bool(mt5.get("connected")) or demo,
        "marketSession": mt5_bridge.current_session(),
        "marketOpen": bool(mkt.get("open", True)),
        "marketStatus": mkt.get("reason", ""),
        "riskEngine": "ACTIVE" if not kill_switch.status().get("active") else "BLOCKED",
        "agentStatus": "Live" if mt5.get("connected") else ("Demo" if demo else "Waiting for MT5"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mt5": mt5,
        "demo": demo,
        "source": "demo" if demo else mt5.get("source", "not_connected"),
        "security": {"corsRestricted": True, "apiKeyEnabled": bool(api_key), "rateLimitPerMinute": rate_limit_per_minute},
    }


@app.post("/api/mt5/connect")
def mt5_connect(payload: dict[str, Any] = Body(default={})):
    # Saves connection settings and attempts auto/manual connection to the running MT5 terminal.
    mt5_cfg = SETTINGS_STATE.setdefault("mt5Connection", {})
    if payload.get("terminalPath") is not None:
        mt5_cfg["terminalPath"] = payload.get("terminalPath")
    if payload.get("login") is not None:
        mt5_cfg["login"] = str(payload.get("login") or "")
    if payload.get("server") is not None:
        mt5_cfg["server"] = payload.get("server")
    if payload.get("password"):
        mt5_cfg["password"] = payload.get("password")
    result = mt5_bridge.connect({**mt5_cfg, **payload, "symbol": SETTINGS_STATE.get("trading", {}).get("symbol", mt5_bridge.symbol), "magicNumber": SETTINGS_STATE.get("trading", {}).get("magicNumber", mt5_bridge.magic)})
    SETTINGS_STATE["mt5"] = result.get("status", mt5_bridge.status())
    _save_settings()
    return result


@app.post("/api/mt5/disconnect")
def mt5_disconnect():
    return mt5_bridge.disconnect()


@app.post("/api/mt5/auto-connect")
def mt5_auto_connect():
    result = _auto_connect_mt5_on_startup()
    _save_settings()
    return result


@app.post("/api/mt5/refresh")
def mt5_refresh(payload: dict[str, Any] = Body(default={})):
    return mt5_bridge.connect(payload or SETTINGS_STATE.get("mt5Connection", {}))


@app.post("/api/mt5/live-mode")
def mt5_live_mode(payload: dict[str, Any] = Body(default={})):
    enabled = bool(payload.get("enabled", payload.get("liveTradingEnabled", False)))
    SETTINGS_STATE.setdefault("execution", {})["liveTradingEnabled"] = enabled
    SETTINGS_STATE.setdefault("execution", {})["dryRun"] = not enabled
    status_payload = mt5_bridge.set_live_enabled(enabled)
    _save_settings()
    return {"ok": True, "message": "Live trading enabled" if enabled else "Dry run enabled", "mt5": status_payload, "settings": _safe_public_settings(SETTINGS_STATE)}


@app.post("/api/mt5/auto-trading")
def mt5_auto_trading(payload: dict[str, Any] = Body(default={})):
    enabled = bool(payload.get("enabled", payload.get("autoTradingEnabled", False)))
    SETTINGS_STATE.setdefault("execution", {})["autoTradingEnabled"] = enabled
    status_payload = mt5_bridge.set_auto_trading_enabled(enabled)
    _save_settings()
    return {"ok": True, "message": "GodMode auto trading enabled" if enabled else "GodMode auto trading disabled", "mt5": status_payload, "settings": _safe_public_settings(SETTINGS_STATE)}


@app.get("/api/docs-info")
def docs_info():
    return {
        "openApiDocs": "/docs",
        "requiredForBasicMT5": ["No external API key required if MT5 is already open and logged in."],
        "optionalKeys": {
            "GODMODE_API_KEY": "Optional local backend protection. If set, frontend must use VITE_GODMODE_API_KEY.",
            "TELEGRAM_BOT_TOKEN": "Optional. Required only for Telegram alerts.",
            "TELEGRAM_CHAT_ID": "Optional. Required only for Telegram alerts.",
            "DXY_FEED_URL / US10Y_FEED_URL / ECONOMIC_CALENDAR_URL": "Optional live macro/news feed adapters.",
        },
        "mt5Connection": {"terminalPath": "Optional; only needed if auto-detect fails.", "login/server/password": "Optional; only needed if terminal is not already logged in."},
    }


@app.post("/api/telegram/test")
def telegram_test(payload: dict[str, Any] = Body(default={})):
    import urllib.parse, urllib.request
    token = str(payload.get("botToken") or SETTINGS_STATE.get("telegram", {}).get("botToken") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(payload.get("chatId") or SETTINGS_STATE.get("telegram", {}).get("chatId") or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return {"ok": False, "authenticated": False, "message": "Telegram bot token and chat ID are required."}
    text_msg = "GodMode Gold Bot Telegram test: alerts are connected."
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text_msg}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        SETTINGS_STATE.setdefault("telegram", {}).update({"enabled": True, "botToken": token, "chatId": chat_id})
        _save_settings()
        return {"ok": True, "authenticated": True, "message": "Telegram test sent.", "telegramResponse": raw[:500]}
    except Exception as exc:
        return {"ok": False, "authenticated": False, "message": f"Telegram test failed: {exc}"}


@app.post("/api/telegram/recap")
def telegram_recap(payload: dict[str, Any] = Body(default={})):
    """Send a recap (and optional wait-forecast) to Telegram now — for testing the charts."""
    weekly = bool(payload.get("weekly"))
    _send_recap(weekly)
    if payload.get("withForecast"):
        RECAP_STATE["lastWaitForecast"] = 0.0
        _send_wait_forecast()
    return {"ok": True, "message": f"{'Weekly' if weekly else 'Daily'} recap sent (charts require matplotlib).", "chartsAvailable": chart_render.available()}


@app.get("/api/ai/monitor")
def ai_monitor_status():
    """Live AI recovery-monitor read for the open bot trade (for UI/Telegram)."""
    active = mt5_bridge.open_positions(bot_only=True)
    if not active:
        return {"ok": True, "openTrade": False, "message": "No open bot trade to monitor."}
    pos = active[0]
    market = _live_market()
    atr = float(market.get("atr14") or 8) or 8
    rec = assess_recovery({**pos, "currentPrice": market.get("price")}, _decision(), atr)
    return {"ok": True, "openTrade": True, "ticket": pos.get("ticket"), "direction": pos.get("direction"), "recovery": rec, "chartsAvailable": chart_render.available()}


@app.get("/api/export/{dataset}")
def export_dataset(dataset: str, format: str = "json"):
    dataset = dataset.lower()
    data: Any
    if dataset == "trades":
        data = _live_trades()
    elif dataset == "analytics":
        data = _live_analytics()
    elif dataset == "signals":
        data = _live_signals()
    elif dataset == "journal":
        data = _live_journal()
    elif dataset == "settings":
        data = _safe_public_settings(SETTINGS_STATE)
    else:
        return JSONResponse({"ok": False, "message": "Unknown export dataset."}, status_code=404)
    if format.lower() == "csv":
        rows = data if isinstance(data, list) else data.get("history") or data.get("active") or []
        if not rows:
            return Response("message\nNo rows available\n", media_type="text/csv")
        keys = sorted({k for row in rows if isinstance(row, dict) for k in row.keys()})
        lines = [",".join(keys)]
        for row in rows:
            lines.append(",".join(str(row.get(k, "")).replace(",", " ").replace("\n", " ") for k in keys))
        return Response("\n".join(lines), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=godmode_{dataset}.csv"})
    return JSONResponse(data, headers={"Content-Disposition": f"attachment; filename=godmode_{dataset}.json"})


@app.get("/api/account")
def account():
    return _live_account()


@app.get("/api/market/snapshot")
def market_snapshot():
    return _live_market()


@app.get("/api/dashboard")
def dashboard():
    return _live_dashboard()


@app.get("/api/signals")
def signals():
    return _live_signals()


@app.get("/api/strategies")
def strategies():
    return _strategies_with_live_stats()


@app.get("/api/trades")
def trades():
    return _live_trades()


@app.get("/api/trades/active")
def active_trades():
    return _live_trades()["active"]


@app.get("/api/trades/pending")
def pending_trades():
    return _live_trades()["pending"]


@app.get("/api/trades/history")
def trade_history():
    return _live_trades()["history"]


@app.get("/api/risk")
def risk():
    return _live_risk()


@app.get("/api/analytics")
def analytics(date_from: str | None = None, date_to: str | None = None):
    return _live_analytics(date_from, date_to)


@app.get("/api/journal")
def journal(date_from: str | None = None, date_to: str | None = None):
    return _live_journal(date_from, date_to)


@app.post("/api/journal/entry")
def journal_add_entry(payload: dict[str, Any] = Body(default={})):
    """Add a manual journal entry (a reflection / lesson the user writes). Persisted to disk so it
    survives restarts and shows alongside the bot's auto trade-journal entries."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = {
        "id": f"man-{int(time.time()*1000)}",
        "date": str(payload.get("date") or now[:10]),
        "time": str(payload.get("date") or now[:10]) + " " + now[11:19] + " UTC",
        "symbol": str(payload.get("symbol") or "XAUUSD")[:20],
        "side": str(payload.get("side") or "—")[:8],
        "outcome": str(payload.get("outcome") or "NOTE")[:16],
        "pnl": float(payload.get("pnl", 0) or 0),
        "strategy": str(payload.get("strategy") or "Manual note")[:80],
        "session": str(payload.get("session") or "—")[:40],
        "confidence": float(payload.get("confidence", 0) or 0),
        "lessons": str(payload.get("lessons") or "")[:2000],
        "improvement": str(payload.get("improvement") or "")[:2000],
        "notes": str(payload.get("notes") or "")[:2000],
        "tags": [str(t)[:24] for t in (payload.get("tags") or ["manual"])][:8],
        "createdAt": now,
    }
    MANUAL_JOURNAL.append(entry)
    try:
        with MANUAL_JOURNAL_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        return {"ok": False, "message": f"Could not save: {exc}"}
    return {"ok": True, "message": "Journal entry saved.", "entry": _manual_to_entry(entry)}


@app.get("/api/journal/decisions")
def journal_decisions(category: str | None = None, limit: int = 250):
    """The Decision & Management Journal: WHY the bot did or didn't trade (entry decisions with
    confidence + blocking reasons), every management action (BE/trail/recovery-room/fast-fail/
    partials), and close outcomes — persisted across restarts."""
    items = DECISION_JOURNAL
    if category and category not in ("all", ""):
        items = [e for e in items if e.get("category") == category]
    counts: dict[str, int] = {}
    for e in DECISION_JOURNAL:
        c = str(e.get("category", "?"))
        counts[c] = counts.get(c, 0) + 1
    return {"ok": True, "items": items[: max(1, min(int(limit or 250), 1000))],
            "counts": counts, "total": len(DECISION_JOURNAL)}


@app.post("/api/journal/decisions/clear")
def journal_decisions_clear():
    DECISION_JOURNAL.clear()
    _LAST_ENTRY_SIG["sig"] = None
    try:
        DECISION_JOURNAL_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "message": "Decision journal cleared."}


@app.get("/api/settings")
def settings():
    _apply_runtime_settings()
    SETTINGS_STATE["mt5"] = mt5_bridge.status()
    return _safe_public_settings(SETTINGS_STATE)


@app.get("/api/ai/decision")
def ai_decision():
    return _decision()


@app.get("/api/ai/trade-review/{ticket}")
def ai_trade_review(ticket: str):
    """Return (or generate on demand) the AI post-trade review for a closed trade."""
    cached = TRADE_REVIEWS.get(str(ticket))
    if cached:
        return {"ok": True, "ticket": ticket, "review": cached, "cached": True}
    history = _enrich_history(_merge_recent_closed(mt5_bridge.closed_bot_trades(days=365))) if mt5_bridge.status().get("connected") else demo_data.journal()
    trade = next((x for x in history if str(x.get("ticket")) == str(ticket)), None)
    if not trade:
        return {"ok": False, "message": "Trade not found in bot history."}
    review = ai_reviewer.review(trade)
    TRADE_REVIEWS[str(ticket)] = review
    return {"ok": True, "ticket": ticket, "review": review, "cached": False}


@app.get("/api/ai/review-summary")
def ai_review_summary():
    """Recent AI post-trade reviews + the provider in use (Claude or local fallback)."""
    reviews = list(TRADE_REVIEWS.values())[-10:]
    provider = f"claude:{ai_reviewer.model}" if (ai_reviewer.enabled and ai_reviewer.api_key) else "local_fallback"
    avg_score = round(sum(float(r.get("aiScore", 0) or 0) for r in reviews) / max(len(reviews), 1), 1) if reviews else 0
    return {"ok": True, "provider": provider, "count": len(TRADE_REVIEWS), "avgProcessScore": avg_score, "reviews": reviews}


@app.get("/api/ai/action-matrix")
def ai_action_matrix():
    return _action_matrix()


@app.get("/api/ai/strictness")
def ai_strictness():
    return {"ok": True, "settings": decision_engine.strictness_dict(), "pyramiding": pyramiding_engine.settings_dict(camel=True)}


@app.post("/api/ai/strictness")
def update_ai_strictness(payload: dict[str, Any] = Body(default={})):
    SETTINGS_STATE.setdefault("ai", {}).update(payload)
    applied = decision_engine.configure_strictness(SETTINGS_STATE.get("ai", {}))
    SETTINGS_STATE["ai"].update(applied)
    _save_settings()
    return {"ok": True, "settings": applied, "message": "AI first-entry strictness updated. Pyramiding thresholds remain strict."}


@app.post("/api/ai/evaluate")
def ai_evaluate(payload: dict[str, Any] = Body(default={})):
    decision = payload.get("decision") or decision_engine.evaluate(payload.get("market") or _live_market(), list(STRATEGIES_STATE.values()), memory.stats())
    return _action_matrix(decision=decision, position=payload.get("position") or {}, market=payload.get("market") or _live_market())


@app.get("/api/strategy/arsenal")
def strategy_arsenal():
    return {"mode": "Auto-select from Arsenal", "strictness": decision_engine.strictness_dict(), "takeThreshold": decision_engine.min_take_score, "sniperThreshold": decision_engine.min_sniper_score, "strategies": list(STRATEGIES_STATE.values()), "decision": _decision()}


def _order_payload_from_market(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    market = _live_market()
    trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    symbol = str(payload.get("symbol") or trading.get("symbol") or market.get("symbol") or "XAUUSD")
    side = str(payload.get("side") or payload.get("direction") or market.get("side") or "BUY").upper()
    volume = float(payload.get("volume") or payload.get("lot") or payload.get("lots") or 0.01)
    price = float(payload.get("price") or market.get("price") or 0.0)
    sl = payload.get("sl")
    tp = payload.get("tp")
    # If no SL/TP is supplied, build conservative placeholders around the current price.
    if price and (sl is None or tp is None):
        dist = 6.0
        if side == "BUY":
            sl = sl if sl is not None else round(price - dist, 3)
            tp = tp if tp is not None else round(price + dist * 1.8, 3)
        else:
            sl = sl if sl is not None else round(price + dist, 3)
            tp = tp if tp is not None else round(price - dist * 1.8, 3)
    return {
        "symbol": symbol,
        "side": side,
        "volume": volume,
        "sl": sl,
        "tp": tp,
        "deviation": int(payload.get("deviation") or mt5_bridge.max_deviation),
        "magic": mt5_bridge.magic,
        "comment": str(payload.get("comment") or "GODMODE_manual"),
        "source": "godmode_bot",
    }

def _record_auto_heartbeat(result: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "id": int(time.time() * 1000),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": bool(result.get("ok")),
        "blocked": bool(result.get("blocked")),
        "message": result.get("message", "Auto-trade checked."),
        "reason": result.get("reason", "auto_trade"),
        "quality": ((result.get("actionMatrix") or {}).get("decision") or {}).get("quality"),
        "confidence": ((result.get("actionMatrix") or {}).get("decision") or {}).get("confidence"),
        "blockedReasons": (result.get("actionMatrix") or {}).get("blockedReasons") or ((result.get("actionMatrix") or {}).get("decision") or {}).get("decisionBlocks", []),
        "softBlocks": (result.get("actionMatrix") or {}).get("softBlocks") or ((result.get("actionMatrix") or {}).get("decision") or {}).get("softBlocks", []),
    }
    AUTO_TRADE_HEARTBEAT.insert(0, entry)
    del AUTO_TRADE_HEARTBEAT[100:]
    try:
        _journal_entry_decision(result, entry)
    except Exception:
        pass
    return entry


def _volatility_normalized_base_lot(symbol: str, entry: float, sl: float, fallback_lot: float) -> dict[str, Any]:
    """Size the BASE lot so the trade risks ~``trading.riskPerTrade`` % of equity given the
    REAL stop distance, instead of a fixed lot. This keeps dollar risk constant across calm
    and volatile (wide-stop) regimes — the single biggest real-money quality fix.

    Broker-accurate: loss-per-lot = (stopDistance / tickSize) * tickValue. Falls back to the
    Gold contract model ($100 per $1 move per lot) when tick specs are unavailable, and to the
    fixed ``fallback_lot`` whenever equity / stop / specs aren't usable. Always rounds DOWN to
    the broker volume step (never overshoot the risk budget) and clamps to broker min/max.
    """
    try:
        tcfg = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
        risk_pct = float(tcfg.get("riskPerTrade", 0.5) or 0.5)
        stop_dist = abs(float(entry) - float(sl))
        equity = float(_live_account().get("equity") or 0)
        if stop_dist <= 0 or equity <= 0 or risk_pct <= 0:
            return {"lot": round(fallback_lot, 2), "source": "fallback_no_inputs"}
        specs = mt5_bridge.symbol_specs(symbol)
        tick_val = float(specs.get("tradeTickValue") or 0.0)
        tick_size = float(specs.get("tradeTickSize") or 0.0)
        if tick_val > 0 and tick_size > 0:
            loss_per_lot = (stop_dist / tick_size) * tick_val
        else:
            loss_per_lot = stop_dist * 100.0   # XAUUSD contract = 100 oz → $100 per $1 move per lot
        if loss_per_lot <= 0:
            return {"lot": round(fallback_lot, 2), "source": "fallback_bad_specs"}
        risk_cash = equity * risk_pct / 100.0
        raw_lot = risk_cash / loss_per_lot
        minv = float(specs.get("volumeMin", 0.01) or 0.01)
        step = float(specs.get("volumeStep", 0.01) or 0.01) or 0.01
        maxv = float(specs.get("volumeMax", 100.0) or 100.0)
        stepped = (int(raw_lot / step)) * step          # round DOWN to a whole step
        lot = round(max(minv, min(maxv, stepped)), 2)
        return {"lot": lot, "rawLot": round(raw_lot, 4), "riskCash": round(risk_cash, 2),
                "riskedAtMin": round(minv * loss_per_lot, 2), "actualRisk": round(lot * loss_per_lot, 2),
                "riskPct": risk_pct, "stopDist": round(stop_dist, 2), "minClamped": stepped < minv,
                "source": specs.get("source", "calc")}
    except Exception as exc:
        return {"lot": round(fallback_lot, 2), "source": f"fallback_err:{exc}"}


def _auto_trade_tick(reason: str = "manual_tick") -> dict[str, Any]:
    status_payload = mt5_bridge.status()
    execution = SETTINGS_STATE.get("execution", {}) if isinstance(SETTINGS_STATE.get("execution"), dict) else {}
    ai_cfg = SETTINGS_STATE.get("ai", {}) if isinstance(SETTINGS_STATE.get("ai"), dict) else {}
    def blocked(message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        result = {"ok": False, "blocked": True, "reason": reason, "message": message, "strictness": decision_engine.strictness_dict(), **(extra or {})}
        result["heartbeat"] = _record_auto_heartbeat(result)
        return result
    if kill_switch.status().get("active"):
        return blocked("Emergency kill switch is active.", {"killSwitch": kill_switch.status()})
    if not status_payload.get("connected"):
        if not AUTO_TRADE_STATE.get("disconnectAlerted"):
            AUTO_TRADE_STATE["disconnectAlerted"] = True
            _push_notification("MT5 disconnected", "Auto-entry paused — MT5 connection lost. It resumes automatically once reconnected. Open trades are protected by their broker SL.", "warning")
        return blocked("MT5 is not connected.", {"mt5": status_payload})
    if AUTO_TRADE_STATE.get("disconnectAlerted"):
        AUTO_TRADE_STATE["disconnectAlerted"] = False
        _push_notification("MT5 reconnected", "Connection restored — auto-entry resumed.", "success")
    if not execution.get("liveTradingEnabled") or execution.get("dryRun", True):
        return blocked("Live Trading is OFF / Dry Run is ON.", {"execution": execution})
    if not execution.get("autoTradingEnabled"):
        return blocked("Auto Trading switch is OFF.", {"execution": execution})
    now = time.time()
    if now - float(AUTO_TRADE_STATE.get("lastFire", 0.0)) < float(AUTO_TRADE_STATE.get("cooldownSeconds", 60)):
        return blocked("Auto trading cooldown active.", {"cooldownSeconds": AUTO_TRADE_STATE.get("cooldownSeconds", 60)})
    # Loss-streak circuit breaker — after N consecutive losses, stop and force re-analysis.
    if now < float(AUTO_TRADE_STATE.get("pausedUntil", 0.0)):
        mins = (float(AUTO_TRADE_STATE["pausedUntil"]) - now) / 60
        return blocked(f"Loss-streak circuit breaker active ({AUTO_TRADE_STATE.get('lossStreak')} losses in a row). Re-analysing — auto-entry resumes in {mins:.0f} min.", {"lossStreak": AUTO_TRADE_STATE.get("lossStreak")})
    # Post-loss reanalysis cooldown — never instantly re-enter right after a loss.
    if now < float(AUTO_TRADE_STATE.get("postLossUntil", 0.0)):
        secs = float(AUTO_TRADE_STATE["postLossUntil"]) - now
        return blocked(f"Post-loss reanalysis cooldown: waiting {secs/60:.1f} min after the last losing trade before considering a new entry.", {"postLossSeconds": round(secs)})
    # Capital circuit breakers — daily realized-loss limit + equity drawdown stop.
    cb = _capital_circuit_breaker(blocked)
    if cb is not None:
        return cb
    market = _live_market()

    # Session filter: only trade during sessions selected in settings
    trading_cfg = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    allowed_sessions = trading_cfg.get("allowedSessions")
    current_session = market.get("session", "Unknown")
    if allowed_sessions and isinstance(allowed_sessions, list) and current_session not in allowed_sessions:
        return blocked(f"Session filter: '{current_session}' not in your allowed sessions {allowed_sessions}. Change in Settings → Trading Defaults.", {"session": current_session, "allowedSessions": allowed_sessions})

    # Read the actual open bot position (if any) to pass real profitR to pyramid + decision engine.
    open_positions = mt5_bridge.open_positions(bot_only=True) if mt5_bridge.status().get("connected") else []
    active_position: dict[str, Any] | None = open_positions[0] if open_positions else None

    # Compute actual profitR from the live position so the pyramid engine
    # cannot be fooled by empty/default values.
    if active_position:
        entry_p = float(active_position.get("entryPrice", 0) or 0)
        cur_p   = float(active_position.get("currentPrice", market.get("price", entry_p)) or entry_p)
        sl_p    = float(active_position.get("sl", entry_p - 10) or entry_p - 10)
        risk    = abs(entry_p - sl_p) or 1.0
        direction = str(active_position.get("direction", "BUY")).upper()
        float_r = (cur_p - entry_p) / risk if direction == "BUY" else (entry_p - cur_p) / risk
        # Populate the fields the pyramid engine gates on — otherwise winStreak=0 and
        # beMoved default block every add. beMoved/locked come from the live protection
        # loop; winStreak from the bot's recent results.
        prot = POSITION_PROTECTION_STATE.get(str(active_position.get("ticket")), {})
        be_moved = bool(prot.get("beMoved"))
        base_lot = float((SETTINGS_STATE.get("pyramiding", {}) or {}).get("baseLot") or 0.01)
        active_position = {**active_position, "profitR": round(float_r, 3), "floatingR": round(float_r, 3),
                           "beMoved": be_moved, "breakEvenProtected": be_moved,
                           "winStreak": int(AUTO_TRADE_STATE.get("winStreak", 0)),
                           "winsSinceLastLoss": int(AUTO_TRADE_STATE.get("winStreak", 0)),
                           "baseLot": base_lot, "currentLots": float(active_position.get("lots") or base_lot),
                           "lockedProfitR": round(max(0.0, float_r - 0.1), 2) if be_moved else 0.0,
                           "allPriorAddsProtected": True, "structureValid": True}

    matrix = _action_matrix(position=active_position or {}, market=market)
    decision = matrix.get("decision", {}) or {}

    # ── REPEAT-SETUP GUARD ──────────────────────────────────────────────
    # Don't immediately re-fire the SAME direction that just lost unless the market
    # has genuinely changed (price moved structurally OR the HTF bias now agrees).
    # This is the direct fix for the "5 SELLs in 72 seconds into a rally" failure:
    # after the first wrong read, the bot must wait for a DIFFERENT setup.
    auto_cfg = SETTINGS_STATE.get("automation", {}) if isinstance(SETTINGS_STATE.get("automation"), dict) else {}
    if not active_position and auto_cfg.get("blockRepeatFailedSetup", True):
        last = AUTO_TRADE_STATE.get("lastLoser")
        sig_side = str(decision.get("side", market.get("side", ""))).upper()
        if last and sig_side and sig_side == last.get("side") and (now - float(last.get("ts", 0))) < float(auto_cfg.get("repeatBlockMinutes", 20)) * 60:
            cur_price = float(market.get("price") or 0)
            moved = abs(cur_price - float(last.get("price", 0)))
            atr = float(market.get("atr14") or 8) or 8
            htf_bias = str((decision.get("features", {}) or {}).get("htfDailyBias", "")).upper()
            if moved < atr * 0.8 and htf_bias != sig_side:
                return blocked(f"Repeat-setup guard: a {sig_side} just lost and the market hasn't changed (moved {moved:.2f} < 0.8 ATR, HTF bias {htf_bias or 'neutral'}). Waiting for a genuinely different setup instead of re-entering the failed idea.", {"repeatGuard": True})

    # ── HEDGE / SCALP MODE ──────────────────────────────────────────────
    # On a RETAIL_HEDGING account, a fresh HIGH-QUALITY setup alongside an open trade
    # can be taken as an INDEPENDENT scalp (not a pyramid add) — with the same strict
    # BE/trail/fast-fail protection. Gated on account type so it can never net-off.
    scalp_mode = False
    if active_position and auto_cfg.get("scalpHedgeEnabled") and mt5_bridge.is_hedging():
        q = str(decision.get("quality", "")).upper()
        min_q = str(auto_cfg.get("scalpMinQuality", "STANDARD")).upper()
        allowed_q = {"SNIPER"} if min_q == "SNIPER" else {"STANDARD", "SNIPER"}
        if len(open_positions) < int(auto_cfg.get("scalpMaxConcurrent", 2)) and q in allowed_q:
            scalp_mode = True  # take it as a new independent position, skip the pyramid path

    # ── PYRAMID SAFETY GATE ─────────────────────────────────────────────
    # If a bot position is already open (and we're NOT scalping), ANY new order is a
    # pyramid ADD. It only fires when the existing trade is PROVEN in profit AND the
    # pyramid engine approves — never stacking adds into a loser.
    is_pyramid_add = bool(active_position) and not scalp_mode
    if is_pyramid_add:
        profit_r = float(active_position.get("profitR", 0) or 0)
        pyr = matrix.get("pyramiding", {}) if isinstance(matrix.get("pyramiding"), dict) else {}
        pyr_settings = SETTINGS_STATE.get("pyramiding", {}) if isinstance(SETTINGS_STATE.get("pyramiding"), dict) else {}
        min_profit_r = float(pyr_settings.get("minProfitRToAdd", 0.75) or 0.75)
        # Same-direction check: only add in the direction of the open trade
        open_dir = str(active_position.get("direction", "")).upper()
        sig_dir = str(decision.get("side", market.get("side", ""))).upper()
        if profit_r < min_profit_r:
            return blocked(f"Pyramid add BLOCKED: open trade only at {profit_r:.2f}R (needs ≥{min_profit_r:.2f}R proven profit). No adds on flat/losing positions.", {"actionMatrix": matrix, "profitR": profit_r})
        if open_dir and sig_dir and open_dir != sig_dir:
            return blocked(f"Pyramid add BLOCKED: signal {sig_dir} opposes open {open_dir} position. No counter-direction adds.", {"actionMatrix": matrix})
        if not matrix.get("pyramidOnlyIfProven"):
            reasons = (pyr.get("blocks") or matrix.get("blockedReasons") or ["Pyramid engine did not approve this add."])
            return blocked("Pyramid add BLOCKED: " + "; ".join(str(x) for x in reasons[:3]), {"actionMatrix": matrix})

    if not matrix.get("takeThisTrade"):
        reasons = matrix.get("blockedReasons") or decision.get("decisionBlocks") or ["AI action matrix did not approve a trade."]
        msg = "WAIT/BLOCKED: " + "; ".join(str(x) for x in reasons[:3])
        return blocked(msg, {"actionMatrix": matrix, "market": {"symbol": market.get("symbol"), "price": market.get("price"), "session": market.get("session")}})

    quality   = str(decision.get("quality", "STANDARD")).upper()
    base_lot  = float((SETTINGS_STATE.get("pyramiding", {}) or {}).get("baseLot") or 0.01)
    # Stamp the REAL selected strategy into the comment (not just the entry type) so
    # closed-trade history, analytics and learning attribute to the right strategy.
    strategy_name = (decision.get("selectedStrategy", {}) or {}).get("name")
    entry_type = "scalp" if scalp_mode else ("pyramid" if is_pyramid_add else ("scout" if quality == "SCOUT" else "auto"))
    _entry_comment = comment_for(strategy_name, entry_type, mt5_bridge.comment_prefix)
    plan = decision.get("tradePlan", {}) if isinstance(decision.get("tradePlan"), dict) else {}
    _extra = {"comment": _entry_comment, "manualTrigger": False}
    # First entries carry the REAL structural SL + a broker TP at TP4 (4R) as a backstop.
    # The management loop takes TP1-TP3 partials and trails the runner out before then —
    # putting the broker TP at TP2 (the old behaviour) was CLOSING trades at 1.8R and
    # starving both trailing and pyramiding of room to work.
    if not is_pyramid_add:
        if plan.get("sl"):
            _extra["sl"] = plan.get("sl")
        if plan.get("tp4"):
            _extra["tp"] = plan.get("tp4")
    payload = _order_payload_from_market(_extra)
    # ── Volatility-normalized BASE lot: size so the trade risks ~riskPerTrade% of equity given
    # the REAL stop distance (constant dollar risk across calm vs volatile/wide-stop regimes).
    # The win-streak ladder then rides ON TOP of this risk-based base. Pyramid ADDs keep the
    # engine's own protected add-sizing.
    vbase = base_lot
    vol_info: dict[str, Any] | None = None
    if auto_cfg.get("volNormalizedSizing", True) and not is_pyramid_add and _extra.get("sl"):
        entry_px = float(payload.get("price") or market.get("price") or 0)
        vol_info = _volatility_normalized_base_lot(payload.get("symbol", symbol), entry_px, float(_extra["sl"]), base_lot)
        vbase = float(vol_info.get("lot") or base_lot)
    if is_pyramid_add:
        # Protected pyramid ADD sizing (adds to an OPEN position) — engine's next add lot.
        pyr = matrix.get("pyramiding", {}) if isinstance(matrix.get("pyramiding"), dict) else {}
        next_lot = float((pyr.get("nextAdd") or {}).get("lot") or pyr.get("nextLot") or base_lot)
        payload["volume"] = max(base_lot, next_lot)
    elif quality == "SCOUT":
        payload["volume"] = vbase   # scout = reduced-quality entry; risk-based base lot
        payload["scoutEntry"] = True
    elif auto_cfg.get("winStreakLotScaling", True):
        # WIN-STREAK LOT LADDER (per NEW trade): first trade = (risk-based) base lot; each
        # consecutive win scales the next trade by lotStep up to maxLot; any loss resets to base.
        pyr_set = SETTINGS_STATE.get("pyramiding", {}) if isinstance(SETTINGS_STATE.get("pyramiding"), dict) else {}
        lot_step = float(pyr_set.get("lotStep") or 0.01)
        max_lot = float(pyr_set.get("maxLot") or 0.05)
        ws = int(AUTO_TRADE_STATE.get("winStreak", 0))
        if vol_info is not None and vbase > max_lot + 1e-9:
            vol_info["maxLotCapped"] = True   # risk-based size exceeds the Max Lot ceiling
        payload["volume"] = round(min(max_lot, vbase + lot_step * ws), 2)
    else:
        payload["volume"] = vbase
    result = mt5_bridge.execute(payload)
    if result.get("ok"):
        AUTO_TRADE_STATE["lastFire"] = now
        _capture_entry_context(result, decision, payload, entry_type, strategy_name)
        result["event"] = _notify_trade_event("auto_trade", result, payload)
    wrapped = {"ok": bool(result.get("ok")), "reason": reason, "message": result.get("message", "Auto trade evaluated."), "quality": quality, "scoutEntry": quality == "SCOUT", "actionMatrix": matrix, "execution": result, "event": result.get("event"), "sizing": vol_info}
    wrapped["heartbeat"] = _record_auto_heartbeat(wrapped)
    return wrapped


@app.get("/api/notifications")
def notifications():
    unread = sum(1 for n in NOTIFICATIONS if not n.get("read"))
    return {"ok": True, "unread": unread, "items": NOTIFICATIONS[:30]}


@app.post("/api/notifications/clear")
def clear_notifications():
    for n in NOTIFICATIONS:
        n["read"] = True
    return {"ok": True, "unread": 0, "items": NOTIFICATIONS[:30]}


@app.get("/api/all")
def all_data():
    return {"status": status(), "account": account(), "market": market_snapshot(), "signals": signals(), "strategies": list(STRATEGIES_STATE.values()), "trades": trades(), "risk": risk(), "analytics": analytics(), "journal": journal(), "settings": settings()}


@app.post("/api/trades/execute")
def execute_trade(payload: dict[str, Any] = Body(...)):
    if kill_switch.status().get("active"):
        return {"ok": False, "blocked": True, "message": "Emergency kill switch is active."}
    if payload.get("requireAiApproval", True):
        matrix = _action_matrix(position=payload.get("position") or {}, market=payload.get("market") or _live_market())
        if not matrix.get("takeThisTrade") and not payload.get("manualOverride", False):
            return {"ok": False, "blocked": True, "message": "AI approval gate blocked execution.", "actionMatrix": matrix}
    payload.setdefault("source", "godmode_bot")
    payload.setdefault("magic", mt5_bridge.magic)
    if payload.get("manualOverride") or payload.get("manualTrigger"):
        payload["manualTrigger"] = True
    # Tag the order with the live AI-selected strategy so it is attributable later.
    _decision_now = _decision()
    _strategy_now = (_decision_now.get("selectedStrategy", {}) or {}).get("name")
    _etype = "signal" if "signal" in str(payload.get("comment", "")).lower() else "execute"
    payload["comment"] = comment_for(_strategy_now, _etype, mt5_bridge.comment_prefix)
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        result = _demo_execute(payload)
    else:
        result = mt5_bridge.execute(payload)
    if result.get("ok"):
        _capture_entry_context(result, _decision_now, payload, _etype, _strategy_now)
    result["event"] = _notify_trade_event("execute_trade", result, payload)
    return result


def _demo_execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Demo execution — does NOT add to closed history (trade hasn't closed yet)."""
    market = demo_data.market_snapshot()
    side = str(payload.get("side") or payload.get("direction") or market.get("side") or "BUY").upper()
    ticket = int(time.time())
    return {
        "ok": True,
        "dryRun": True,
        "demo": True,
        "message": f"Demo: {side} XAUUSD {payload.get('volume', 0.01)} lots at {market.get('price')}. (Not added to history until closed.)",
        "ticket": ticket,
        "request": {
            "symbol": payload.get("symbol", "XAUUSD"),
            "side": side,
            "volume": payload.get("volume") or payload.get("lots") or 0.01,
            "price": market.get("price"),
        },
    }



@app.post("/api/trades/manual-trigger")
def manual_trade_trigger(payload: dict[str, Any] = Body(default={})):
    if kill_switch.status().get("active"):
        return {"ok": False, "blocked": True, "message": "Emergency kill switch is active."}
    order_payload = _order_payload_from_market(payload)
    order_payload["manualOverride"] = True
    order_payload["manualTrigger"] = True
    order_payload["requireAiApproval"] = False
    _decision_now = _decision()
    _strategy_now = (_decision_now.get("selectedStrategy", {}) or {}).get("name") or "Manual Trade"
    order_payload["comment"] = comment_for(_strategy_now, "manual", mt5_bridge.comment_prefix)
    if not mt5_bridge.status().get("connected") and _demo_enabled():
        result = _demo_execute(order_payload)
    else:
        result = mt5_bridge.execute(order_payload)
    if result.get("ok"):
        _capture_entry_context(result, _decision_now, order_payload, "manual", _strategy_now)
    result["event"] = _notify_trade_event("manual_trade", result, order_payload)
    return result

@app.get("/api/auto-trading/status")
def auto_trading_status():
    return {"ok": True, "state": AUTO_TRADE_STATE, "heartbeat": AUTO_TRADE_HEARTBEAT[:20], "mt5": mt5_bridge.status(), "settings": _safe_public_settings(SETTINGS_STATE).get("execution", {}), "strictness": decision_engine.strictness_dict()}

@app.get("/api/auto-trading/heartbeat")
def auto_trading_heartbeat():
    return {"ok": True, "items": AUTO_TRADE_HEARTBEAT[:50], "lastResult": AUTO_TRADE_STATE.get("lastResult"), "strictness": decision_engine.strictness_dict()}

@app.post("/api/auto-trading/tick")
def auto_trading_tick(payload: dict[str, Any] = Body(default={})):
    result = _auto_trade_tick(reason=str(payload.get("reason", "ui_manual_tick")))
    AUTO_TRADE_STATE["lastResult"] = result
    return result

@app.post("/api/trades/close")
def close_trade(payload: dict[str, Any] = Body(...)):
    result = mt5_bridge.close_position(payload)
    _cache_close_event_with_ts(payload, result)
    if result.get("ok"):
        _register_close_outcome(payload.get("ticket") or payload.get("position"), payload.get("pnlUsd"),
                                payload.get("direction") or payload.get("side"),
                                payload.get("currentPrice") or payload.get("exitPrice"))
        result["event"] = _notify_trade_event("close_trade", result, payload)
    return result


@app.post("/api/trades/modify")
def modify_trade(payload: dict[str, Any] = Body(...)):
    result = mt5_bridge.modify_position(payload)
    if result.get("ok"):
        result["event"] = _push_notification("Trade modified", result.get("message", "SL/TP modification processed."), "success", payload)
    return result


@app.post("/api/settings")
def update_settings(payload: dict[str, Any] = Body(...)):
    _deep_merge(SETTINGS_STATE, payload)
    SETTINGS_STATE.setdefault("meta", {})["lastSaved"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if isinstance(payload.get("pyramiding"), dict):
        pyramiding_engine.update_settings(payload["pyramiding"])
    if isinstance(payload.get("dataFeeds"), dict):
        _apply_data_feed_env()   # live macro/news feed URLs take effect immediately
    _apply_runtime_settings()
    _save_settings()
    SETTINGS_STATE["mt5"] = mt5_bridge.status()
    return {"ok": True, "settings": _safe_public_settings(SETTINGS_STATE)}


@app.post("/api/strategy/enable")
def enable_strategy(payload: StrategyToggle):
    if payload.id in STRATEGIES_STATE:
        STRATEGIES_STATE[payload.id]["enabled"] = True
        return {"ok": True, "strategy": STRATEGIES_STATE[payload.id]}
    return {"ok": False, "message": "Strategy not found"}


@app.post("/api/strategy/disable")
def disable_strategy(payload: StrategyToggle):
    if payload.id in STRATEGIES_STATE:
        STRATEGIES_STATE[payload.id]["enabled"] = False
        return {"ok": True, "strategy": STRATEGIES_STATE[payload.id]}
    return {"ok": False, "message": "Strategy not found"}


@app.post("/api/strategy/configure")
def configure_strategy(payload: dict[str, Any] = Body(...)):
    sid = str(payload.get("id", ""))
    if sid not in STRATEGIES_STATE:
        return {"ok": False, "message": "Strategy not found"}
    allowed = {"enabled", "minConfidence", "riskMultiplier", "session", "notes", "maxSpread", "timeframe"}
    config = {k: v for k, v in payload.items() if k in allowed}
    STRATEGIES_STATE[sid].setdefault("config", {}).update(config)
    if "enabled" in config:
        STRATEGIES_STATE[sid]["enabled"] = bool(config["enabled"])
    return {"ok": True, "strategy": STRATEGIES_STATE[sid]}


@app.post("/api/risk/update")
def update_risk(payload: dict[str, Any] = Body(...)):
    # Accept either flat limit keys (maxDailyLossPct, ...) or a {rule, limit, enabled}
    # row from the Risk Rules Editor. Both persist so edits take effect after save.
    rule_name = payload.get("rule") or payload.get("title")
    if rule_name and ("limit" in payload or "enabled" in payload or "main" in payload):
        rules = RISK_STATE.setdefault("rules", {})
        rules[str(rule_name)] = {
            "limit": payload.get("limit", payload.get("main")),
            "enabled": bool(payload.get("enabled", True)),
        }
        # Map well-known rules onto the structured limits so the cards update too.
        limit_val = payload.get("limit") or payload.get("main") or ""
        num = _first_number(str(limit_val))
        key_map = {
            "Max Daily Loss": "maxDailyLossPct",
            "Max Drawdown": "maxDrawdownPct",
            "Drawdown Guard": "maxDrawdownPct",
            "Max Risk Per Trade": "maxRiskPerTradePct",
            "Max Open Risk": "maxOpenRiskPct",
            "Open Risk": "maxOpenRiskPct",
            "Max Exposure": "maxExposurePct",
            "Loss Streak Limit": "lossStreakLimit",
            "Circuit Breaker": "circuitBreakerPct",
        }
        mapped = key_map.get(str(rule_name))
        if mapped and num is not None:
            RISK_STATE[mapped] = num
    else:
        for k, v in payload.items():
            RISK_STATE[k] = v
    _save_risk()
    return {"ok": True, "risk": RISK_STATE, "limits": _risk_limits_view(), "message": f"Risk rule saved: {rule_name or 'limits updated'}."}


@app.get("/api/market/intelligence")
def market_intelligence():
    m = _live_market()
    cal = calendar.blackout_status()
    return {"economicCalendar": cal, "macroAwareness": macro.snapshot(), "volatilityRegime": volatility.classify(m.get("candles"), m.get("atr14")), "marketCleanliness": cleanliness.evaluate(m, cal)}


@app.get("/api/calendar/economic")
def economic_calendar():
    return {"events": calendar.events(), "blackout": calendar.blackout_status()}


@app.get("/api/macro/gold-context")
def macro_gold_context():
    return macro.snapshot()


@app.get("/api/market/volatility-regime")
def volatility_regime():
    m = _live_market()
    return volatility.classify(m.get("candles"), m.get("atr14"))


@app.get("/api/news/blackout")
def news_blackout():
    return calendar.blackout_status()


@app.get("/api/memory/performance")
def performance_memory():
    return memory.stats()


@app.post("/api/memory/record-trade")
def record_trade(payload: dict[str, Any] = Body(...)):
    return memory.record_trade(payload)


@app.post("/api/journal/auto")
def auto_journal(payload: dict[str, Any] = Body(...)):
    return memory.auto_journal(str(payload.get("event", "AUTO_JOURNAL")), str(payload.get("detail", "")), str(payload))


@app.post("/api/backtest/walk-forward")
def backtest_walk_forward(payload: dict[str, Any] = Body(default={})):
    return walk_forward.run(payload)


def _backtest_params(payload: dict[str, Any]) -> dict[str, Any]:
    trading = SETTINGS_STATE.get("trading", {}) if isinstance(SETTINGS_STATE.get("trading"), dict) else {}
    return {**payload, "symbol": trading.get("symbol", "XAUUSD"),
            "allowedSessions": trading.get("allowedSessions")}


@app.post("/api/backtest/run")
def backtest_run(payload: dict[str, Any] = Body(default={})):
    """Cost-aware walk-forward replay of the real decision engine over history.
    Returns per-strategy edge (expectancy R, profit factor, win rate, DD) + verdicts."""
    candles = _backtest_candles(int(payload.get("bars", 4000)))
    res = backtester.run(candles, decision_engine, list(STRATEGIES_STATE.values()), _backtest_params(payload))
    res["dataSource"] = "mt5_history" if mt5_bridge.status().get("connected") else "synthetic_demo"
    if res.get("dataSource") == "synthetic_demo":
        res["note"] = "Synthetic candles (MT5 not connected) — numbers are illustrative. Connect MT5 for a real edge measurement."
    return res


def _validate_impl(payload: dict[str, Any], progress: Any = None) -> dict[str, Any]:
    connected = bool(mt5_bridge.status().get("connected"))
    tf = str(payload.get("timeframe") or (SETTINGS_STATE.get("trading") or {}).get("timeframe") or "M15").upper()
    candles = _backtest_candles(int(payload.get("bars") or _tf_default_bars(tf)), tf)   # ~2 yrs at this TF
    params = _backtest_params({"spread": 0.25, "commission": 0.07, "minSample": 40, "folds": 6, **payload})
    res = backtester.run(candles, decision_engine, list(STRATEGIES_STATE.values()), params, progress=progress)
    if not res.get("ok"):
        return res
    a = res.get("assessment", {}) or {}
    o = res.get("overall", {}) or {}
    edge = a.get("edge", "none")
    n = int(res.get("totalTrades", 0) or 0)
    if not connected:
        decision, head = "NO-GO (test data)", "Ran on SYNTHETIC data — MT5 not connected. Connect MT5 and re-run for a real verdict."
    elif n < 40:
        decision, head = "INCONCLUSIVE", f"Only {n} trades over {res.get('span','')} — load more history (scroll your M15 chart far back so the terminal caches it) and re-run."
    elif edge == "strong":
        decision, head = "GO (demo-forward first)", "Positive expectancy after costs with consistent walk-forward folds."
    elif edge == "marginal":
        decision, head = "CAUTION", "Barely above costs / inconsistent folds — refine (disable DISABLE-verdict strategies, tighten filters) before sizing up."
    else:
        decision, head = "NO-GO", "No reliable edge after costs as configured — do not trade live as-is."
    res["timeframe"] = tf
    res["validation"] = {
        "decision": decision, "headline": head, "timeframe": tf,
        "dataSource": "mt5_history" if connected else "synthetic_demo",
        "expectancyR": o.get("expectancyR"), "profitFactor": o.get("profitFactor"),
        "winRatePct": o.get("winRate"), "maxDrawdownR": o.get("maxDrawdownR"),
        "trades": n, "span": res.get("span"), "oosConsistencyPct": res.get("oosConsistencyPct"),
        "checklist": [
            "1) Validate on real MT5 history here — a GO needs positive expectancy AND consistent folds.",
            "2) Forward-test on a DEMO account 2–4 weeks before any real money.",
            "3) Start live at the minimum risk % and scale ONLY after live results match the backtest.",
            "Note: the backtest is deliberately conservative (SL-before-TP within a bar, no exit slippage, news not modeled).",
        ],
    }
    res["dataSource"] = res["validation"]["dataSource"]
    return res


@app.post("/api/backtest/validate")
def backtest_validate(payload: dict[str, Any] = Body(default={})):
    return _validate_impl(payload)


# ── Background jobs (so long backtests run without freezing the page, with a progress bar) ──
JOBS: dict[str, dict[str, Any]] = {}


def _new_job(kind: str) -> str:
    jid = f"{kind}-{int(time.time() * 1000)}"
    JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "progress": 0, "stage": "Starting…",
                 "startedAt": time.time(), "result": None, "message": "", "etaSeconds": None}
    for old in sorted(JOBS, key=lambda k: JOBS[k]["startedAt"])[:-20]:   # keep last 20
        JOBS.pop(old, None)
    return jid


class _JobCancelled(Exception):
    """Raised inside a worker's progress callback when the user clicks Stop."""


def _job_progress(jid: str):
    def cb(frac: float, stage: str) -> None:
        j = JOBS.get(jid)
        if not j:
            return
        if j.get("cancelRequested"):
            raise _JobCancelled()   # checked on every progress tick → Stop takes effect within ~1 step
        j["progress"] = int(max(0, min(100, frac * 100)))
        j["stage"] = stage
        el = time.time() - j["startedAt"]
        j["etaSeconds"] = round(el * (1 - frac) / frac) if frac > 0.03 else None
    return cb


def _run_job(jid: str, fn) -> None:
    def worker():
        try:
            res = fn(_job_progress(jid))
            j = JOBS.get(jid)
            if j:
                j.update(status="done", progress=100, stage="Done", result=res, finishedAt=time.time(), etaSeconds=0)
        except _JobCancelled:
            j = JOBS.get(jid)
            if j:
                j.update(status="cancelled", stage="Stopped by you", message="Stopped by user.", finishedAt=time.time(), etaSeconds=0)
        except Exception as exc:
            j = JOBS.get(jid)
            if j:
                j.update(status="error", message=str(exc), stage="Error")
    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    j = JOBS.get(jid)
    if not j:
        return {"ok": False, "message": "Unknown or expired job."}
    return {"ok": True, **{k: v for k, v in j.items() if k != "result"},
            "result": j["result"] if j["status"] == "done" else None}


@app.post("/api/jobs/{jid}/cancel")
def job_cancel(jid: str):
    """Request a running job to stop. The worker's next progress tick raises and ends it cleanly."""
    j = JOBS.get(jid)
    if not j:
        return {"ok": False, "message": "Unknown or expired job."}
    if j.get("status") == "running":
        j["cancelRequested"] = True
        j["stage"] = "Stopping…"
    return {"ok": True, "status": j.get("status")}


@app.post("/api/backtest/validate-async")
def backtest_validate_async(payload: dict[str, Any] = Body(default={})):
    jid = _new_job("validate")
    def fn(prog):
        r = _validate_impl(payload, prog)
        if isinstance(r, dict) and r.get("ok"):
            BACKTEST_STATE.update(lastRun=time.time(), lastValidation=r, lastResult=r)
        return r
    _run_job(jid, fn)
    return {"ok": True, "jobId": jid}


@app.post("/api/backtest/run-async")
def backtest_run_async(payload: dict[str, Any] = Body(default={})):
    jid = _new_job("backtest")
    def fn(prog):
        tf = str(payload.get("timeframe") or (SETTINGS_STATE.get("trading") or {}).get("timeframe") or "M15").upper()
        candles = _backtest_candles(int(payload.get("bars", 4000)), tf)
        r = backtester.run(candles, decision_engine, list(STRATEGIES_STATE.values()), _backtest_params(payload), progress=prog)
        r["timeframe"] = tf
        r["dataSource"] = "mt5_history" if mt5_bridge.status().get("connected") else "synthetic_demo"
        if r.get("dataSource") == "synthetic_demo":
            r["note"] = "Synthetic candles (MT5 not connected) — numbers are illustrative. Connect MT5 for a real edge measurement."
        if isinstance(r, dict) and r.get("ok"):
            BACKTEST_STATE.update(lastRun=time.time(), lastResult=r)
        return r
    _run_job(jid, fn)
    return {"ok": True, "jobId": jid}


@app.get("/api/backtest/last")
def backtest_last():
    """The most recent Backtest / Validate result, so the Backtest tab can restore it after you
    click away or reload — the same persistence the Strategy Lab uses."""
    return {"ok": True, "lastRun": BACKTEST_STATE.get("lastRun"),
            "result": BACKTEST_STATE.get("lastResult"),
            "validation": BACKTEST_STATE.get("lastValidation")}


@app.post("/api/lab/run-async")
def lab_run_async(payload: dict[str, Any] = Body(default={})):
    jid = _new_job("lab")
    def fn(prog):
        res = _run_strategy_lab(int(payload.get("bars", 60000)), progress=prog)
        _alert_lab_recommendation(res)
        return res
    _run_job(jid, fn)
    return {"ok": True, "jobId": jid}


@app.post("/api/backtest/optimize-weights")
def backtest_optimize_weights(payload: dict[str, Any] = Body(default={})):
    """Fit confidence-factor weights from cost-adjusted backtest outcomes, validate
    out-of-sample, and (if apply=true and OOS improved) persist + apply them live."""
    candles = _backtest_candles(int(payload.get("bars", 5000)))
    res = backtester.optimize_weights(candles, decision_engine, list(STRATEGIES_STATE.values()), _backtest_params(payload))
    res["dataSource"] = "mt5_history" if mt5_bridge.status().get("connected") else "synthetic_demo"
    if res.get("ok") and payload.get("apply") and res.get("learnedWeights"):
        if res.get("outOfSample", {}).get("improved") or payload.get("force"):
            decision_engine.set_factor_weights(res["learnedWeights"])
            _save_factor_weights(res["learnedWeights"])
            res["applied"] = True
            res["message"] = "Learned factor weights applied and persisted."
        else:
            res["applied"] = False
            res["message"] = "Not applied: out-of-sample did not improve. Re-run with force=true to override."
    return res


@app.get("/api/backtest/weights")
def backtest_weights():
    return {"ok": True, "applied": decision_engine.factor_weights, "usingDefaults": not decision_engine.factor_weights}


@app.post("/api/backtest/weights/reset")
def backtest_weights_reset():
    decision_engine.reset_factor_weights()
    try:
        FACTOR_WEIGHTS_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "message": "Reverted to default hand-set factor weights."}


# ── AI Strategy Lab ──────────────────────────────────────────────────────────────────────
def _refresh_strategy_feed() -> int:
    """Pull candidate profiles from the trusted strategy-feed URL (if configured) into the pool."""
    cfg = SETTINGS_STATE.get("strategyLab", {}) if isinstance(SETTINGS_STATE.get("strategyLab"), dict) else {}
    url = str(cfg.get("feedUrl", "") or "").strip()
    if not url:
        return 0
    res = ai_strategy_gen.fetch_feed_candidates(url, str(cfg.get("feedKey", "") or ""))
    return strategy_lab.add_candidates(res.get("candidates", [])) if res.get("ok") else 0


def _run_strategy_lab(bars: int = 60000, progress: Any = None) -> dict[str, Any]:
    """Back-/forward-test every candidate trading style + the live baseline over your history."""
    _refresh_strategy_feed()   # pull any trusted-feed candidates before testing
    connected = bool(mt5_bridge.status().get("connected"))
    candles = _backtest_candles(bars)
    lab_cfg = SETTINGS_STATE.get("strategyLab", {}) if isinstance(SETTINGS_STATE.get("strategyLab"), dict) else {}
    params = _backtest_params({"spread": 0.25, "commission": 0.07, "minSample": 30, "folds": 6,
                               "improveMarginR": float(lab_cfg.get("improveMarginR", 0.05) or 0.05),
                               "dataSource": "mt5_history" if connected else "synthetic_demo"})
    baseline = decision_engine.strictness_dict()
    res = strategy_lab.evaluate(candles, decision_engine, list(STRATEGIES_STATE.values()), backtester, baseline, params, progress=progress)
    res["dataSource"] = params["dataSource"]
    LAB_STATE["lastRun"] = time.time()
    LAB_STATE["lastResult"] = res
    return res


@app.get("/api/lab/candidates")
def lab_candidates():
    return {"ok": True, "candidates": strategy_lab.candidates(), "installed": LAB_STATE.get("installedProfile")}


def _alert_lab_recommendation(res: dict[str, Any]) -> None:
    """Fire the notification + top-bar + sound + Telegram alert when the lab finds a NEW better
    candidate (deduped by signature so the same recommendation doesn't re-alert)."""
    rec = res.get("recommendation")
    if rec and res.get("signature") != LAB_STATE.get("lastRecSig"):
        LAB_STATE["lastRecSig"] = res.get("signature")
        _push_notification("AI found a better strategy", f"{rec['name']}: {rec['why'][:150]} Review & install in Analytics → Strategy Lab.", "success", {"sound": True, "strategyLab": True})
        tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
        if tg.get("enabled"):
            _telegram_send_text(f"🧠 *GodMode — better strategy found*\n*{rec['name']}*\n{rec['why']}\n\nReview the back/forward test and install it in the dashboard → Analytics → Strategy Lab.")


def _auto_discover_strategy() -> None:
    """Auto-pilot: when NO enabled strategy fits the current market, run the Lab, auto-install the best
    candidate that beats your edge out-of-sample, and alert Telegram with Uninstall/Keep buttons.
    OPT-IN (strategyLab.autoDiscover). Heavily guarded: never during a news blackout, never stacks a
    second install, cooldown-throttled, and only installs a candidate the Lab VALIDATES — so it can
    inform you and save a missed trade WITHOUT ever forcing a losing chop trade."""
    lab_cfg = SETTINGS_STATE.get("strategyLab", {}) if isinstance(SETTINGS_STATE.get("strategyLab"), dict) else {}
    if not lab_cfg.get("autoDiscover"):
        return
    if not mt5_bridge.status().get("connected") or not _market_state().get("open", True):
        return
    if LAB_STATE.get("installedProfile"):
        return  # a discovered strategy is already active — don't stack a second one
    cooldown = float(lab_cfg.get("autoDiscoverCooldownMin", 60) or 60) * 60
    now = time.time()
    if now - float(RECAP_STATE.get("lastAutoDiscover", 0) or 0) < cooldown:
        return
    try:
        dec = _decision()
    except Exception:
        return
    if str(dec.get("action")) == "TAKE_TRADE":
        return  # a strategy already fits — nothing to discover
    if (dec.get("economicCalendar") or {}).get("isBlackout"):
        return  # news blackout — correct to wait
    evals = dec.get("strategyEvaluations") or []
    if evals and any(e.get("passes") for e in evals):
        return  # some strategy already passes — not a fit problem
    RECAP_STATE["lastAutoDiscover"] = now
    res = _run_strategy_lab(60000)
    rec = res.get("recommendation")
    if not rec:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if RECAP_STATE.get("lastAutoDiscoverNone") != today:
            RECAP_STATE["lastAutoDiscoverNone"] = today
            _telegram_send_text("🔎 *GodMode — auto-scan*\nNo strategy fits the current market, so I scanned the "
                                "Strategy Lab. *Nothing beats your current edge out-of-sample right now*, so I'm "
                                "staying flat (correct — no forced trades). I'll keep watching and alert you the "
                                "moment a validated strategy fits.")
        return
    inst = lab_install({"id": rec["id"]})
    if not inst.get("ok"):
        return
    why = str(rec.get("why", ""))[:320]
    _push_notification("Auto-installed a fitting strategy", f"{rec['name']}: {why}", "success", {"sound": True, "strategyLab": True})
    _telegram_send_text(
        f"🤖 *GodMode — auto-installed a fitting strategy*\n*{rec['name']}*\n{why}\n\n"
        f"It now competes in your rotation with its OWN entry gates (your global config is untouched), so "
        f"you don't miss the setup while you're busy. Tap below to manage it:",
        buttons=[[{"text": "↩️ Uninstall", "callback_data": "gm_lab_uninstall"},
                  {"text": "✅ Keep", "callback_data": "gm_lab_keep"}]])


async def _telegram_command_loop() -> None:
    """Poll Telegram for button taps / commands so you can Uninstall or Keep an auto-installed strategy
    straight from your phone. Short-poll (~12s); no webhook, nothing exposed to the internet. Telegram-
    only and resilient — any error just retries. Handles the auto-discover Uninstall/Keep buttons and the
    /uninstall and /keep text commands as a fallback."""
    while True:
        try:
            tg = SETTINGS_STATE.get("telegram", {}) if isinstance(SETTINGS_STATE.get("telegram"), dict) else {}
            token, _chat = _telegram_creds()
            if not tg.get("enabled") or not token:
                await asyncio.sleep(20); continue
            offset = int(RECAP_STATE.get("tgUpdateOffset", 0) or 0)
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=0&offset={offset}&allowed_updates=%5B%22message%22%2C%22callback_query%22%5D"
            def _fetch() -> dict[str, Any]:
                with urllib.request.urlopen(url, timeout=12) as r:
                    return json.loads(r.read().decode("utf-8", "ignore"))
            data = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            for upd in data.get("result", []) if isinstance(data, dict) else []:
                RECAP_STATE["tgUpdateOffset"] = int(upd.get("update_id", offset)) + 1
                cb = upd.get("callback_query") or {}
                msg = upd.get("message") or {}
                action, cb_id = None, cb.get("id")
                if cb:
                    action = str(cb.get("data") or "")
                elif isinstance(msg.get("text"), str):
                    t = msg["text"].strip().lower()
                    if t in ("/uninstall", "/uninstall_lab", "uninstall"):
                        action = "gm_lab_uninstall"
                    elif t in ("/keep", "/skip", "keep"):
                        action = "gm_lab_keep"
                if action == "gm_lab_uninstall":
                    r = lab_uninstall({})
                    _telegram_send_text("↩️ *Uninstalled.* " + str(r.get("message", "Removed the auto-installed strategy from your rotation.")))
                elif action == "gm_lab_keep":
                    _telegram_send_text("✅ *Kept.* The strategy stays in your rotation with its own gates. Remove it any time in the app or with /uninstall.")
                if cb_id:
                    try:
                        ack = urllib.parse.urlencode({"callback_query_id": cb_id}).encode()
                        await asyncio.get_event_loop().run_in_executor(None, lambda: urllib.request.urlopen(
                            urllib.request.Request(f"https://api.telegram.org/bot{token}/answerCallbackQuery", data=ack, method="POST"), timeout=8).read())
                    except Exception:
                        pass
            await asyncio.sleep(12)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(20)


@app.post("/api/lab/run")
def lab_run(payload: dict[str, Any] = Body(default={})):
    """Run the lab now. If a candidate genuinely beats your live config out-of-sample, raise a
    notification + top-bar + sound + Telegram alert prompting you to review & install it."""
    res = _run_strategy_lab(int(payload.get("bars", 60000)))
    _alert_lab_recommendation(res)
    return res


@app.post("/api/lab/fetch-feed")
def lab_fetch_feed():
    """Pull candidate profiles from the trusted strategy-feed URL now (Settings → Strategy Lab)."""
    cfg = SETTINGS_STATE.get("strategyLab", {}) if isinstance(SETTINGS_STATE.get("strategyLab"), dict) else {}
    url = str(cfg.get("feedUrl", "") or "").strip()
    if not url:
        return {"ok": False, "message": "No strategy feed URL set. Add one in Settings → Strategy Lab."}
    res = ai_strategy_gen.fetch_feed_candidates(url, str(cfg.get("feedKey", "") or ""))
    if res.get("ok"):
        res["added"] = strategy_lab.add_candidates(res.get("candidates", []))
        res["total"] = len(strategy_lab.candidates())
        res["message"] = f"Feed returned {res.get('acceptedCount', 0)} valid candidate(s); {res['added']} added. Run the lab to test them."
    return res


@app.get("/api/lab/status")
def lab_status():
    return {"ok": True, "lastRun": LAB_STATE.get("lastRun"), "result": LAB_STATE.get("lastResult"),
            "installed": LAB_STATE.get("installedProfile")}


@app.post("/api/lab/add-candidates")
def lab_add_candidates(payload: dict[str, Any] = Body(default={})):
    """Append externally-sourced candidate PROFILES (trusted feed / AI generator) — rule-specs of
    the same shape as the library, never executable code. They then get backtested like any other."""
    items = payload.get("candidates") or payload.get("items") or []
    n = strategy_lab.add_candidates(items if isinstance(items, list) else [])
    return {"ok": True, "added": n, "total": len(strategy_lab.candidates())}


@app.post("/api/lab/generate")
def lab_generate(payload: dict[str, Any] = Body(default={})):
    """Ask the configured LLM (Claude or ChatGPT) to PROPOSE new candidate style profiles, validate
    + clamp them to the safe schema, and add them to the Strategy Lab pool (they then get backtested
    like any other candidate — nothing trades until you run the lab and click Install)."""
    cfg = SETTINGS_STATE.get("aiProvider", {}) if isinstance(SETTINGS_STATE.get("aiProvider"), dict) else {}
    if not cfg.get("enabled"):
        return {"ok": False, "message": "AI Strategy Generator is OFF. Enable it and add an API key in Settings → AI Strategy Generator."}
    provider = str(payload.get("provider") or cfg.get("provider", "claude"))
    api_key = str(cfg.get("apiKey", "") or "")
    model = str(payload.get("model") or cfg.get("model", "") or "")
    n = int(payload.get("n") or cfg.get("candidatesPerRun", 3) or 3)
    try:
        kpis = (_live_analytics().get("kpis", {}) if mt5_bridge.status().get("connected") else {})
    except Exception:
        kpis = {}
    context = {"baseline": decision_engine.strictness_dict(),
               "performance": {k: kpis.get(k) for k in ("winRate", "profitFactor", "expectancy", "totalTrades", "maxDrawdown") if k in kpis}}
    res = ai_strategy_gen.generate_candidates(provider, api_key, model, context, n=n)
    if not res.get("ok"):
        return res
    added = strategy_lab.add_candidates(res["candidates"])
    res["added"] = added
    res["total"] = len(strategy_lab.candidates())
    res["message"] = f"{provider.upper()} proposed {res.get('acceptedCount', 0)} safe candidate(s); {added} added. Run the lab to test them on your data."
    _push_notification("AI generated strategies", res["message"], "info")
    return res


@app.post("/api/lab/install")
def lab_install(payload: dict[str, Any] = Body(default={})):
    """ADDITIVELY install a candidate: register it as a real strategy carrying its OWN entry gates
    and let the router pick it when it fits — WITHOUT rewriting the global strictness. Returns the
    back/forward evidence + thesis. Only ever called after the user clicks Install."""
    cand = strategy_lab.get(str(payload.get("id", "")))
    if not cand:
        return {"ok": False, "message": f"Unknown candidate '{payload.get('id')}'."}
    prof = cand["profile"]
    lab_state = SETTINGS_STATE.setdefault("strategyLab", {})
    row = next((r for r in (LAB_STATE.get("lastResult") or {}).get("candidates", []) if r["id"] == cand["id"]), None)
    # Register it as a visible, removable strategy. It competes in the rotation with its OWN gates;
    # the global strictness is left untouched (that's the whole point — installs are additive now).
    sid = _register_installed_strategy(cand, row)
    lab_state["installed"] = {
        "id": cand["id"], "name": cand["name"], "thesis": cand.get("thesis", ""),
        "source": cand.get("source", "library"), "profile": prof, "evidence": row,
        "additive": True, "strategyId": sid}
    _save_settings()
    LAB_STATE["installedProfile"] = {"id": cand["id"], "name": cand["name"], "strategyId": sid,
                                     "appliedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _management_alert("Strategy installed", f"{cand['name']} now competes in your strategy rotation with its own entry gates — it did NOT change your global strictness. {cand.get('thesis','')}", "success")
    return {"ok": True, "installed": LAB_STATE["installedProfile"], "evidence": row,
            "thesis": cand.get("thesis"), "gateProfile": _profile_to_gate(prof), "additive": True}


@app.post("/api/lab/uninstall")
def lab_uninstall(payload: dict[str, Any] = Body(default={})):
    """Remove an installed Strategy-Lab strategy. Additive installs (the new default) just drop the
    strategy from the rotation — the global strictness was never touched. LEGACY installs that
    rewrote the global strictness are reverted to the snapshot taken at install time, or to safe
    defaults if the install predates revert-tracking (so a stuck user is never trapped)."""
    lab_state = SETTINGS_STATE.setdefault("strategyLab", {})
    installed = lab_state.get("installed")
    if not installed and not any(v.get("source") == "strategy_lab" for v in STRATEGIES_STATE.values()):
        return {"ok": False, "message": "No Strategy-Lab strategy is installed."}
    name = (installed or {}).get("name", "Lab strategy")
    additive = bool((installed or {}).get("additive"))
    # Always remove the visible strategy entry from the rotation.
    for k in [k for k, v in STRATEGIES_STATE.items() if v.get("source") == "strategy_lab"]:
        STRATEGIES_STATE.pop(k, None)
    msg_tail = ""
    if not additive:
        # LEGACY install mutated the GLOBAL strictness — restore it (snapshot, else safe defaults).
        ai_cfg = SETTINGS_STATE.setdefault("ai", {})
        pre = lab_state.get("preInstallAi")
        if not pre:
            d = _default_settings().get("ai", {})
            pre = {k: d.get(k) for k in _LAB_GATE_KEYS if k in d}
        for k, v in pre.items():
            ai_cfg[k] = v
        for k in _LAB_GATE_KEYS:
            if k not in pre:
                ai_cfg.pop(k, None)
        pre_sess = lab_state.get("preInstallSessions")
        if pre_sess is not None:
            SETTINGS_STATE.setdefault("trading", {})["allowedSessions"] = pre_sess
        decision_engine.configure_strictness(ai_cfg)
        msg_tail = f" Restored your global strictness: {decision_engine.strictness_dict().get('strictnessMode', 'balanced')}."
    for key in ("installed", "preInstallAi", "preInstallSessions"):
        lab_state.pop(key, None)
    LAB_STATE["installedProfile"] = None
    _save_settings()
    _management_alert("Strategy uninstalled", f"Removed '{name}' from your strategy rotation.{msg_tail}", "info")
    return {"ok": True, "message": f"Removed '{name}' from the rotation.{msg_tail}",
            "restoredConfig": decision_engine.strictness_dict()}


@app.post("/api/backtest/apply-verdicts")
def backtest_apply_verdicts(payload: dict[str, Any] = Body(default={})):
    """Disable strategies the backtest flagged DISABLE (kept editable on the Strategies page)."""
    disabled: list[str] = []
    rows = payload.get("strategies", []) if isinstance(payload.get("strategies"), list) else []
    want_disable = {str(r.get("strategy")) for r in rows if r.get("verdict") == "DISABLE"}
    for s in STRATEGIES_STATE.values():
        if s.get("name") in want_disable:
            s["enabled"] = False
            disabled.append(s["name"])
    return {"ok": True, "disabled": disabled, "message": f"Disabled {len(disabled)} strategy(ies) with no measured edge."}


@app.post("/api/backtest/monte-carlo")
def backtest_monte_carlo(payload: dict[str, Any] = Body(default={})):
    return monte_carlo.run(payload)


@app.get("/api/replay/trade/{trade_id}")
def replay_trade(trade_id: str):
    return replay_engine.replay(trade_id)


@app.get("/api/calibration/probability")
def probability_calibration():
    return memory.stats().get("probabilityCalibration", [])


@app.post("/api/trades/manage-live")
def manage_live_trade(payload: dict[str, Any] = Body(...)):
    return trade_manager.live_management_decision(payload)


@app.get("/api/broker/execution-quality")
def broker_execution_quality():
    return broker_scorer.score()


@app.get("/api/overfitting/guard")
def overfitting_status():
    return overfitting_guard.evaluate(memory.stats().get("strategyPerformance", []))


@app.get("/api/emergency/kill-switch")
def emergency_status():
    return kill_switch.status()


@app.post("/api/emergency/kill-switch")
def emergency_activate(payload: dict[str, Any] = Body(default={})):
    return kill_switch.activate(str(payload.get("reason", "Manual emergency stop")))


@app.post("/api/emergency/reset")
def emergency_reset():
    return kill_switch.reset()


@app.post("/api/trades/execute-multi-target")
def execute_multi_target(payload: dict[str, Any] = Body(...)):
    if kill_switch.status().get("active"):
        return {"ok": False, "blocked": True, "message": "Emergency kill switch is active."}
    plan = trade_manager.build_child_orders(payload)
    if not plan.get("ok"):
        return {"ok": False, "blocked": True, "tradePlan": plan, "message": "TP1-TP4 plan failed safety validation."}
    bridge_result = mt5_bridge.execute_multi_target(payload)
    return {"ok": bool(bridge_result.get("ok")), "tradePlan": plan, "execution": bridge_result}


@app.get("/api/pyramiding/settings")
def pyramiding_settings():
    return pyramiding_engine.settings_dict(camel=True)


@app.post("/api/pyramiding/settings")
def update_pyramiding_settings(payload: dict[str, Any] = Body(default={})):
    updated = pyramiding_engine.update_settings(payload)
    SETTINGS_STATE["pyramiding"] = updated
    return {"ok": True, "settings": updated}


@app.get("/api/pyramiding/plan")
def pyramiding_plan():
    decision = _decision()
    active = mt5_bridge.open_positions(bot_only=True)
    position = active[0] if active else None
    return pyramiding_engine.evaluate(decision, position=position, market=_live_market(), broker_quality=broker_scorer.score(), kill_switch=kill_switch.status())


@app.post("/api/pyramiding/plan")
def pyramiding_plan_post(payload: dict[str, Any] = Body(default={})):
    decision = payload.get("decision") or _decision()
    return pyramiding_engine.evaluate(decision, position=payload.get("position") or None, market=payload.get("market") or _live_market(), broker_quality=broker_scorer.score(), kill_switch=kill_switch.status())


@app.post("/api/pyramiding/execute")
def pyramiding_execute(payload: dict[str, Any] = Body(default={})):
    if kill_switch.status().get("active"):
        return {"ok": False, "blocked": True, "message": "Emergency kill switch is active."}
    plan = pyramiding_engine.evaluate(payload.get("decision") or _decision(), position=payload.get("position") or None, market=payload.get("market") or _live_market(), broker_quality=broker_scorer.score(), kill_switch=kill_switch.status())
    if not plan.get("allowed"):
        return {"ok": False, "dryRun": True, "message": "Pyramiding blocked by protected lot-scaling controls.", "plan": plan}
    next_add = plan.get("nextAdd") or {}
    order_payload = {"symbol": payload.get("symbol", "XAUUSD"), "side": payload.get("side", _live_market().get("side", "BUY")), "volume": float(payload.get("volume", next_add.get("lot", plan.get("nextLot", 0.01)))), "comment": f"GODMODE_Protected Pyramid Add {next_add.get('add_number', 1)}", "magic": mt5_bridge.magic, "source": "godmode_bot", "riskPlan": {"mode": plan.get("mode"), "fastGuard": plan.get("fastGuard"), "riskGovernor": plan.get("riskGovernor")}}
    return {"ok": True, "dryRun": not mt5_bridge.live_enabled, "message": "Protected aggressive pyramid order prepared.", "pyramidingPlan": plan, "execution": mt5_bridge.execute(order_payload)}


@app.get("/api/trade-management/status")
def trade_management_status():
    return {"hold": {"enabled": True, "status": "ACTIVE", "rule": "Hold while structure, macro, spread and momentum remain valid."}, "breakEven": {"enabled": True, "status": "ARMED", "rule": "Move SL to BE after TP1 or +1R before pyramid adds."}, "trailing": {"enabled": True, "status": "ACTIVE", "rule": "Trail behind M5/M15 structure after TP2; ATR/liquidity trail after TP3."}, "tpPush": {"enabled": True, "status": "AI_CONTROLLED", "rule": "Push TP3/TP4 only if HTF liquidity remains open and volatility expands cleanly."}, "tpTargets": ["TP1", "TP2", "TP3", "TP4"], "pyramiding": pyramiding_plan()}


@app.get("/api/ai/super-intelligence")
def ai_super_intelligence():
    m = _live_market()
    decision = _decision()
    market_intel = market_intelligence()
    broker = broker_scorer.score()
    overfit = overfitting_guard.evaluate(memory.stats().get("strategyPerformance", []))
    kill = kill_switch.status()
    active = mt5_bridge.open_positions(bot_only=True)
    pyramid = pyramiding_engine.evaluate(decision, position=active[0] if active else None, market=m, broker_quality=broker, kill_switch=kill)
    return super_summary.build(decision, market_intel, memory.stats(), broker, overfit, kill, pyramid)


@app.get("/api/ui/feature-map")
def ui_feature_map():
    return {"aiAgentPanels": ["Super Intelligence Score", "Deterministic Decision Engine", "Trader Questions", "Pyramiding Autopilot", "Hold/BE/Trailing/TP Push", "TP1-TP4 Runner", "News Blackout", "Macro Context", "Calibration", "Overfitting Guard", "Kill Switch"], "backendFeatures": {"walkForwardBacktesting": True, "monteCarloTesting": True, "strategyPerformanceMemory": True, "sessionWinRateMemory": True, "spreadSlippageMemory": True, "economicCalendar": True, "dxyUs10yMacroAwareness": True, "goldVolatilityRegime": True, "tradeReplay": True, "probabilityCalibration": True, "tp1tp4Management": True, "postTradeAutoJournal": True, "brokerExecutionQuality": True, "newsBlackout": True, "overfittingGuard": True, "emergencyKillSwitch": True, "aiControlledPyramiding": True, "protectedAggressiveLotScaling": True, "profitBufferRiskFunding": True, "fastGuardNewestAddFirst": True}, "warning": "UI reflects backend modules. Live proof still requires real feeds and forward testing."}


@app.get("/api/feeds/economic-calendar/live")
def live_economic_calendar():
    return {"events": live_calendar.events(), "blackout": live_calendar.blackout_status(), "configured": bool(live_calendar.url)}


@app.get("/api/feeds/dxy")
def live_dxy_feed():
    return macro_feed.snapshot().get("dxy")


@app.get("/api/feeds/us10y")
def live_us10y_feed():
    return macro_feed.snapshot().get("us10y")


@app.get("/api/macro/live-gold-context")
def live_macro_gold_context():
    return macro_feed.snapshot()


@app.get("/api/feeds/status")
def feeds_status():
    """Live/stub status for each data feed — drives the Settings → Data Feeds badges so you
    can SEE whether macro & news are actually live or running neutral/unconfigured."""
    df = SETTINGS_STATE.get("dataFeeds", {}) if isinstance(SETTINGS_STATE.get("dataFeeds"), dict) else {}
    try:
        macro_snap = macro.snapshot()
    except Exception:
        macro_snap = {"status": "error", "macroGoldBias": "neutral"}
    try:
        cal = calendar.blackout_status()
    except Exception:
        cal = {"status": "error", "isBlackout": False}
    return {
        "ok": True,
        "dxy": {"configured": bool(str(df.get("dxyUrl", "")).strip())},
        "us10y": {"configured": bool(str(df.get("us10yUrl", "")).strip())},
        "macro": {"status": macro_snap.get("status", "not_configured"), "goldBias": macro_snap.get("macroGoldBias"),
                  "liveFeeds": macro_snap.get("liveFeeds", False), "detail": macro_snap.get("detail")},
        "economicCalendar": {"status": cal.get("status", "not_configured"), "configured": bool(str(df.get("economicCalendarUrl", "")).strip()),
                             "isBlackout": cal.get("isBlackout", False), "upcoming": len(cal.get("upcomingEvents", []))},
        "note": "Unconfigured feeds run NEUTRAL (no tilt) and do not block trades. Macro affects the decision; the live-* display endpoints are informational.",
    }


@app.post("/api/backtest/tick-data")
def tick_data_backtest(payload: dict[str, Any] = Body(default={})):
    return tick_backtester.run(payload)


@app.post("/api/execution/lot-size")
def broker_lot_size(payload: dict[str, Any] = Body(default={})):
    return lot_sizer.calculate(payload)


@app.get("/api/execution/symbol-specs/{symbol}")
def symbol_specs(symbol: str):
    return lot_sizer.symbol_specs(symbol)


@app.post("/api/trades/partial-close")
def partial_close_trade(payload: dict[str, Any] = Body(...)):
    return live_execution.partial_close(payload)


@app.post("/api/trades/modify-trailing-stop")
def modify_trailing_stop(payload: dict[str, Any] = Body(...)):
    return live_execution.modify_trailing_stop(payload)


@app.post("/api/exposure/validate-pyramid")
def validate_pyramid_exposure(payload: dict[str, Any] = Body(default={})):
    return exposure_validator.validate_pyramid(payload)


@app.post("/api/trades/pyramid-execute-real")
def pyramid_execute_real(payload: dict[str, Any] = Body(default={})):
    if kill_switch.status().get("active"):
        return {"ok": False, "blocked": True, "message": "Emergency kill switch is active."}
    validation = exposure_validator.validate_pyramid(payload)
    if not validation.get("allowed"):
        return live_execution.pyramid_execute(payload, validation)
    order_payload = dict(payload)
    order_payload.setdefault("source", "godmode_bot")
    order_payload.setdefault("magic", mt5_bridge.magic)
    order_payload.setdefault("comment", "GODMODE_pyramid_execute")
    if not mt5_bridge.live_enabled:
        return live_execution.pyramid_execute(order_payload, validation)
    return {"ok": True, "validation": validation, "execution": mt5_bridge.execute(order_payload)}


@app.post("/api/replay/store")
def replay_store(payload: dict[str, Any] = Body(default={})):
    return replay_storage.store(payload)


@app.get("/api/replay/storage")
def replay_storage_list():
    return replay_storage.list()


@app.post("/api/versioning/strategy")
def register_strategy_version(payload: dict[str, Any] = Body(default={})):
    return version_registry.register_strategy(payload)


@app.post("/api/versioning/parameters")
def register_parameter_version(payload: dict[str, Any] = Body(default={})):
    return version_registry.register_parameters(payload)


@app.get("/api/versioning")
def versioning_list():
    return version_registry.list()


@app.post("/api/reports/forward-test")
def forward_test_report(payload: dict[str, Any] = Body(default={})):
    return forward_reporter.generate(payload)


@app.get("/api/reports/daily-ai-review")
def daily_ai_review():
    return forward_reporter.daily_ai_review()


@app.get("/api/ui/full-feature-map")
def ui_full_feature_map():
    return {"realEconomicCalendarApi": True, "realDxyFeed": True, "realUs10yYieldFeed": True, "realTickDataBacktester": True, "brokerSpecificLotSizing": True, "partialCloseTp1Tp4": True, "mt5TrailingStopModifier": True, "pyramidExecutionExposureValidation": True, "protectedAggressiveLotScaling": True, "profitBufferRiskFunding": True, "fastGuardNewestAddFirst": True, "tradeScreenshotReplayStorage": True, "strategyVersioning": True, "parameterVersionTracking": True, "forwardTestReportGenerator": True, "dailyAiPerformanceReview": True, "uiPagesUpdated": ["Dashboard", "Signals", "Strategies", "Trades", "Risk", "AI Agent", "Analytics", "Journal", "Settings"], "liveFeedNote": "Adapters are live-provider ready. Configure API URLs/keys in .env for real data; safe fallback keeps development stable."}


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"ok": False, "message": "Frontend build not found. Run npm run build or use start_frontend.bat."}, status_code=404)
