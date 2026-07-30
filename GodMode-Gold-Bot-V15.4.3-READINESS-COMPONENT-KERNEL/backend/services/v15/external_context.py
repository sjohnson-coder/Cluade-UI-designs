from __future__ import annotations

import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from .contracts import clamp

_RISK_TERMS = {
    "emergency": 1.0, "rate decision": 0.9, "interest rate": 0.75, "inflation": 0.65,
    "federal reserve": 0.7, "bank of england": 0.7, "ecb": 0.65, "war": 0.9,
    "sanction": 0.8, "tariff": 0.6, "recession": 0.7, "jobs report": 0.55,
    "nonfarm": 0.65, "cpi": 0.65, "gold": 0.25, "dollar": 0.3,
}


class FreeExternalContext:
    DEFAULT_SOURCES = [
        ("rss", "https://www.federalreserve.gov/feeds/press_all.xml", "Federal Reserve"),
        ("rss", "https://www.bankofengland.co.uk/rss/news", "Bank of England"),
        ("rss", "https://www.ecb.europa.eu/rss/press.html", "European Central Bank"),
        ("gdelt", "https://api.gdeltproject.org/api/v2/doc/doc?query=gold%20OR%20federal%20reserve%20OR%20inflation&mode=artlist&format=json&maxrecords=20", "GDELT"),
    ]

    def __init__(self, cache_path: Path, ttl_seconds: int = 300):
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.sources = list(self.DEFAULT_SOURCES)
        self._lock = threading.RLock()
        self._refreshing = False

    def _normalise(self, source: str, payload: bytes, provider: str) -> list[dict[str, Any]]:
        if source == "rss":
            root = ET.fromstring(payload)
            nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            rows = []
            for item in nodes[:25]:
                title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                published = item.findtext("pubDate") or item.findtext("published") or item.findtext("updated") or ""
                rows.append({"title": title.strip(), "published": published.strip(), "provider": provider})
            return rows
        data = json.loads(payload.decode("utf-8"))
        articles = data.get("articles") or data.get("items") or []
        return [{"title": str(x.get("title") or ""), "published": str(x.get("seendate") or x.get("published") or ""), "provider": provider} for x in articles[:25]]

    @staticmethod
    def _risk(items: list[dict[str, Any]]) -> float:
        scores = []
        for item in items:
            title = re.sub(r"\s+", " ", str(item.get("title") or "").lower())
            score = max((weight for term, weight in _RISK_TERMS.items() if term in title), default=0.0)
            if score:
                scores.append(score)
        if not scores:
            return 0.0
        scores.sort(reverse=True)
        return clamp(sum(scores[:5]) / min(5, len(scores)))

    def refresh(self, fetcher: Callable[..., Any] | None = None) -> dict[str, Any]:
        fetcher = fetcher or self._default_fetcher
        with self._lock:
            if self._refreshing:
                cached = self.cached()
                cached["refresh_in_progress"] = True
                return cached
            self._refreshing = True
        try:
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            def fetch_one(row):
                source, url, provider = row
                response = fetcher(url, timeout=4)
                payload = response if isinstance(response, bytes) else getattr(response, "read", lambda: response)()
                return self._normalise(source, payload, provider)
            with ThreadPoolExecutor(max_workers=min(4, len(self.sources))) as pool:
                futures = {pool.submit(fetch_one, row): row for row in self.sources}
                for future in as_completed(futures):
                    source, _url, provider = futures[future]
                    try:
                        items.extend(future.result())
                    except Exception as exc:
                        errors.append(f"{provider}/{source}: {exc}")
            now = time.time()
            risk = self._risk(items)
            provider_count = len({x.get("provider") for x in items})
            uncertainty = clamp(1.0 - min(0.75, len(items) / 40 * 0.45 + provider_count / max(1, len(self.sources)) * 0.3)) if items else 1.0
            result = {"available": bool(items), "items": items[:60], "errors": errors, "risk_bias": risk, "uncertainty": uncertainty, "fetched_at": now, "fresh": bool(items), "providers": provider_count, "source_count": len(self.sources)}
            temp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temp.replace(self.cache_path)
            return result
        finally:
            with self._lock:
                self._refreshing = False

    @staticmethod
    def _default_fetcher(url: str, timeout: int = 4):
        import urllib.request
        from services.safe_http import read_public_https
        request = urllib.request.Request(url, headers={"User-Agent": "GodMode-V15/1.0"})
        return read_public_https(request, timeout=timeout)

    def cached(self) -> dict[str, Any]:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            data["fresh"] = time.time() - float(data.get("fetched_at", 0)) <= self.ttl_seconds
            return data
        except Exception:
            return {"available": False, "items": [], "errors": ["No cached external context"], "risk_bias": 0.0, "uncertainty": 1.0, "fresh": False, "providers": 0, "source_count": len(self.sources)}
