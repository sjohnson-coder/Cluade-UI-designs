from __future__ import annotations
import base64, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
DATA_DIR=Path(__file__).resolve().parents[1]/'data'; REPLAY_DIR=DATA_DIR/'replays'; REPORT_DIR=DATA_DIR/'reports'; VERSION_DIR=DATA_DIR/'versions'
for d in (REPLAY_DIR,REPORT_DIR,VERSION_DIR): d.mkdir(parents=True,exist_ok=True)
def now_iso(): return datetime.now(timezone.utc).isoformat()
class TradeReplayStorage:
    def store(self,payload):
        trade_id=str(payload.get('tradeId') or payload.get('ticket') or f'trade-{datetime.now().strftime("%Y%m%d-%H%M%S")}'); img_path=None; img=payload.get('chartImageBase64')
        if img:
            try:
                if ',' in img: img=img.split(',',1)[1]
                img_path=REPLAY_DIR/f'{trade_id}.png'; img_path.write_bytes(base64.b64decode(img))
            except Exception as exc: payload['imageStoreError']=str(exc); img_path=None
        record={'tradeId':trade_id,'storedAtUtc':now_iso(),'symbol':payload.get('symbol',''),'strategy':payload.get('strategy',''),'decisionSnapshot':payload.get('decisionSnapshot',{}),'chartImagePath':str(img_path) if img_path else None,'events':payload.get('events',[]),'notes':payload.get('notes','')}
        (REPLAY_DIR/f'{trade_id}.json').write_text(json.dumps(record,indent=2),encoding='utf-8'); return {'ok':True,'replay':record}
    def list(self):
        out=[]
        for f in sorted(REPLAY_DIR.glob('*.json'),reverse=True)[:100]:
            try: out.append(json.loads(f.read_text(encoding='utf-8')))
            except Exception: pass
        return {'ok':True,'count':len(out),'replays':out}
class VersionRegistry:
    def _hash(self,p): return hashlib.sha256(json.dumps(p,sort_keys=True,default=str).encode()).hexdigest()[:12]
    def register_strategy(self,payload):
        sid=str(payload.get('strategyId','unknown-strategy')); ver=str(payload.get('version') or f'v{datetime.now().strftime("%Y.%m.%d.%H%M")}'); rec={'type':'strategy','strategyId':sid,'version':ver,'hash':self._hash(payload),'createdAtUtc':now_iso(),'payload':payload}; (VERSION_DIR/f'strategy_{sid}_{ver}.json').write_text(json.dumps(rec,indent=2),encoding='utf-8'); return {'ok':True,'record':rec}
    def register_parameters(self,payload):
        profile=str(payload.get('profile','default')); ver=str(payload.get('version') or f'v{datetime.now().strftime("%Y.%m.%d.%H%M")}'); rec={'type':'parameters','profile':profile,'version':ver,'hash':self._hash(payload),'createdAtUtc':now_iso(),'payload':payload}; (VERSION_DIR/f'parameters_{profile}_{ver}.json').write_text(json.dumps(rec,indent=2),encoding='utf-8'); return {'ok':True,'record':rec}
    def list(self):
        out=[]
        for f in sorted(VERSION_DIR.glob('*.json'),reverse=True):
            try: out.append(json.loads(f.read_text(encoding='utf-8')))
            except Exception: pass
        return {'ok':True,'count':len(out),'versions':out[:200]}
class ForwardTestReporter:
    def generate(self,payload=None):
        payload=payload or {}; trades=payload.get('trades') or payload.get('history') or []
        rid=f'forward-test-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
        if not trades:
            report={'reportId':rid,'createdAtUtc':now_iso(),'source':'no_bot_trade_data','summary':{'trades':0,'winRate':0,'profitFactor':0,'expectancyR':0,'maxDrawdownPct':0,'executionScore':0},'strategyBreakdown':[],'recommendations':['Connect MT5 and collect GodMode-tagged bot trades before using performance reports.'],'message':'No fake/demo report generated.'}
        else:
            wins=[t for t in trades if float(t.get('pnlUsd',t.get('pnl',0)) or 0)>0]; losses=[t for t in trades if float(t.get('pnlUsd',t.get('pnl',0)) or 0)<0]
            gp=sum(float(t.get('pnlUsd',t.get('pnl',0)) or 0) for t in wins); gl=abs(sum(float(t.get('pnlUsd',t.get('pnl',0)) or 0) for t in losses)); total=len(trades)
            report={'reportId':rid,'createdAtUtc':now_iso(),'source':'bot_only_history','summary':{'trades':total,'winRate':round(len(wins)/total*100,2) if total else 0,'profitFactor':round(gp/gl,2) if gl else 0,'expectancyR':0,'maxDrawdownPct':0,'executionScore':0},'strategyBreakdown':[],'recommendations':['Use this report only after enough real bot-only trades have accumulated.']}
        (REPORT_DIR/f'{rid}.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); return {'ok':True,'report':report}
    def daily_ai_review(self):
        return {'ok':True,'review':{'dateUtc':datetime.now(timezone.utc).date().isoformat(),'source':'bot_only_history','overallGrade':'UNRATED','aiSummary':'No fake/demo AI review is generated. Connect MT5 and collect GodMode-tagged bot trades for a true daily review.','whatWorked':[],'whatToImprove':['Collect real bot-only trades.','Confirm MT5 connection and symbol mapping.','Keep dry-run on until execution is validated.'],'tomorrowPlan':['Wait for live MT5 data.','Only trade when AI action matrix approves.','Keep pyramiding blocked unless an active protected bot trade exists.']}}
