"""AI strategy-candidate generator — Claude (Anthropic) or ChatGPT (OpenAI).
import logging

Asks the configured LLM to propose new candidate trading-STYLE *profiles* for the Strategy Lab.
The LLM only ever returns parameter profiles (the same safe shape as the curated library) — it
tunes/combines existing rule parameters, it NEVER writes or runs code. Every field the model
returns is strictly whitelisted and clamped to a safe range here before it can enter the candidate
pool, and each candidate is then backtested on the user's data and requires the user's click to
install. So a bad model output can, at worst, propose a safe-but-mediocre profile that the
backtest then rejects.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any
from .safe_http import read_public_https, validate_public_https_url

# The ONLY keys a generated profile may contain, with safe clamps / allowed values.
_ALLOWED_SESSIONS = ["Asia", "London", "London / New York", "New York"]
_NUM_BOUNDS = {
    "scoutConfidence": (50.0, 92.0), "standardConfidence": (55.0, 95.0),
    "sniperConfidence": (60.0, 98.0), "minRiskReward": (1.0, 3.5),
    "maxSpread": (0.15, 1.0), "minEfficiencyRatio": (0.15, 0.6),
    "minConfluence": (1.0, 8.0),
}
_MODES = {"relaxed", "balanced", "strict", "sniper"}

SCHEMA_HINT = (
    "Each profile object MUST be: {\"id\": short_snake_case, \"name\": short title, "
    "\"thesis\": one sentence why it could work, \"profile\": { optional subset of: "
    "strictnessMode (relaxed|balanced|strict|sniper), scoutConfidence (50-92), "
    "standardConfidence (55-95), sniperConfidence (60-98), minRiskReward (1.0-3.5), "
    "maxSpread (0.15-1.0), minEfficiencyRatio (0.15-0.6), minConfluence (1-8), "
    "allowScoutEntries (true|false), allowedSessions (subset of [Asia, London, "
    "\"London / New York\", New York]) } }. Return ONLY a JSON array of such objects. "
    "No code, no prose, no extra keys."
)


def sanitize_profile(raw: dict[str, Any], source: str = "ai") -> dict[str, Any] | None:
    """Strictly whitelist + clamp an externally-proposed candidate (LLM or trusted feed). Returns
    a clean candidate or None. This is the security boundary: anything not explicitly allowed is
    dropped — applied to feed candidates too, so even a compromised 'trusted' URL can't inject
    code or out-of-range parameters."""
    if not isinstance(raw, dict):
        return None
    source = re.sub(r"[^a-z]", "", str(source).lower()) or "ext"
    rid = re.sub(r"[^a-z0-9_]", "", str(raw.get("id", "")).lower().replace(" ", "_"))[:40]
    name = str(raw.get("name", "") or rid or "AI candidate")[:60]
    thesis = str(raw.get("thesis", ""))[:200]
    src_prof = raw.get("profile") if isinstance(raw.get("profile"), dict) else {}
    prof: dict[str, Any] = {}
    for k, v in src_prof.items():
        if k == "strictnessMode" and str(v).lower() in _MODES:
            prof[k] = str(v).lower()
        elif k == "allowScoutEntries":
            prof[k] = bool(v)
        elif k == "allowedSessions" and isinstance(v, list):
            sess = [s for s in v if s in _ALLOWED_SESSIONS]
            if sess:
                prof[k] = sess
        elif k in _NUM_BOUNDS:
            try:
                lo, hi = _NUM_BOUNDS[k]
                prof[k] = round(max(lo, min(hi, float(v))), 3)
            except Exception:
                continue
        # anything else (incl. any "code"/"rule"/unknown key) is silently dropped
    if not rid or not prof:
        return None
    return {"id": f"{source}_{rid}"[:43], "name": name, "thesis": thesis, "source": source, "profile": prof}


def _build_request(provider: str, api_key: str, model: str, prompt: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Return (url, headers, body) for the chosen provider — Anthropic or OpenAI shape."""
    sys_msg = ("You are a quantitative trading assistant for an XAUUSD (Gold) M15 bot. You propose "
               "candidate trading-STYLE parameter profiles only. " + SCHEMA_HINT)
    if provider == "openai":
        # V12.55: use the current Responses API first. The parser below still supports
        # the older Chat Completions response shape for backwards compatibility.
        return (
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            {"model": model or "gpt-4.1-mini", "temperature": 0.2, "store": False,
             "instructions": sys_msg, "input": prompt, "max_output_tokens": 1600},
        )
    # default: anthropic / claude
    return (
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        {"model": model or "claude-sonnet-4-6", "max_tokens": 1500, "temperature": 0.7,
         "system": sys_msg, "messages": [{"role": "user", "content": prompt}]},
    )


def _extract_text(provider: str, data: dict[str, Any]) -> str:
    if provider == "openai":
        # Responses API shape
        out = ""
        for item in data.get("output", []) or []:
            for c in item.get("content", []) or []:
                if isinstance(c, dict) and c.get("type") in {"output_text", "text"}:
                    out += c.get("text", "")
        if out:
            return out
        # Legacy Chat Completions shape
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
    blocks = data.get("content") or []
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict)) if isinstance(blocks, list) else ""


def _parse_array(text: str) -> list[dict[str, Any]]:
    """Pull the JSON array out of the model text (tolerating ```json fences / surrounding prose)."""
    if not text:
        return []
    m = re.search(r"\[.*\]", text, re.DOTALL)
    blob = m.group(0) if m else text
    try:
        arr = json.loads(blob)
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def fetch_feed_candidates(url: str, key: str = "", timeout: float = 15.0,
                          _transport=None) -> dict[str, Any]:
    """Pull candidate PROFILES from a trusted strategy-feed URL (a JSON array, or {"candidates":[...]})
    and sanitize every one — same whitelist/clamp as the AI path, so a compromised feed still can't
    inject code or out-of-range parameters. ``_transport`` lets tests inject a fake HTTP layer."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "message": "No strategy feed URL configured."}
    try:
        if _transport is not None:
            data = _transport(url, key)
        else:
            validate_public_https_url(url)
            u = url + (("&" if "?" in url else "?") + "apikey=" + key) if key else url
            headers = {"User-Agent": "GodModeGoldBot/1.0"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            req = urllib.request.Request(u, headers=headers)
            data = json.loads(read_public_https(req, timeout=timeout).decode("utf-8", "ignore"))
    except Exception as exc:
        return {"ok": False, "message": f"Strategy feed fetch failed: {exc}"}
    items = data.get("candidates", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return {"ok": False, "message": "Strategy feed did not return a JSON array of candidates."}
    clean = [c for c in (sanitize_profile(r, source="feed") for r in items) if c]
    return {"ok": True, "candidates": clean, "rawCount": len(items), "acceptedCount": len(clean)}


def generate_candidates(provider: str, api_key: str, model: str, context: dict[str, Any],
                        n: int = 3, timeout: float = 30.0,
                        _transport=None) -> dict[str, Any]:
    """Ask the LLM for up to n candidate profiles, then sanitize them. ``_transport`` lets tests
    inject a fake HTTP layer; in production it does a real HTTPS POST via urllib."""
    provider = (provider or "claude").lower()
    if provider not in ("claude", "anthropic", "openai"):
        return {"ok": False, "message": f"Unknown AI provider '{provider}'. Use 'claude' or 'openai'."}
    provider = "openai" if provider == "openai" else "claude"
    if not api_key:
        return {"ok": False, "message": "No API key configured. Add your Claude or OpenAI key in Settings → AI Strategy Generator."}
    prompt = (
        f"Propose {int(n)} NEW, distinct candidate trading-style profiles for this Gold M15 bot.\n"
        f"Current live config (baseline): {json.dumps(context.get('baseline', {}))}\n"
        f"Recent performance: {json.dumps(context.get('performance', {}))}\n"
        f"Goal: styles that could plausibly beat the baseline after costs in different regimes "
        f"(trend, range, news-heavy, session-specific). Be diverse. {SCHEMA_HINT}"
    )
    url, headers, body = _build_request(provider, api_key, model, prompt)
    data = None
    for attempt in range(3):   # retry transient rate-limit / overload with backoff
        try:
            if _transport is not None:
                data = _transport(url, headers, body)
            else:
                req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                             headers={"User-Agent": "GodModeGoldBot/1.0", **headers}, method="POST")
                data = json.loads(
                    read_public_https(req, timeout=timeout).decode(
                        "utf-8",
                        "ignore",
                    )
                )
            break
        except urllib.error.HTTPError as he:
            code = getattr(he, "code", 0)
            if code in (429, 503, 529) and attempt < 2:
                time.sleep(2 * (2 ** attempt))   # 2s, then 4s
                continue
            detail = ""
            try:
                detail = he.read().decode("utf-8", "ignore")[:160]
            except Exception as _suppressed_exc:
                logging.getLogger(__name__).warning("Recoverable failure in ai_strategy_gen.py:193: %s", _suppressed_exc)
            if code == 429:
                return {"ok": False, "rateLimited": True, "provider": provider,
                        "message": f"{provider.upper()} rate-limited the request (429) even after retries — your key is being throttled or is out of credits. Wait ~a minute and try again, or check your plan/billing at the provider. {detail}"}
            if code in (401, 403):
                return {"ok": False, "provider": provider,
                        "message": f"{provider.upper()} rejected the API key ({code}) — double-check the key (and that it has access to the model) in Settings → AI Strategy Generator. {detail}"}
            return {"ok": False, "provider": provider, "message": f"AI request failed: HTTP {code}. {detail}"}
        except Exception as exc:
            return {"ok": False, "message": f"AI request failed: {exc}", "provider": provider}
    if data is None:
        return {"ok": False, "provider": provider, "message": f"{provider.upper()} kept rate-limiting the request — try again shortly."}
    raw = _parse_array(_extract_text(provider, data))
    clean = [c for c in (sanitize_profile(r) for r in raw) if c]
    if not clean:
        return {"ok": False, "message": "The AI returned no valid candidate profiles (after safety validation).",
                "provider": provider, "rawCount": len(raw)}
    return {"ok": True, "provider": provider, "model": model, "candidates": clean,
            "rawCount": len(raw), "acceptedCount": len(clean)}
