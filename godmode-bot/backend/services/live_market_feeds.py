from __future__ import annotations
import csv, io, json, math, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

def utcnow(): return datetime.now(timezone.utc)
def get_text(url: str, headers: dict[str,str] | None=None, timeout: float=8.0) -> str:
    req = urllib.request.Request(url, headers=headers or {'User-Agent':'GodModeGoldBot/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as res: return res.read().decode('utf-8')
def get_json(url: str, headers: dict[str,str] | None=None): return json.loads(get_text(url, headers))

class EconomicCalendarAPI:
    def __init__(self):
        self.key=(os.getenv('GODMODE_ECONOMIC_CALENDAR_KEY','').strip() or os.getenv('ECONOMIC_CALENDAR_KEY','').strip())
        self.before=int(os.getenv('GODMODE_NEWS_BLACKOUT_BEFORE_MINUTES','30')); self.after=int(os.getenv('GODMODE_NEWS_BLACKOUT_AFTER_MINUTES','30'))
    @property
    def url(self):
        return (os.getenv('GODMODE_ECONOMIC_CALENDAR_URL','').strip() or os.getenv('ECONOMIC_CALENDAR_URL','').strip())
    def events(self):
        if self.url:
            try:
                url=self.url; headers={'User-Agent':'GodModeGoldBot/1.0'}
                if self.key: headers['Authorization']=f'Bearer {self.key}'; url += ('&' if '?' in url else '?')+'apikey='+urllib.parse.quote(self.key)
                raw=get_json(url, headers); data=raw.get('events', raw) if isinstance(raw, dict) else raw
                out=[]
                for i,e in enumerate(data[:80] if isinstance(data,list) else []):
                    if not isinstance(e,dict): continue
                    title=e.get('title') or e.get('event') or e.get('name') or f'Economic Event {i+1}'
                    impact=str(e.get('impact') or e.get('importance') or 'medium').lower(); ccy=str(e.get('currency') or e.get('country') or 'USD').upper()
                    t=e.get('time') or e.get('date') or e.get('datetime') or e.get('timestamp')
                    dt=self._parse(t)
                    out.append({'id':e.get('id') or f'event-{i+1}','title':title,'currency':ccy,'impact':'high' if 'high' in impact or impact in {'3','red'} else 'medium' if 'medium' in impact or impact in {'2','orange'} else 'low','timeUtc':dt.isoformat(),'actual':e.get('actual'),'forecast':e.get('forecast'),'previous':e.get('previous'),'source':'live_api'})
                return out or self._fallback('live_api_empty')
            except Exception as exc: return self._fallback(f'fallback_after_api_error:{exc}')
        return self._fallback('local_fallback_no_api_configured')
    def _parse(self, v):
        if isinstance(v,(int,float)): return datetime.fromtimestamp(float(v), tz=timezone.utc)
        if isinstance(v,str):
            try:
                d=datetime.fromisoformat(v.replace('Z','+00:00')); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except Exception: pass
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

class MacroFeed:
    NEUTRAL_BAND = 0.05  # |changePct| within this band = noise, no directional read
    def snapshot(self):
        # Read env FRESH each call so feed URLs set from the Settings UI take effect at
        # runtime. Accept both the GODMODE_* and *_FEED_URL naming conventions.
        dxy_url=(os.getenv('GODMODE_DXY_URL','').strip() or os.getenv('DXY_FEED_URL','').strip())
        us10y_url=(os.getenv('GODMODE_US10Y_URL','').strip() or os.getenv('US10Y_FEED_URL','').strip())
        dxy_key=(os.getenv('GODMODE_DXY_KEY','').strip() or os.getenv('DXY_FEED_KEY','').strip())
        us10y_key=(os.getenv('GODMODE_US10Y_KEY','').strip() or os.getenv('US10Y_FEED_KEY','').strip())
        dxy=self._one('DXY', dxy_url, dxy_key, 104.21); us10y=self._one('US10Y', us10y_url, us10y_key, 4.28)
        # A fallback (unconfigured) feed contributes NO tilt — the bias stays NEUTRAL instead of
        # the old hardcoded bullish stub. Only a LIVE feed moving beyond the neutral band tilts.
        score=50; reasons=[]; live=[]
        for feed,sup,pres,wt in ((dxy,'DXY softening supports gold upside','DXY strengthening pressures gold',(18,14)),
                                 (us10y,'US10Y yield softening supports gold','US10Y yield rising pressures gold',(16,12))):
            if feed['status']!='live':
                continue
            live.append(feed['symbol']); chg=feed['changePct']
            if chg < -self.NEUTRAL_BAND: score+=wt[0]; reasons.append(sup)
            elif chg > self.NEUTRAL_BAND: score-=wt[1]; reasons.append(pres)
            else: reasons.append(f"{feed['symbol']} flat — no macro tilt")
        if not live:
            reasons=['No live macro feed configured — NEUTRAL (no tilt). Set DXY/US10Y feed URLs in Settings → Data Feeds for live context.']
        score=max(0,min(100,score))
        return {'dxy':dxy,'us10y':us10y,'goldBias':'BULLISH_GOLD' if score>=62 else 'BEARISH_GOLD' if score<=42 else 'NEUTRAL_GOLD','goldBiasScore':score,'reasons':reasons,'feedStatus':'live' if live else 'not_configured','liveFeeds':live,'timestampUtc':utcnow().isoformat()}
    def _one(self, name,url,key,fv):
        if not url: return {'symbol':name,'value':fv,'changePct':0.0,'source':'local_fallback_no_api_configured','status':'fallback'}
        try:
            headers={'User-Agent':'GodModeGoldBot/1.0'}
            if key: headers['Authorization']=f'Bearer {key}'; url += ('&' if '?' in url else '?')+'apikey='+urllib.parse.quote(key)
            text=get_text(url,headers); val,chg=self._parse(text); return {'symbol':name,'value':val,'changePct':chg,'source':'live_api','status':'live'}
        except Exception as exc: return {'symbol':name,'value':fv,'changePct':0.0,'source':f'fallback_after_api_error:{exc}','status':'fallback'}
    def _parse(self,text):
        try:
            raw=json.loads(text); node=raw[0] if isinstance(raw,list) and raw else raw
            if isinstance(node,dict):
                v=node.get('price') or node.get('value') or node.get('close') or node.get('last') or node.get('rate'); c=node.get('changePercent') or node.get('changesPercentage') or node.get('changePct') or node.get('change') or 0
                return float(v), float(str(c).replace('%',''))
        except Exception: pass
        rows=list(csv.DictReader(io.StringIO(text))); last=rows[-1]; key=next((k for k in last if k.lower() in {'close','value','price'}), list(last)[-1]); v=float(last[key]); p=float(rows[-2][key]) if len(rows)>1 else v; return v, ((v-p)/p*100 if p else 0)

class TickDataBacktester:
    def load_ticks(self,symbol='XAUUSD',source='mt5',csv_path=None,limit=5000):
        if source=='csv' and csv_path: return self._csv(symbol,csv_path,limit)
        if source=='mt5':
            try:
                import MetaTrader5 as mt5
                if mt5.initialize():
                    ticks=mt5.copy_ticks_from(symbol, utcnow()-timedelta(days=5), limit, mt5.COPY_TICKS_ALL)
                    if ticks is not None and len(ticks): return {'symbol':symbol,'source':'mt5_live_terminal','tickCount':len(ticks),'ticks':[{'time':int(t['time']),'bid':float(t['bid']),'ask':float(t['ask']),'last':float(t['last'] or t['bid'])} for t in ticks[:limit]]}
            except Exception: pass
        return self._sample(symbol, min(limit,1200))
    def _csv(self,symbol,path,limit):
        p=Path(path)
        if not p.exists(): return self._sample(symbol,min(limit,1200),f'fallback_csv_missing:{path}')
        out=[]
        for i,row in enumerate(csv.DictReader(p.open(encoding='utf-8'))):
            if i>=limit: break
            bid=float(row.get('bid') or row.get('Bid') or row.get('close') or row.get('Close') or 0); ask=float(row.get('ask') or row.get('Ask') or bid+0.2)
            out.append({'time':row.get('time') or i,'bid':bid,'ask':ask,'last':float(row.get('last') or bid)})
        return {'symbol':symbol,'source':'csv','tickCount':len(out),'ticks':out}
    def _sample(self,symbol,limit,source='synthetic_development_sample'):
        b=2380; t0=int((utcnow()-timedelta(hours=6)).timestamp()); out=[]
        for i in range(limit):
            mid=b+math.sin(i/17)*4.2+i*.002; sp=.18+abs(math.sin(i/33))*.09; out.append({'time':t0+i,'bid':round(mid-sp/2,2),'ask':round(mid+sp/2,2),'last':round(mid,2)})
        return {'symbol':symbol,'source':source,'tickCount':len(out),'ticks':out}
    def run(self,payload):
        pack=self.load_ticks(payload.get('symbol','XAUUSD'),payload.get('source','mt5'),payload.get('csvPath'),int(payload.get('limit',5000))); ticks=pack['ticks']; eq=float(payload.get('startingBalance',10000)); trades=[]
        for i in range(30,len(ticks),180):
            entry=ticks[i]['ask']; exitp=ticks[min(i+120,len(ticks)-1)]['bid']; pnl=(exitp-entry)*10; eq+=pnl; trades.append({'entryTick':i,'exitTick':min(i+120,len(ticks)-1),'entry':entry,'exit':exitp,'pnl':round(pnl,2),'equity':round(eq,2)})
        wins=[t for t in trades if t['pnl']>0]
        return {'ok':True,'symbol':pack['symbol'],'source':pack['source'],'tickCount':pack['tickCount'],'trades':trades[:250],'summary':{'trades':len(trades),'winRate':round(len(wins)/len(trades)*100,2) if trades else 0,'netProfit':round(eq-float(payload.get('startingBalance',10000)),2),'endingEquity':round(eq,2),'note':'Tick backtest scaffold: replace sample strategy rule with final production strategy logic for proof-grade results.'}}
