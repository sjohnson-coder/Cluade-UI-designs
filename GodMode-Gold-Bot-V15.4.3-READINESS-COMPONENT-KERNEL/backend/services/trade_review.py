"""V12.80 — Deterministic Trade-Review Engine.

This is the honest half of "AI review": pure arithmetic over closed trades. No LLM, no
guessing, same output every time for the same input. It answers the questions that actually
move the needle:

  • Is expectancy positive, and where does it come from (win rate vs R)?
  • Are losses disproportionately large vs wins? (the July-10 finding: 4.5x)
  • Did fast-fail cut losers at a sane depth, or let them bleed past the floor?
  • Do winners give back most of their MFE before closing? (exit timing)
  • Which strategy / session / confidence bucket actually carries the edge?

Every finding carries a sample size. Findings below MIN_SAMPLE are marked LOW_CONFIDENCE and
never turned into auto-proposals — with 16 trades, any "pattern" is noise. Proposals are
suggestions the user approves one at a time; this module NEVER writes settings.
"""
from __future__ import annotations

import statistics
from typing import Any

MIN_SAMPLE_FINDING = 8      # below this, a finding is informational only
MIN_SAMPLE_PROPOSAL = 30    # below this, we do not propose config changes at all
STRONG_SAMPLE = 50          # findings above this are high-confidence


def _f(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return d
        return float(v)
    except Exception:
        return d


def _bucket_conf(c: float) -> str:
    if c <= 0:
        return "unknown"
    if c < 70:
        return "<70"
    if c < 80:
        return "70-79"
    if c < 88:
        return "80-87"
    return "88+"


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the vetting-journal rows into deterministic performance stats."""
    trades = [r for r in rows if r.get("outcome") in ("WIN", "LOSS")]
    n = len(trades)
    if n == 0:
        return {"ok": True, "sampleSize": 0, "message": "No closed trades to review yet."}

    wins = [r for r in trades if r["outcome"] == "WIN"]
    losses = [r for r in trades if r["outcome"] == "LOSS"]
    rs = [_f(r.get("rMultiple")) for r in trades if r.get("rMultiple") not in ("", None)]

    gross_win = sum(_f(r.get("pnlUsd")) for r in wins)
    gross_loss = sum(_f(r.get("pnlUsd")) for r in losses)
    net = gross_win + gross_loss
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    pf = (gross_win / abs(gross_loss)) if gross_loss else float("inf")
    win_rate = 100.0 * len(wins) / n
    expectancy = net / n
    avg_r = statistics.mean(rs) if rs else 0.0
    loss_win_ratio = (abs(avg_loss) / avg_win) if avg_win else 0.0

    # excursion / management quality (only trades that carry MFE/MAE)
    giveback = None
    if wins:
        gbs = []
        for r in wins:
            mfe = _f(r.get("mfeR"))
            rr = _f(r.get("rMultiple"))
            if mfe > 0.05:
                gbs.append(max(0.0, (mfe - rr) / mfe))
        giveback = round(100.0 * statistics.mean(gbs), 1) if gbs else None

    # losers that bled past a sane scalp stop: deep in R, deep MAE, OR large vs the average win
    # (a -5.56 at -0.86R doesn't cross -1R but is 6x the avg win — it is the trade that hurt).
    deep_losers = [r for r in losses
                   if _f(r.get("rMultiple")) < -1.0
                   or _f(r.get("maeR")) < -1.2
                   or (avg_win > 0 and abs(_f(r.get("pnlUsd"))) >= 3.0 * avg_win)]

    # per-strategy / session / confidence breakdown
    def _by(key: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in trades:
            k = str(r.get(key) or "unknown") or "unknown"
            b = out.setdefault(k, {"n": 0, "wins": 0, "net": 0.0, "r": []})
            b["n"] += 1
            b["wins"] += 1 if r["outcome"] == "WIN" else 0
            b["net"] += _f(r.get("pnlUsd"))
            if r.get("rMultiple") not in ("", None):
                b["r"].append(_f(r.get("rMultiple")))
        for k, b in out.items():
            b["winRate"] = round(100.0 * b["wins"] / b["n"], 1) if b["n"] else 0.0
            b["avgR"] = round(statistics.mean(b["r"]), 2) if b["r"] else 0.0
            b["net"] = round(b["net"], 2)
        return out

    conf_buckets: dict[str, dict[str, Any]] = {}
    for r in trades:
        k = _bucket_conf(_f(r.get("confidence")))
        b = conf_buckets.setdefault(k, {"n": 0, "wins": 0, "net": 0.0})
        b["n"] += 1
        b["wins"] += 1 if r["outcome"] == "WIN" else 0
        b["net"] += _f(r.get("pnlUsd"))
    for k, b in conf_buckets.items():
        b["winRate"] = round(100.0 * b["wins"] / b["n"], 1) if b["n"] else 0.0
        b["net"] = round(b["net"], 2)

    return {
        "ok": True,
        "sampleSize": n,
        "wins": len(wins),
        "losses": len(losses),
        "winRate": round(win_rate, 1),
        "netUsd": round(net, 2),
        "grossWin": round(gross_win, 2),
        "grossLoss": round(gross_loss, 2),
        "profitFactor": round(pf, 2) if pf != float("inf") else None,
        "expectancyUsd": round(expectancy, 3),
        "avgWinUsd": round(avg_win, 2),
        "avgLossUsd": round(avg_loss, 2),
        "avgR": round(avg_r, 3),
        "lossWinSizeRatio": round(loss_win_ratio, 2),
        "winnerGivebackPct": giveback,
        "deepLoserCount": len(deep_losers),
        "byStrategy": _by("strategy"),
        "bySession": _by("session"),
        "byConfidence": conf_buckets,
    }


def findings_and_proposals(stats: dict[str, Any]) -> dict[str, Any]:
    """Turn deterministic stats into ranked findings and (sample-gated) proposals.

    Proposals are diffs the user approves; this function never applies anything.
    """
    n = int(stats.get("sampleSize", 0) or 0)
    findings: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []

    if n == 0:
        return {"findings": [], "proposals": [], "sampleSize": 0,
                "verdict": "No trades yet. Collect data before drawing conclusions."}

    low = n < MIN_SAMPLE_FINDING
    can_propose = n >= MIN_SAMPLE_PROPOSAL
    conf_tag = "HIGH" if n >= STRONG_SAMPLE else ("MEDIUM" if n >= MIN_SAMPLE_PROPOSAL else "LOW")

    # 1) expectancy source
    wr = _f(stats.get("winRate"))
    avg_r = _f(stats.get("avgR"))
    if _f(stats.get("netUsd")) > 0:
        src = "win rate" if wr >= 60 and avg_r < 0.3 else "R per trade"
        findings.append({"severity": "info", "confidence": conf_tag,
                         "title": f"Positive expectancy, driven by {src}",
                         "detail": f"Net +{stats.get('netUsd')} over {n} trades, {wr}% win rate, avg {avg_r}R, PF {stats.get('profitFactor')}."})
    else:
        findings.append({"severity": "warn", "confidence": conf_tag,
                         "title": "Negative or flat expectancy",
                         "detail": f"Net {stats.get('netUsd')} over {n} trades. Do not scale size until this is positive."})

    # 2) loss/win asymmetry — the July-10 signal
    ratio = _f(stats.get("lossWinSizeRatio"))
    if ratio >= 2.5:
        findings.append({"severity": "high", "confidence": conf_tag,
                         "title": f"Losses are {ratio}x the size of wins",
                         "detail": f"Avg win +{stats.get('avgWinUsd')} vs avg loss {stats.get('avgLossUsd')}. "
                                   f"Your edge is win-rate; a few oversized losers can erase many wins. "
                                   f"This is a management problem, not an entry problem."})
        if can_propose:
            proposals.append({
                "id": "tighten_fast_fail_floor",
                "title": "Tighten the fast-fail R floor to cap oversized losers",
                "rationale": f"{stats.get('deepLoserCount')} loser(s) ran past -1R while avg win is only {stats.get('avgR')}R. "
                             f"A tighter floor caps the tail that is hurting expectancy.",
                "path": "trading.tradeManagement.fastFailLossR",
                "suggest": -0.30, "current_hint": "-0.35",
                "risk": "low", "confidence": conf_tag})

    # 3) deep losers → fast-fail audit
    if int(stats.get("deepLoserCount", 0)) > 0:
        findings.append({"severity": "high", "confidence": conf_tag,
                         "title": f"{stats.get('deepLoserCount')} trade(s) bled past -1R before closing",
                         "detail": "Fast-fail or the broker SL let these run deeper than a scalp should. "
                                   "Check whether the -0.35R floor is firing on time."})

    # 4) winner giveback → exit timing
    gb = stats.get("winnerGivebackPct")
    if gb is not None and gb >= 45 and not low:
        findings.append({"severity": "warn", "confidence": conf_tag,
                         "title": f"Winners give back ~{gb}% of their best move",
                         "detail": "Trades reach good MFE then retrace before the trailing stop closes them. "
                                   "A tighter trail after +0.5R could bank more of each move."})
        if can_propose:
            proposals.append({
                "id": "tighten_trail_after_half_r",
                "title": "Tighten trailing stop once a trade reaches +0.5R",
                "rationale": f"Winners currently surrender ~{gb}% of peak. Locking earlier converts MFE into realised R.",
                "path": "trading.tradeManagement.trailTightenAfterR",
                "suggest": 0.5, "current_hint": "off",
                "risk": "medium", "confidence": conf_tag})

    # 5) best/worst strategy & session (informational unless strong sample)
    for dim, label in (("byStrategy", "strategy"), ("bySession", "session")):
        d = stats.get(dim) or {}
        ranked = [(k, v) for k, v in d.items() if v.get("n", 0) >= 3]
        if len(ranked) >= 2:
            ranked.sort(key=lambda kv: kv[1].get("net", 0), reverse=True)
            best, worst = ranked[0], ranked[-1]
            sev = "info" if low else "warn"
            findings.append({"severity": sev, "confidence": conf_tag,
                             "title": f"Best {label}: {best[0]} ({best[1]['net']:+}) · weakest: {worst[0]} ({worst[1]['net']:+})",
                             "detail": f"{best[0]} {best[1]['winRate']}% WR / {best[1]['avgR']}R (n={best[1]['n']}); "
                                       f"{worst[0]} {worst[1]['winRate']}% WR / {worst[1]['avgR']}R (n={worst[1]['n']}). "
                                       + ("Sample too small to act on — informational only." if not can_propose else
                                          "Consider down-weighting the weakest if this holds.")})

    verdict = _verdict(stats, n, can_propose)
    return {"findings": findings, "proposals": proposals, "sampleSize": n,
            "sampleConfidence": conf_tag, "canPropose": can_propose, "verdict": verdict}


def _verdict(stats: dict[str, Any], n: int, can_propose: bool) -> str:
    if not can_propose:
        return (f"{n} trades reviewed. Findings shown are directional only — below {MIN_SAMPLE_PROPOSAL} "
                f"trades any pattern is likely noise, so no config changes are proposed. Keep collecting.")
    ratio = _f(stats.get("lossWinSizeRatio"))
    if _f(stats.get("netUsd")) > 0 and ratio >= 2.5:
        return ("Expectancy is positive but fragile: it rests on win rate while a few oversized losers "
                "do most of the damage. The highest-value fix is loss control, not entries.")
    if _f(stats.get("netUsd")) <= 0:
        return "Expectancy is not yet positive. Fix management/loss-control before changing entries or sizing."
    return "Expectancy is positive and losses are proportionate. Maintain discipline; avoid over-tuning."


def build_llm_prompt(stats: dict[str, Any], deterministic: dict[str, Any]) -> str:
    """Compact prompt for the optional LLM layer. It reads AGGREGATES ONLY — never raw trades —
    so it cannot overfit to individual outcomes."""
    lines = [
        "You are a trading-systems reviewer for an XAUUSD M5 scalping bot. You are given "
        "DETERMINISTIC aggregate statistics (not individual trades). Do not invent patterns not "
        "supported by the numbers. If the sample is small, say so and refuse to over-conclude.",
        "",
        f"Sample size: {stats.get('sampleSize')} trades (confidence: {deterministic.get('sampleConfidence')}).",
        f"Win rate {stats.get('winRate')}%, net {stats.get('netUsd')} USD, profit factor {stats.get('profitFactor')}, "
        f"avg {stats.get('avgR')}R, expectancy {stats.get('expectancyUsd')} USD/trade.",
        f"Avg win {stats.get('avgWinUsd')} vs avg loss {stats.get('avgLossUsd')} (loss/win size {stats.get('lossWinSizeRatio')}x).",
        f"Winner giveback {stats.get('winnerGivebackPct')}%, deep losers (< -1R) {stats.get('deepLoserCount')}.",
        f"By strategy: {stats.get('byStrategy')}",
        f"By session: {stats.get('bySession')}",
        f"By confidence: {stats.get('byConfidence')}",
        "",
        "Deterministic findings already computed:",
    ]
    for f in deterministic.get("findings", []):
        lines.append(f"- [{f.get('severity')}] {f.get('title')}")
    lines += [
        "",
        "Write: (1) a 2-3 sentence plain-English diagnosis of the single biggest issue, "
        "(2) up to 3 concrete, testable adjustments phrased as PROPOSALS the human must approve, "
        "each with the setting to change and why. Never claim certainty on a small sample.",
    ]
    return "\n".join(lines)
