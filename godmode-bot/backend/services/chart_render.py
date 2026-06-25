"""Server-side chart image rendering for Telegram alerts and daily/weekly recaps.

Renders a real XAUUSD candlestick chart with EMA20/50 and the trade's entry / SL /
TP levels annotated, plus an equity-curve recap image. Uses matplotlib if available
and degrades gracefully (returns None) when it is not installed, so alerts always
send — just as text-only when charts can't be drawn.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

try:
    import matplotlib
    matplotlib.use("Agg")  # headless, no display server needed
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    _HAVE_MPL = True
except Exception:  # pragma: no cover
    _HAVE_MPL = False


def available() -> bool:
    return _HAVE_MPL


def render_trade_chart(candles: list[dict[str, Any]], *, side: str, entry: float | None = None,
                       sl: float | None = None, tps: list[float] | None = None,
                       title: str = "XAUUSD", subtitle: str = "",
                       timeframe: str = "", live: bool = True) -> bytes | None:
    """Candlestick + EMA20/50 + entry/SL/TP lines → PNG bytes (or None if unavailable).

    ``timeframe`` is stamped in the title and a real time axis is drawn from the candle
    timestamps, so the image can be cross-checked against your platform on the SAME timeframe
    (the bot trades M15 — an M5 platform view will look different). ``live=False`` watermarks
    the image as DEMO data so a synthetic/disconnected feed is never mistaken for your broker's.
    """
    if not _HAVE_MPL or not candles:
        return None
    try:
        view = candles[-70:]
        n = len(view)
        fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=130)
        fig.patch.set_facecolor("#0e1116")
        ax.set_facecolor("#0e1116")
        for i, c in enumerate(view):
            o, h, l, cl = float(c.get("open", 0)), float(c.get("high", 0)), float(c.get("low", 0)), float(c.get("close", 0))
            up = cl >= o
            col = "#16c784" if up else "#ea3943"
            ax.plot([i, i], [l, h], color=col, linewidth=0.8, zorder=2)
            ax.add_patch(Rectangle((i - 0.3, min(o, cl)), 0.6, max(abs(cl - o), 0.01), facecolor=col, edgecolor=col, zorder=3))
        ema20 = [float(c.get("ema20", 0) or 0) for c in view]
        ema50 = [float(c.get("ema50", 0) or 0) for c in view]
        if any(ema20):
            ax.plot(range(n), ema20, color="#f0b90b", linewidth=1.1, label="EMA20", zorder=4)
        if any(ema50):
            ax.plot(range(n), ema50, color="#7a5cff", linewidth=1.1, label="EMA50", zorder=4)

        def hline(level, color, label):
            if level and level > 0:
                ax.axhline(level, color=color, linewidth=1.0, linestyle="--", alpha=0.9, zorder=5)
                ax.text(n - 1, level, f" {label} {level:.2f}", color=color, fontsize=7, va="center", ha="left")

        hline(entry, "#3b82f6", "ENTRY")
        hline(sl, "#ea3943", "SL")
        for idx, tp in enumerate(tps or []):
            hline(tp, "#16c784", f"TP{idx + 1}")

        tf = f" · {timeframe}" if timeframe else ""
        ax.set_title(f"{title}{tf}   {side}", color="#e6e6e6", fontsize=11, loc="left")
        if subtitle:
            ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, color="#9aa4b2", fontsize=8, ha="left")
        # DEMO watermark so a synthetic/disconnected feed is never mistaken for the live broker feed.
        if not live:
            ax.text(0.5, 0.5, "DEMO DATA", transform=ax.transAxes, color="#3a4150",
                    fontsize=30, ha="center", va="center", rotation=18, alpha=0.45, zorder=1)
        ax.tick_params(colors="#9aa4b2", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#2a2f3a")
        ax.grid(color="#1c212b", linewidth=0.5)
        # Real date+time axis from candle timestamps (broker/server time, matching your
        # platform) → cross-check bar-for-bar against your chart.
        def _lbl(c: dict[str, Any]) -> str:
            t = c.get("time")
            if t:
                try:
                    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%m/%d %H:%M")
                except Exception:
                    pass
            return str(c.get("timeLabel", ""))
        labels = [_lbl(c) for c in view]
        if any(labels):
            step = max(1, n // 6)
            ticks = list(range(0, n, step))
            ax.set_xticks(ticks)
            ax.set_xticklabels([labels[i] for i in ticks], fontsize=6, color="#9aa4b2", rotation=12)
        ax.set_xlim(-1, n + 6)
        ax.legend(loc="upper left", fontsize=7, facecolor="#0e1116", edgecolor="#2a2f3a", labelcolor="#cbd5e1")
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def render_equity_recap(points: list[dict[str, Any]], *, title: str = "Daily Recap",
                        kpis: dict[str, Any] | None = None) -> bytes | None:
    """Equity-curve recap image with a KPI strip → PNG bytes (or None)."""
    if not _HAVE_MPL:
        return None
    try:
        ys = [float(p.get("value", p.get("equity", 0)) or 0) for p in points] or [0.0]
        fig, ax = plt.subplots(figsize=(7.2, 3.8), dpi=130)
        fig.patch.set_facecolor("#0e1116")
        ax.set_facecolor("#0e1116")
        col = "#16c784" if ys[-1] >= ys[0] else "#ea3943"
        ax.plot(range(len(ys)), ys, color=col, linewidth=1.6)
        ax.fill_between(range(len(ys)), ys, min(ys), color=col, alpha=0.12)
        ax.set_title(title, color="#e6e6e6", fontsize=12, loc="left")
        if kpis:
            strip = "   ".join(f"{k}: {v}" for k, v in kpis.items())
            ax.text(0.0, 1.04, strip, transform=ax.transAxes, color="#9aa4b2", fontsize=8, ha="left")
        ax.tick_params(colors="#9aa4b2", labelsize=7)
        for spine in ax.spines.values():
            spine.set_color("#2a2f3a")
        ax.grid(color="#1c212b", linewidth=0.5)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None
