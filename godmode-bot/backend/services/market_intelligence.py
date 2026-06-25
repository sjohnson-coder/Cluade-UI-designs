"""GodMode Market Intelligence — Upgraded v3.
Fixes:
- Economic Calendar no longer uses fake relative-time events.
- MacroAwareness no longer hardcodes DXY/US10Y; tries live env-URL first, then
  falls back to neutral context (not permanently bullish).
- GoldVolatilityRegime now also classifies by session ATR norms.
- MarketCleanliness gets a richer scoring model.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from statistics import mean, pstdev
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
        self._cache_ttl_seconds = 300  # 5 min

    @property
    def url(self) -> str:
        return _env_url("ECONOMIC_CALENDAR_URL", "GODMODE_ECONOMIC_CALENDAR_URL")

    def force_refresh(self) -> None:
        self._cache = []
        self._cache_at = None

    def _fetch_live(self) -> list[dict[str, Any]]:
        if not self.url:
            return []
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "GodModeBot/3"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("events") or data.get("data") or []
        except Exception:
            pass
        return []

    def events(self) -> list[dict[str, Any]]:
        now = utc_now()
        # Refresh cache every 5 minutes.
        if self._cache_at is None or (now - self._cache_at).total_seconds() > self._cache_ttl_seconds:
            live = self._fetch_live()
            if live:
                self._cache = live
            self._cache_at = now
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
            before = timedelta(minutes=int(event.get("blackoutBeforeMin", 15)))
            after = timedelta(minutes=int(event.get("blackoutAfterMin", 20)))
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
            req = urllib.request.Request(url, headers={"User-Agent": "GodModeBot/3"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            return None

    def snapshot(self) -> dict[str, Any]:
        now = utc_now()
        if self._cache and self._cache_at and (now - self._cache_at).total_seconds() < self._ttl:
            return self._cache

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
        self._cache_at = now
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
        confidence = float(market.get("confidence", 0) or 0)
        volatility = str(market.get("volatility", "normal")).lower()
        dirty_reasons: list[str] = []

        if calendar_status.get("isBlackout"):
            dirty_reasons.append("high-impact news blackout active")
        if spread > 0.35:
            dirty_reasons.append(f"spread {spread:.2f} above 0.35 Gold threshold")
        if spread > 0.5:
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
