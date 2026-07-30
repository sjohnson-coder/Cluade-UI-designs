from __future__ import annotations
import logging
import csv, io, json, math, os, time, threading, urllib.error, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from .safe_http import read_public_https, validate_public_https_url

def utcnow(): return datetime.now(timezone.utc)

# V12.84: shared browser-style headers for EVERY feed fetch. Faireconomy (Cloudflare) and
# Yahoo commonly return 403 to bot-like User-Agents such as 'GodModeGoldBot/1.0' — which is
# exactly why the news card kept showing error_or_empty on live machines while the URL was
# perfectly configured. One constant, used by get_text AND all class fetches below.
_BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
    'Accept': 'application/json,text/xml,application/xml,text/plain,*/*',
}

def get_text(url: str, headers: dict[str,str] | None=None, timeout: float=4.0) -> str:
    # Some free feeds (Yahoo/Faireconomy/Alpha) reject bot-like user agents. Use a
    # browser-style UA by default and keep timeouts short so live decisions are not delayed.
    default_headers = dict(_BROWSER_HEADERS)
    if headers:
        default_headers.update(headers)
    validate_public_https_url(url)
    req = urllib.request.Request(url, headers=default_headers)
    return read_public_https(req, timeout=timeout).decode('utf-8', errors='replace')
def get_json(url: str, headers: dict[str,str] | None=None): return json.loads(get_text(url, headers))

def _append_query(url: str, params: dict[str, str]) -> str:
    parts = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    for k, v in params.items():
        if v and k not in q:
            q[k] = v
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))

def _apply_api_key(url: str, key: str | None) -> str:
    """Append/replace common API key parameters safely.

    Users often paste Alpha/FMP template URLs containing apikey=YOUR_KEY or demo,
    then put the real key in the API-key field. This must replace placeholders, not
    silently keep the bad query string.
    """
    key = (key or '').strip()
    if not key:
        return url
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    low_keys = {k.lower(): i for i, (k, _v) in enumerate(pairs)}
    for candidate in ('apikey', 'api_key', 'token'):
        if candidate in low_keys:
            i = low_keys[candidate]
            old = str(pairs[i][1] or '').strip().lower()
            if old in {'', 'demo', 'your_key', 'your_api_key', 'apikey', 'api_key', 'key', 'xxx', 'xxxx'} or key:
                pairs[i] = (pairs[i][0], key)
            break
    else:
        pairs.append(('apikey', key))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(pairs), parts.fragment))

class EconomicCalendarAPI:
    def __init__(self):
        self.before=int(os.getenv('GODMODE_NEWS_BLACKOUT_BEFORE_MINUTES','30')); self.after=int(os.getenv('GODMODE_NEWS_BLACKOUT_AFTER_MINUTES','30'))
        self._cache=None; self._cache_at=0.0; self._last_error=''; self._failure_count=0; self._last_error_at=0.0; self._error_backoff=60.0; self._failure_count=0; self._refreshing=False; self._lock=threading.Lock(); self.ttl=max(300, int(os.getenv('GODMODE_ECONOMIC_CALENDAR_TTL_SECONDS','900') or 900))
        # V12.77 NEWS FIX: url/key used to read ONLY environment variables, so a calendar URL
        # saved in Settings 12c updated settings.json and nothing else — the feed stayed
        # "not_configured" forever no matter how many times you saved. Settings now override env.
        self._url_override=''; self._key_override=''
    def configure(self, url='', key='', before=None, after=None):
        changed = (url or '').strip() != self._url_override or (key or '').strip() != self._key_override
        self._url_override=(url or '').strip(); self._key_override=(key or '').strip()
        if before is not None:
            try:
                value=int(before)
            except (TypeError, ValueError) as exc:
                raise ValueError('newsBlackoutBeforeMinutes must be an integer between 0 and 240') from exc
            if not 0 <= value <= 240:
                raise ValueError('newsBlackoutBeforeMinutes must be between 0 and 240')
            self.before=value
        if after is not None:
            try:
                value=int(after)
            except (TypeError, ValueError) as exc:
                raise ValueError('newsBlackoutAfterMinutes must be an integer between 0 and 240') from exc
            if not 0 <= value <= 240:
                raise ValueError('newsBlackoutAfterMinutes must be between 0 and 240')
            self.after=value
        if changed:
            self.force_refresh()   # a new URL must be fetched immediately, not after the TTL
    def force_refresh(self):
        self._cache=None; self._cache_at=0.0; self._last_error=''
    @property
    def key(self):
        return (self._key_override or os.getenv('GODMODE_ECONOMIC_CALENDAR_KEY','').strip() or os.getenv('ECONOMIC_CALENDAR_KEY','').strip())
    @property
    def url(self):
        return (self._url_override or os.getenv('GODMODE_ECONOMIC_CALENDAR_URL','').strip() or os.getenv('ECONOMIC_CALENDAR_URL','').strip())
    def events(self):
        """Return cached events immediately and refresh off-thread.

        UI/status polling must never perform blocking Internet I/O. A single-flight worker
        refreshes at most once per TTL, with exponential 429/outage backoff and stale-cache use.
        """
        if not self.url:
            return []
        now=time.time()
        fresh=self._cache is not None and now-self._cache_at < self.ttl
        cooling=self._last_error and now-self._last_error_at < self._error_backoff
        if not fresh and not cooling and not self._refreshing:
            with self._lock:
                if not self._refreshing:
                    self._refreshing=True
                    threading.Thread(target=self._refresh_worker, name='godmode-calendar-feed', daemon=True).start()
        return list(self._cache) if self._cache else []

    def refresh_now(self) -> list[dict[str, Any]]:
        """Perform one synchronous refresh for explicit user/API diagnostics.

        Normal dashboard polling stays cached/background; first-load and Tools tests can request
        deterministic data instead of receiving an empty list while a daemon thread starts.
        """
        with self._lock:
            if self._refreshing:
                return (self._cache or [])
            self._refreshing = True
        self._refresh_worker()
        return (self._cache or [])

    def _refresh_worker(self):
        now=time.time(); out=[]
        try:
            url=self.url; headers=dict(_BROWSER_HEADERS)
            if self.key: url=_apply_api_key(url,self.key)
            raw=get_json(url,headers); data=raw
            if isinstance(raw,dict):
                for k in ('events','data','calendar','results','items'):
                    if isinstance(raw.get(k),list): data=raw.get(k); break
            if not isinstance(data,list): data=[]
            for i,e in enumerate(data[:240]):
                if not isinstance(e,dict): continue
                title=(e.get('title') or e.get('event') or e.get('name') or e.get('indicator') or e.get('release') or f'Economic Event {i+1}')
                impact_raw=str(e.get('impact') or e.get('importance') or e.get('Importance') or e.get('impact_level') or '').strip().lower()
                ccy=str(e.get('currency') or e.get('country') or e.get('Country') or e.get('countryCode') or 'USD').strip().upper()
                if ccy in {'UNITED STATES','US','USA','UNITED STATES OF AMERICA'}: ccy='USD'
                t=(e.get('time') or e.get('date') or e.get('datetime') or e.get('timestamp') or e.get('Date') or e.get('releaseDate'))
                if (not t or str(t).lower() in {'none','null',''}) and e.get('date') and e.get('hour'): t=f"{e.get('date')} {e.get('hour')}"
                dt=self._parse(t)
                if 'high' in impact_raw or impact_raw in {'3','red','important'}: impact='high'
                elif 'medium' in impact_raw or impact_raw in {'2','orange','moderate'}: impact='medium'
                elif 'low' in impact_raw or impact_raw in {'1','yellow'}: impact='low'
                else:
                    tl=str(title).lower(); impact='high' if any(k in tl for k in ('fomc','federal reserve','fed ','cpi','inflation','nfp','nonfarm','payroll','rate decision','pce')) else 'medium'
                out.append({'id':e.get('id') or f'event-{i+1}','title':str(title),'currency':ccy,'impact':impact,'timeUtc':dt.isoformat(),'actual':e.get('actual') or e.get('Actual'),'forecast':e.get('forecast') or e.get('Forecast'),'previous':e.get('previous') or e.get('Previous'),'source':'live_api'})
            self._cache=out; self._cache_at=time.time(); self._last_error=''; self._failure_count=0; self._error_backoff=60.0
        except Exception as exc:
            self._failure_count+=1; self._last_error=str(exc); self._last_error_at=now
            is429=isinstance(exc,urllib.error.HTTPError) and getattr(exc,'code',0)==429
            base=300.0 if is429 else 60.0
            self._error_backoff=min(1800.0, base*(2**min(self._failure_count-1,4)))
            logging.getLogger(__name__).warning('Calendar feed unavailable; cached data retained, retry in %.0fs: %s',self._error_backoff,exc)
        finally:
            self._refreshing=False

    def _parse(self, v):
        if isinstance(v,(int,float)):
            # handle ms timestamps too
            val=float(v); val = val/1000.0 if val > 100000000000 else val
            return datetime.fromtimestamp(val, tz=timezone.utc)
        if isinstance(v,str):
            txt=v.strip()
            if txt:
                # ISO-8601 is the dominant live-feed format and may include an offset.
                # Try it first so valid timestamps do not generate one warning per rejected
                # legacy format. Expected parse misses are normal and remain silent.
                try:
                    d=datetime.fromisoformat(txt.replace('Z','+00:00').replace(' UTC','+00:00'))
                    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    logging.getLogger(__name__).debug("Calendar timestamp is not ISO-8601; trying legacy formats")
                for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%m-%d-%Y %H:%M:%S','%m-%d-%Y %H:%M','%d-%m-%Y %H:%M:%S','%d-%m-%Y %H:%M'):
                    try:
                        return datetime.strptime(txt, fmt).replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError):
                        continue
                logging.getLogger(__name__).warning("Unsupported economic-calendar timestamp %r; using safe fallback", txt)
        return utcnow()+timedelta(hours=2)

    def _fallback(self, source):
        b=utcnow().replace(second=0,microsecond=0)
        return [{'id':'usd-cpi','title':'US CPI / Inflation Watch','currency':'USD','impact':'high','timeUtc':(b+timedelta(hours=3)).isoformat(),'actual':None,'forecast':None,'previous':None,'source':source},{'id':'usd-fomc','title':'FOMC / Fed Speaker Risk','currency':'USD','impact':'high','timeUtc':(b+timedelta(hours=7)).isoformat(),'actual':None,'forecast':None,'previous':None,'source':source},{'id':'usd-claims','title':'US Jobless Claims','currency':'USD','impact':'medium','timeUtc':(b+timedelta(days=1,hours=1)).isoformat(),'actual':None,'forecast':None,'previous':None,'source':source}]
    def blackout_status(self):
        now=utcnow(); active=[]; nxt=None
        for e in self.events():
            dt=self._parse(e.get('timeUtc')); delta=(dt-now).total_seconds()/60
            if e.get('currency')=='USD' and e.get('impact')=='high':
                if -self.after <= delta <= self.before: active.append({**e,'minutesToEvent':round(delta,1)})
                if delta>=0 and (not nxt or delta < nxt.get('minutesToEvent',1e9)): nxt={**e,'minutesToEvent':round(delta,1)}
        return {'blackoutActive':bool(active),'activeEvents':active,'nextHighImpactUsdEvent':nxt,'beforeMinutes':self.before,'afterMinutes':self.after,'decision':'BLOCK_NEW_TRADES' if active else 'CLEAR'}

    def status(self):
        ev=self.events(); blk=self.blackout_status(); next_event=blk.get('nextHighImpactUsdEvent')
        stale = bool(self._last_error) and bool(self._cache)
        if not self.url:
            status='not_configured'; detail='No economic calendar URL configured.'
        elif ev and stale:
            status='live_stale'
            detail=f'{len(ev)} event(s) from last good fetch; refresh failing. News protection still active. Last error: {self._last_error}'
        elif ev:
            status='live'; detail=f'{len(ev)} event(s) loaded.'
        elif self._last_error:
            # V12.82: only call it an error if a fetch actually FAILED. A configured feed that
            # simply returned no events right now (weekends, between async fetch fire/return) is
            # NOT an error and must not flicker the dashboard to a red "off" state.
            status='error_or_empty'; detail='Calendar URL configured but the last fetch failed. Last error: '+self._last_error
        else:
            # Configured, reachable, just quiet (no high-impact events in the window / market closed).
            status='live_quiet'; detail='Calendar configured and active — no events in the current window (e.g. weekend/market closed).'
        return {'configured': bool(self.url), 'status': status, 'detail': detail, 'eventsLoaded': len(ev),
                # 'active' means "wired and working" for the dashboard dot: green when configured
                # and not in a hard-error state, regardless of whether events exist right now.
                'active': bool(self.url) and status in ('live', 'live_stale', 'live_quiet'),
                'blackoutActive': blk.get('blackoutActive', False), 'nextHighImpactUsdEvent': next_event, 'stale': stale, 'lastError': self._last_error,
                'beforeMinutes': self.before, 'afterMinutes': self.after}

class MarketNewsAPI:
    """Generic live market-news adapter for dashboard visibility.

    Recommended Alpha Vantage URL:
      https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_macro,economy_monetary,financial_markets&sort=LATEST&limit=20
    Put the API key in GODMODE_MARKET_NEWS_KEY or append apikey=... to the URL.
    Accepts Alpha Vantage (feed[]), FMP/generic arrays, or {items/news/articles/data:[...]} JSON.
    Informational only by default — it does NOT override the economic calendar blackout gate.
    """
    def __init__(self):
        self._cache=None; self._cache_at=0.0; self._last_error=''; self._last_error_at=0.0; self._error_backoff=60.0; self._failure_count=0; self._refreshing=False; self._lock=threading.Lock(); self.ttl=max(300, int(os.getenv('GODMODE_MARKET_NEWS_TTL_SECONDS','900') or 900))
        self._url_override=''; self._key_override=''   # V12.77: Settings override env
    def configure(self, url='', key=''):
        changed = (url or '').strip() != self._url_override or (key or '').strip() != self._key_override
        self._url_override=(url or '').strip(); self._key_override=(key or '').strip()
        if changed: self.force_refresh()
    @property
    def key(self):
        return (self._key_override or os.getenv('GODMODE_MARKET_NEWS_KEY','').strip() or os.getenv('MARKET_NEWS_KEY','').strip())
    @property
    def url(self):
        return (self._url_override or os.getenv('GODMODE_MARKET_NEWS_URL','').strip() or os.getenv('MARKET_NEWS_URL','').strip())
    def force_refresh(self):
        self._cache=None; self._cache_at=0.0; self._last_error=''; self._failure_count=0
    def headlines(self, limit=8):
        if not self.url: return []
        now=time.time(); fresh=self._cache is not None and now-self._cache_at < self.ttl
        cooling=self._last_error and now-self._last_error_at < self._error_backoff
        if not fresh and not cooling and not self._refreshing:
            with self._lock:
                if not self._refreshing:
                    self._refreshing=True
                    threading.Thread(target=self._refresh_worker, name='godmode-market-news', daemon=True).start()
        return (self._cache or [])[:max(1,min(int(limit or 8),30))]

    def refresh_now(self) -> list[dict[str, Any]]:
        """Perform one synchronous refresh for explicit user/API diagnostics.

        Normal dashboard polling stays cached/background; first-load and Tools tests can request
        deterministic data instead of receiving an empty list while a daemon thread starts.
        """
        with self._lock:
            if self._refreshing:
                return (self._cache or [])
            self._refreshing = True
        self._refresh_worker()
        return (self._cache or [])

    def _refresh_worker(self):
        now=time.time()
        try:
            url=self.url; headers=dict(_BROWSER_HEADERS)
            if self.key: url=_apply_api_key(url,self.key)
            text=get_text(url,headers); raw=None; data=[]
            try: raw=json.loads(text)
            except Exception: raw=None
            if isinstance(raw,dict):
                api_msg=raw.get('Information') or raw.get('Note') or raw.get('Error Message') or raw.get('message')
                if api_msg and not any(isinstance(raw.get(k),list) for k in ('feed','items','news','articles','data','results')):
                    raise RuntimeError(str(api_msg)[:300])
                data=raw.get('feed') or raw.get('items') or raw.get('news') or raw.get('articles') or raw.get('data') or raw.get('results') or []
            elif isinstance(raw,list): data=raw
            else: data=self._parse_rss(text)
            out=[]
            for i,n in enumerate(data[:30] if isinstance(data,list) else []):
                if not isinstance(n,dict): continue
                title=n.get('title') or n.get('headline') or n.get('name') or f'Market headline {i+1}'
                source=n.get('source') or n.get('source_name') or n.get('publisher') or n.get('site') or 'market_news'
                out.append({'id':n.get('id') or f'news-{i+1}','title':str(title)[:220],'source':source,'url':n.get('url') or n.get('link') or n.get('article_url') or '', 'time':n.get('time_published') or n.get('publishedAt') or n.get('publishedDate') or n.get('date') or n.get('datetime') or n.get('pubDate') or '', 'sentiment':n.get('overall_sentiment_label') or n.get('sentiment') or n.get('tone') or '', 'score':n.get('overall_sentiment_score') or n.get('sentiment_score') or n.get('score'), 'topics':n.get('topics') or n.get('category') or n.get('keywords') or []})
            self._cache=out; self._cache_at=time.time(); self._last_error=''; self._failure_count=0; self._error_backoff=60.0
        except Exception as exc:
            self._failure_count+=1; self._last_error=str(exc); self._last_error_at=now
            is429=isinstance(exc,urllib.error.HTTPError) and getattr(exc,'code',0)==429
            base=300.0 if is429 else 60.0
            self._error_backoff=min(1800.0,base*(2**min(self._failure_count-1,4)))
            logging.getLogger(__name__).warning('Market news unavailable; cached data retained, retry in %.0fs: %s',self._error_backoff,exc)
        finally:
            self._refreshing=False

    def _parse_rss(self, text: str) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(text.encode('utf-8'))
            items=[]
            # Work with RSS 2.0 and Atom-like namespaces by checking tag suffixes.
            for item in root.iter():
                if not str(item.tag).lower().endswith('item') and not str(item.tag).lower().endswith('entry'):
                    continue
                row={}
                for child in list(item):
                    tag=str(child.tag).split('}')[-1]
                    txt=(child.text or '').strip()
                    if tag in {'title','link','pubDate','published','updated','source','description'}:
                        if tag == 'published': tag='pubDate'
                        if tag == 'updated' and not row.get('pubDate'): tag='pubDate'
                        # Atom links can use href attribute.
                        if tag == 'link' and not txt:
                            txt = child.attrib.get('href','')
                        row[tag]=txt
                if row.get('title'):
                    items.append({'title':row.get('title'), 'url':row.get('link',''), 'time_published':row.get('pubDate',''), 'source':row.get('source') or 'rss_news'})
            return items
        except Exception as exc:
            raise ValueError(f'RSS/XML parse failed: {exc}') from exc
    def status(self):
        items=self.headlines(8)
        if not self.url:
            return {'configured': False, 'status':'not_configured', 'headlinesLoaded':0, 'latestHeadline': None,
                    'detail':'No market news URL configured.'}
        if items:
            return {'configured': True, 'status':'live', 'headlinesLoaded':len(items), 'latestHeadline':items[0],
                    'detail':f'{len(items)} headline(s) loaded.'}
        return {'configured': True, 'status':'error_or_empty', 'headlinesLoaded':0, 'latestHeadline': None,
                'detail':('Market news URL is configured but returned no parseable headlines.' + ((' Last error: '+self._last_error) if self._last_error else ''))}

class MacroFeed:
    NEUTRAL_BAND = 0.05
    CACHE_TTL_SECONDS = 60.0
    MAX_STALE_SECONDS = 1800.0
    INITIAL_BACKOFF_SECONDS = 60.0
    MAX_BACKOFF_SECONDS = 900.0

    def __init__(self):
        self._last_errors: dict[str, str] = {}
        self._cfg = {"dxyUrl": "", "us10yUrl": "", "dxyKey": "", "us10yKey": ""}
        self._cache: dict[str, dict[str, Any]] = {}
        self._locks = {"DXY": threading.Lock(), "US10Y": threading.Lock()}
        self._backoff_until = {"DXY": 0.0, "US10Y": 0.0}
        self._backoff_seconds = {"DXY": self.INITIAL_BACKOFF_SECONDS, "US10Y": self.INITIAL_BACKOFF_SECONDS}

    def configure(self, dxy_url='', us10y_url='', dxy_key='', us10y_key=''):
        new_cfg = {"dxyUrl": (dxy_url or '').strip(), "us10yUrl": (us10y_url or '').strip(),
                   "dxyKey": (dxy_key or '').strip(), "us10yKey": (us10y_key or '').strip()}
        if new_cfg != self._cfg:
            self._cfg = new_cfg
            self.force_refresh()

    def force_refresh(self):
        self._last_errors = {}
        self._cache = {}
        self._backoff_until = {"DXY": 0.0, "US10Y": 0.0}
        self._backoff_seconds = {"DXY": self.INITIAL_BACKOFF_SECONDS, "US10Y": self.INITIAL_BACKOFF_SECONDS}
        return None

    def snapshot(self):
        dxy_url=(self._cfg.get('dxyUrl') or os.getenv('GODMODE_DXY_URL','').strip() or os.getenv('DXY_FEED_URL','').strip())
        us10y_url=(self._cfg.get('us10yUrl') or os.getenv('GODMODE_US10Y_URL','').strip() or os.getenv('US10Y_FEED_URL','').strip())
        dxy_key=(self._cfg.get('dxyKey') or os.getenv('GODMODE_DXY_KEY','').strip() or os.getenv('DXY_FEED_KEY','').strip())
        us10y_key=(self._cfg.get('us10yKey') or os.getenv('GODMODE_US10Y_KEY','').strip() or os.getenv('US10Y_FEED_KEY','').strip())
        dxy=self._one('DXY', dxy_url, dxy_key, 104.21)
        us10y=self._one('US10Y', us10y_url, us10y_key, 4.28)
        score=50; reasons=[]; live=[]
        for feed,sup,pres,wt in ((dxy,'DXY softening supports gold upside','DXY strengthening pressures gold',(18,14)),
                                 (us10y,'US10Y yield softening supports gold','US10Y yield rising pressures gold',(16,12))):
            if feed['status'] not in {'live','stale_live'}:
                continue
            live.append(feed['symbol']); chg=feed['changePct']
            if chg < -self.NEUTRAL_BAND: score+=wt[0]; reasons.append(sup)
            elif chg > self.NEUTRAL_BAND: score-=wt[1]; reasons.append(pres)
            else: reasons.append(f"{feed['symbol']} flat — no macro tilt")
        if not live:
            reasons=['No live macro feed configured — NEUTRAL (no tilt). Set DXY/US10Y feed URLs in Settings → Data Feeds for live context.']
        score=max(0,min(100,score))
        return {'dxy':dxy,'us10y':us10y,'goldBias':'BULLISH_GOLD' if score>=62 else 'BEARISH_GOLD' if score<=42 else 'NEUTRAL_GOLD','goldBiasScore':score,'reasons':reasons,'feedStatus':'live' if live else 'not_configured','liveFeeds':live,'timestampUtc':utcnow().isoformat()}

    def _stale_or_fallback(self, name: str, fv: float, detail: str) -> dict[str, Any]:
        cached = self._cache.get(name) or {}
        age = max(0.0, time.time() - float(cached.get('_cachedAt', 0.0) or 0.0))
        if cached and age <= self.MAX_STALE_SECONDS:
            row = {k:v for k,v in cached.items() if not k.startswith('_')}
            row.update(status='stale_live', stale=True, staleAgeSeconds=round(age,1), detail=detail)
            return row
        return {'symbol':name,'value':fv,'changePct':0.0,'source':'fallback_after_api_error','status':'fallback','detail':detail}

    def _one(self, name,url,key,fv):
        if not url:
            return {'symbol':name,'value':fv,'changePct':0.0,'source':'local_fallback_no_api_configured','status':'fallback'}
        now=time.time()
        cached=self._cache.get(name) or {}
        age=now-float(cached.get('_cachedAt',0.0) or 0.0)
        if cached and age <= self.CACHE_TTL_SECONDS:
            row={k:v for k,v in cached.items() if not k.startswith('_')}
            row.update(cached=True, cacheAgeSeconds=round(age,1))
            return row
        if now < float(self._backoff_until.get(name,0.0) or 0.0):
            wait=max(0.0,self._backoff_until[name]-now)
            return self._stale_or_fallback(name,fv,f'Provider backoff active for {wait:.0f}s after rate-limit/error.')
        lock=self._locks.setdefault(name,threading.Lock())
        if not lock.acquire(blocking=False):
            return self._stale_or_fallback(name,fv,'Macro refresh already in progress; serving last-known-good value.')
        try:
            headers=dict(_BROWSER_HEADERS)
            if key:
                url = _apply_api_key(url, key)
            text=get_text(url,headers)
            val,chg=self._parse(text)
            row={'symbol':name,'value':val,'changePct':chg,'source':'live_api','status':'live'}
            self._cache[name]={**row,'_cachedAt':time.time()}
            self._last_errors.pop(name,None)
            self._backoff_until[name]=0.0
            self._backoff_seconds[name]=self.INITIAL_BACKOFF_SECONDS
            return row
        except Exception as exc:
            detail=str(exc)
            self._last_errors[name]=detail
            is_429=isinstance(exc,urllib.error.HTTPError) and getattr(exc,'code',None)==429 or '429' in detail or 'too many request' in detail.lower()
            if is_429:
                delay=float(self._backoff_seconds.get(name,self.INITIAL_BACKOFF_SECONDS))
                self._backoff_until[name]=time.time()+delay
                self._backoff_seconds[name]=min(self.MAX_BACKOFF_SECONDS,delay*2.0)
                detail=f'HTTP 429 rate limited; retry suppressed for {delay:.0f}s. {detail}'
            else:
                delay=min(120.0,float(self._backoff_seconds.get(name,self.INITIAL_BACKOFF_SECONDS)))
                self._backoff_until[name]=time.time()+delay
            return self._stale_or_fallback(name,fv,detail)
        finally:
            lock.release()

    def _parse(self,text):
        def num(x):
            try:
                if x is None: return None
                sx=str(x).strip().replace('%','').replace(',','')
                if sx.lower() in {'','none','null','nan','-'}: return None
                return float(sx)
            except Exception:
                return None
        def pct_from(cur, prev):
            cur=num(cur); prev=num(prev)
            if cur is None: return None
            if prev not in (None, 0): return (cur-prev)/prev*100.0
            return 0.0
        def walk(obj):
            if isinstance(obj, dict):
                # Yahoo chart shape: chart.result[0].meta.regularMarketPrice/chartPreviousClose
                meta=obj.get('meta') if isinstance(obj.get('meta'), dict) else obj
                if isinstance(meta, dict):
                    v = num(meta.get('regularMarketPrice') or meta.get('price') or meta.get('value') or meta.get('last') or meta.get('close'))
                    if v is not None:
                        c = num(meta.get('regularMarketChangePercent') or meta.get('changePercent') or meta.get('changesPercentage') or meta.get('changePct') or meta.get('percentChange'))
                        if c is None:
                            c = pct_from(v, meta.get('chartPreviousClose') or meta.get('previousClose') or meta.get('regularMarketPreviousClose'))
                        return v, float(c or 0.0)
                # Alpha Treasury data rows / generic quote shapes.
                keys_price=('price','value','close','last','rate','regularMarketPrice','bid','ask')
                keys_change=('changePercent','changesPercentage','changePct','change','regularMarketChangePercent','percentChange')
                v=next((obj.get(k) for k in keys_price if obj.get(k) not in (None,'')), None)
                c=next((obj.get(k) for k in keys_change if obj.get(k) not in (None,'')), None)
                vv=num(v)
                if vv is not None:
                    cc=num(c)
                    if cc is None:
                        cc=pct_from(vv, obj.get('previousClose') or obj.get('prevClose') or obj.get('previous') or obj.get('prior'))
                    return vv, float(cc or 0.0)
                # include common nested containers from Yahoo/Alpha/FMP/TwelveData
                for k in ('chart','result','Global Quote','globalQuote','quote','meta','data','results','values','historical','items','indicators'):
                    if k in obj:
                        r=walk(obj[k])
                        if r: return r
            if isinstance(obj, list) and obj:
                # If this is a time-series list with value/close rows, calculate latest change from previous row.
                parsed=[]
                sample = obj if len(obj) <= 10 else (obj[:5] + obj[-5:])
                for item in sample:
                    r=walk(item)
                    if r: parsed.append(r)
                if parsed:
                    # Prefer first two values (Alpha daily latest-first), otherwise last two (CSV/oldest-first).
                    if len(parsed) >= 2:
                        v0,_=parsed[0]; v1,_=parsed[1]
                        return v0, pct_from(v0, v1) or 0.0
                    return parsed[0]
            return None
        try:
            raw=json.loads(text)
            # Alpha Vantage can return Note/Information/Error Message when limit/key fails.
            if isinstance(raw, dict):
                msg = raw.get('Information') or raw.get('Note') or raw.get('Error Message')
                if msg and not any(k in raw for k in ('data','chart','Global Quote','values','results')):
                    raise ValueError(str(msg)[:300])
            r=walk(raw)
            if r: return r
        except Exception as exc:
            # Fall through to CSV; if CSV also fails, raise a useful error.
            json_exc = exc
        else:
            json_exc = None
        try:
            rows=list(csv.DictReader(io.StringIO(text)))
            if not rows: raise ValueError('No CSV rows')
            # FRED/stooq/Yahoo CSV often use Close, DGS10, value, price, last.
            numeric_keys=[]
            for k in rows[-1].keys():
                kl=k.lower()
                if kl in {'close','value','price','last','rate','dgs10','dx.f'} or not {'date','time','timestamp'}.intersection({kl}):
                    if num(rows[-1].get(k)) is not None:
                        numeric_keys.append(k)
            key = numeric_keys[-1] if numeric_keys else next((k for k in rows[-1] if num(rows[-1].get(k)) is not None), None)
            if not key: raise ValueError('No numeric quote field in CSV')
            v=num(rows[-1].get(key))
            p=None
            for prior in reversed(rows[:-1]):
                p=num(prior.get(key))
                if p is not None: break
            return float(v), float(pct_from(v,p) or 0.0)
        except Exception as csv_exc:
            raise ValueError(f'No parseable JSON/XML/CSV quote rows. json={json_exc}; csv={csv_exc}')


class TickDataBacktester:
    def load_ticks(self,symbol='XAUUSD',source='mt5',csv_path=None,limit=5000):
        source=str(source or 'mt5').lower()
        if source=='csv':
            if not csv_path:
                raise ValueError('csvPath is required when source=csv')
            return self._csv(symbol,csv_path,limit)
        if source in {'synthetic','simulation','sample'}:
            return self._sample(symbol, min(limit,1200))
        if source!='mt5':
            raise ValueError(f"Unsupported tick source '{source}'. Use mt5, csv, or synthetic.")
        try:
            import MetaTrader5 as mt5
        except Exception as exc:
            raise RuntimeError(f'MT5 tick retrieval unavailable: MetaTrader5 import failed: {exc}') from exc
        initialized=False
        try:
            initialized=bool(mt5.initialize())
            if not initialized:
                raise RuntimeError(f'MT5 initialize failed: {mt5.last_error()}')
            ticks=mt5.copy_ticks_from(symbol, utcnow()-timedelta(days=5), int(limit), mt5.COPY_TICKS_ALL)
            if ticks is None:
                raise RuntimeError(f'MT5 copy_ticks_from failed: {mt5.last_error()}')
            if not len(ticks):
                raise RuntimeError(f'No MT5 ticks returned for {symbol}; verify symbol mapping and history availability')
            return {'symbol':symbol,'source':'mt5_live_terminal','sourceRequested':'mt5','syntheticFallback':False,'tickCount':len(ticks),'ticks':[{'time':int(t['time']),'bid':float(t['bid']),'ask':float(t['ask']),'last':float(t['last'] or t['bid'])} for t in ticks[:limit]]}
        finally:
            if initialized:
                try:
                    mt5.shutdown()
                except Exception as exc:
                    logging.getLogger("godmode.tick_backtest").warning("MT5 shutdown failed after tick retrieval: %s", exc, exc_info=True)

    def _csv(self,symbol,path,limit):
        p=Path(path)
        if not p.exists(): raise FileNotFoundError(f'CSV tick file not found: {path}')
        out=[]
        for i,row in enumerate(csv.DictReader(p.open(encoding='utf-8'))):
            if i>=limit: break
            bid=float(row.get('bid') or row.get('Bid') or row.get('close') or row.get('Close') or 0); ask=float(row.get('ask') or row.get('Ask') or bid+0.2)
            out.append({'time':row.get('time') or i,'bid':bid,'ask':ask,'last':float(row.get('last') or bid)})
        if not out: raise ValueError(f'CSV tick file contains no parseable rows: {path}')
        return {'symbol':symbol,'source':'csv','sourceRequested':'csv','syntheticFallback':False,'tickCount':len(out),'ticks':out}
    def _sample(self,symbol,limit,source='synthetic_development_sample'):
        b=2380; t0=int((utcnow()-timedelta(hours=6)).timestamp()); out=[]
        for i in range(limit):
            mid=b+math.sin(i/17)*4.2+i*.002; sp=.18+abs(math.sin(i/33))*.09; out.append({'time':t0+i,'bid':round(mid-sp/2,2),'ask':round(mid+sp/2,2),'last':round(mid,2)})
        return {'symbol':symbol,'source':source,'sourceRequested':'synthetic','syntheticFallback':True,'tickCount':len(out),'ticks':out}
    def run(self,payload):
        pack=self.load_ticks(payload.get('symbol','XAUUSD'),payload.get('source','mt5'),payload.get('csvPath'),int(payload.get('limit',5000))); ticks=pack['ticks']; eq=float(payload.get('startingBalance',10000)); trades=[]
        for i in range(30,len(ticks),180):
            entry=ticks[i]['ask']; exitp=ticks[min(i+120,len(ticks)-1)]['bid']; pnl=(exitp-entry)*10; eq+=pnl; trades.append({'entryTick':i,'exitTick':min(i+120,len(ticks)-1),'entry':entry,'exit':exitp,'pnl':round(pnl,2),'equity':round(eq,2)})
        wins=[t for t in trades if t['pnl']>0]
        return {'ok':True,'symbol':pack['symbol'],'source':pack['source'],'tickCount':pack['tickCount'],'trades':trades[:250],'summary':{'trades':len(trades),'winRate':round(len(wins)/len(trades)*100,2) if trades else 0,'netProfit':round(eq-float(payload.get('startingBalance',10000)),2),'endingEquity':round(eq,2),'note':'Tick backtest scaffold: replace sample strategy rule with final production strategy logic for proof-grade results.'}}
