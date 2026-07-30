"""GodMode Market Intelligence — Upgraded v3.
Fixes:
- Economic Calendar no longer uses fake relative-time events.
- MacroAwareness no longer hardcodes DXY/US10Y; tries live env-URL first, then
  falls back to neutral context (not permanently bullish).
- GoldVolatilityRegime now also classifies by session ATR norms.
- MarketCleanliness gets a richer scoring model.
"""
from __future__ import annotations

import logging
import json
import os
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from statistics import pstdev
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_url(*names: str) -> str:
    """First non-empty env var among ``names`` (read FRESH each call, so feed URLs set
    from the Settings UI at runtime take effect without a restart). Accepts both the
    ``*_FEED_URL`` and ``GODMODE_*_URL`` naming conventions used across the codebase."""
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""


class EconomicCalendar:
    """Economic calendar with live-URL hook.

    Set ECONOMIC_CALENDAR_URL (or GODMODE_ECONOMIC_CALENDAR_URL) to a ForexFactory-compatible
    JSON endpoint. Without it the calendar stays empty (no fake blackouts).
    """

    def __init__(self) -> None:
        self._cache: list[dict[str, Any]] = []
        self._cache_at: datetime | None = None
        self._cache_ttl_seconds = 900  # 15 min; economic calendars do not need high-frequency polling
        self._refreshing = False
        self._retry_after = None
        self._failure_count = 0
        # V12.82: this calendar drives the TRADING news-blackout (decision_engine uses it).
        # It used to resolve its URL from environment variables ONLY, so a URL saved in
        # Settings 12c never reached it — the dashboard could show "configured" while the
        # calendar that actually blocks trades stayed empty. Settings now override env here too.
        self._url_override = ""
        self._before_override: int | None = None
        self._after_override: int | None = None

    def configure(self, url: str = "", before: Any = None, after: Any = None) -> None:
        new_url = (url or "").strip()
        changed = new_url != self._url_override
        self._url_override = new_url
        try:
            self._before_override = int(before) if before is not None else self._before_override
        except Exception as _suppressed_exc:
            logging.getLogger(__name__).warning("Recoverable failure in market_intelligence.py:61: %s", _suppressed_exc)
        try:
            self._after_override = int(after) if after is not None else self._after_override
        except Exception as _suppressed_exc:
            logging.getLogger(__name__).warning("Recoverable failure in market_intelligence.py:65: %s", _suppressed_exc)
        if changed:
            self.force_refresh()

    @property
    def url(self) -> str:
        return self._url_override or _env_url("ECONOMIC_CALENDAR_URL", "GODMODE_ECONOMIC_CALENDAR_URL")

    def force_refresh(self) -> None:
        self._cache = []
        self._cache_at = None

    def _fetch_live(self) -> list[dict[str, Any]]:
        if not self.url:
            return []
        try:
            from .safe_http import read_public_https
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept": "application/json,text/plain,*/*"})
            data = json.loads(read_public_https(req, timeout=8).decode("utf-8", "ignore"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("events") or data.get("data") or []
        except Exception as exc:
            self._failure_count += 1
            is429 = getattr(exc, "code", 0) == 429
            delay = min(1800, (300 if is429 else 60) * (2 ** min(self._failure_count - 1, 4)))
            self._retry_after = utc_now() + timedelta(seconds=delay)
            logging.getLogger(__name__).warning("Economic calendar unavailable; retry in %ss: %s", delay, exc)
        return []

    def events(self) -> list[dict[str, Any]]:
        now = utc_now()
        # Refresh every 5 min — but NEVER block the calling request on the network. When the cache is
        # stale we kick the fetch onto a daemon thread and return the current (stale/empty) cache
        # immediately, so a slow calendar URL can't freeze a decision/poll for up to 8s.
        stale = self._cache_at is None or (now - self._cache_at).total_seconds() > self._cache_ttl_seconds
        cooling = self._retry_after is not None and now < self._retry_after
        if stale and self.url and not cooling and not self._refreshing:
            self._refreshing = True

            def _bg() -> None:
                try:
                    live = self._fetch_live()
                    if live:
                        self._cache = live
                        self._failure_count = 0
                        self._retry_after = None
                    self._cache_at = utc_now()
                finally:
                    self._refreshing = False

            threading.Thread(target=_bg, daemon=True).start()
        return self._cache

    def blackout_status(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        active = []
        upcoming = []
        for event in self.events():
            try:
                t_raw = event.get("time") or event.get("date") or event.get("timestamp") or ""
                t = datetime.fromisoformat(str(t_raw).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            impact = str(event.get("impact") or event.get("importance") or "").lower()
            if impact not in {"high", "3", "red"}:
                continue
            before = timedelta(minutes=int(event.get("blackoutBeforeMin", self._before_override if self._before_override is not None else 15)))
            after = timedelta(minutes=int(event.get("blackoutAfterMin", self._after_override if self._after_override is not None else 20)))
            if t - before <= now <= t + after:
                active.append(event)
            elif now < t:
                upcoming.append(event)
        return {"isBlackout": bool(active), "activeEvents": active, "upcomingEvents": upcoming[:5],
                "liveConfigured": bool(self.url),
                "status": "live" if self.url else "not_configured"}


class MacroAwareness:
    """Gold macro context: DXY and US10Y move inversely to gold (generally).

    Hooks:
      DXY_FEED_URL  — JSON endpoint returning {"value": float, "changePct": float}
      US10Y_FEED_URL — same shape
    Falls back to "neutral" context (never permanently bullish).
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] | None = None
        self._cache_at: datetime | None = None
        self._ttl = 600  # 10 min
        self._refreshing = False

    @property
    def dxy_url(self) -> str:
        return _env_url("DXY_FEED_URL", "GODMODE_DXY_URL")

    @property
    def us10y_url(self) -> str:
        return _env_url("US10Y_FEED_URL", "GODMODE_US10Y_URL")

    def force_refresh(self) -> None:
        self._cache = None
        self._cache_at = None

    def _fetch(self, url: str) -> dict[str, Any] | None:
        if not url:
            return None
        try:
            from .safe_http import read_public_https
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36", "Accept": "application/json,text/plain,*/*"})
            return json.loads(read_public_https(req, timeout=8).decode("utf-8", "ignore"))
        except Exception:
            return None

    def _neutral(self) -> dict[str, Any]:
        configured = bool(self.dxy_url or self.us10y_url)
        return {
            "dxy": {"value": 0.0, "changePct": 0.0, "biasForGold": "neutral"},
            "us10y": {"value": 0.0, "changeBp": 0.0, "biasForGold": "neutral"},
            "realYields": {"biasForGold": "neutral"},
            "macroGoldBias": "neutral",
            "detail": "Macro feed warming up…" if configured else "No live macro feed configured. Set DXY_FEED_URL / US10Y_FEED_URL in .env for live context.",
            "liveFeeds": False,
            "status": "warming" if configured else "not_configured",
        }

    def snapshot(self) -> dict[str, Any]:
        now = utc_now()
        if self._cache and self._cache_at and (now - self._cache_at).total_seconds() < self._ttl:
            return self._cache
        # Stale/cold → refresh on a daemon thread and return the last good cache (or neutral) NOW,
        # so a slow DXY/US10Y URL can never block the decision that asked for macro context.
        if (self.dxy_url or self.us10y_url) and not self._refreshing:
            self._refreshing = True
            threading.Thread(target=self._refresh, daemon=True).start()
        return self._cache or self._neutral()

    def _refresh(self) -> None:
        try:
            self._build_snapshot()
        finally:
            self._refreshing = False

    def _build_snapshot(self) -> dict[str, Any]:
        dxy_data = self._fetch(self.dxy_url)
        us10y_data = self._fetch(self.us10y_url)

        if dxy_data:
            dxy_val = float(dxy_data.get("value", 0) or 0)
            dxy_chg = float(dxy_data.get("changePct", 0) or 0)
            dxy_bias = "bullish" if dxy_chg < -0.10 else "bearish" if dxy_chg > 0.10 else "neutral"
        else:
            dxy_val = 0.0
            dxy_chg = 0.0
            dxy_bias = "neutral"

        if us10y_data:
            us10y_val = float(us10y_data.get("value", 0) or 0)
            us10y_chg = float(us10y_data.get("changeBp", us10y_data.get("changePct", 0)) or 0)
            us10y_bias = "bullish" if us10y_chg < -3 else "bearish" if us10y_chg > 3 else "neutral"
        else:
            us10y_val = 0.0
            us10y_chg = 0.0
            us10y_bias = "neutral"

        bullish_count = sum(b == "bullish" for b in [dxy_bias, us10y_bias])
        bearish_count = sum(b == "bearish" for b in [dxy_bias, us10y_bias])
        if bullish_count > bearish_count:
            macro_bias = "bullish"
            detail = "DXY/yields supportive for gold longs."
        elif bearish_count > bullish_count:
            macro_bias = "bearish"
            detail = "DXY/yields headwind for gold longs."
        else:
            macro_bias = "neutral"
            detail = "Macro context is neutral — no strong directional macro edge." if (dxy_data or us10y_data) else "No live macro feed configured. Set DXY_FEED_URL / US10Y_FEED_URL in .env for live context."

        self._cache = {
            "dxy": {"value": dxy_val, "changePct": dxy_chg, "biasForGold": dxy_bias},
            "us10y": {"value": us10y_val, "changeBp": us10y_chg, "biasForGold": us10y_bias},
            "realYields": {"biasForGold": "neutral"},
            "macroGoldBias": macro_bias,
            "detail": detail,
            "liveFeeds": bool(dxy_data or us10y_data),
            "status": "live" if (dxy_data or us10y_data) else "not_configured",
        }
        self._cache_at = utc_now()
        return self._cache


class GoldVolatilityRegime:
    """Classify Gold volatility using ATR-14 vs typical Gold ATR norms."""

    # Typical XAUUSD M15 ATR ranges (empirical Gold norms)
    _NORM_ATR_LOW = 4.0       # below this = compression / squeeze
    _NORM_ATR_HIGH = 25.0     # above this = high volatility expansion
    _NORM_ATR_EXTREME = 45.0  # above this = extreme / reduce size

    def classify(self, candles: list[dict[str, Any]] | None = None, atr14: float | None = None) -> dict[str, Any]:
        atr = float(atr14 or 0.0)
        closes: list[float] = []
        if candles:
            closes = [float(c.get("close", 0)) for c in candles if c.get("close")]

        if not atr and len(closes) >= 15:
            # Compute from candles if not supplied
            highs = [float(c.get("high", 0)) for c in candles or []]
            lows  = [float(c.get("low",  0)) for c in candles or []]
            trs = []
            for i in range(1, len(closes)):
                trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
            if trs:
                atr = sum(trs[-14:]) / min(14, len(trs))

        vol = pstdev(closes[-30:]) if len(closes) >= 30 else atr / 2.0

        if atr == 0.0:
            regime = "Unknown — No ATR Data"
            tradable = False
        elif atr < self._NORM_ATR_LOW:
            regime = "Low Volatility / Compression"
            tradable = False
        elif atr <= self._NORM_ATR_HIGH:
            regime = "Normal Tradable Volatility"
            tradable = True
        elif atr <= self._NORM_ATR_EXTREME:
            regime = "High Volatility Expansion"
            tradable = True
        else:
            regime = "Extreme / Reduce Size"
            tradable = False

        return {
            "regime": regime,
            "atr14": round(atr, 3),
            "closeStd30": round(vol, 3),
            "isTradable": tradable,
        }


class MarketCleanliness:
    """Evaluate whether market conditions are clean enough to trade Gold."""

    def evaluate(self, market: dict[str, Any], calendar_status: dict[str, Any]) -> dict[str, Any]:
        spread = float(market.get("spread", 0.12) or 0.12)
        volatility = str(market.get("volatility", "normal")).lower()
        dirty_reasons: list[str] = []

        if calendar_status.get("isBlackout"):
            dirty_reasons.append("high-impact news blackout active")
        # Use the same maxSpread configured in AI settings; V12.35 had a hidden 0.35 hard gate
        # that could contradict Settings maxSpread=0.40 and silently block otherwise-approved trades.
        max_spread = float(market.get("maxSpread", 0.40) or 0.40)
        critical_spread = max(0.50, max_spread * 1.35)
        if spread > max_spread:
            dirty_reasons.append(f"spread {spread:.2f} above configured maxSpread {max_spread:.2f}")
        if spread > critical_spread:
            dirty_reasons.append("spread critically wide — no entries")
        if volatility in {"extreme", "chaotic"}:
            dirty_reasons.append("volatility regime is extreme/chaotic")

        penalties = len(dirty_reasons)
        score = max(10, 95 - penalties * 25)
        return {
            "isClean": not dirty_reasons,
            "dirtyReasons": dirty_reasons,
            "score": score,
        }
