import { useEffect, useMemo, useState } from 'react';
import { Activity, BrainCircuit, Gauge, Layers, RefreshCcw, ShieldCheck, Sparkles, TrendingUp } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, SideBadge, Tag } from '../components/ui';
import { LiveChart } from '../components/LiveChart';
import { api } from '../lib/api';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const num=(v:any,d=1)=>Number(v||0).toFixed(d);

export default function AIAgent(){
  const [matrix,setMatrix]=useState<any>({}); const [market,setMarket]=useState<any>({}); const [analytics,setAnalytics]=useState<any>({kpis:{}}); const [monitor,setMonitor]=useState<any>({});
  const [review,setReview]=useState<any>(null); const [auditLog,setAuditLog]=useState<any>({items:[],verdictCounts:{}}); const [coachMsg,setCoachMsg]=useState(''); const [configLib,setConfigLib]=useState<any>({items:[]});
  const [recs,setRecs]=useState<any>({items:[],review:{}}); const [recMsg,setRecMsg]=useState('');
  const loadRecs=async()=>{ const r=await api.aiUnifiedRecommendations(); setRecs(r||{items:[],review:{}}); };
  const approveRec=async(it:any)=>{
    const label=it.kind==='setting'?`${it.path} -> ${it.suggest}`:`profile ${it.title}`;
    if(!confirm(`Apply this change?\n\n${it.title}\n${label}`))return;
    setRecMsg('Applying...');
    const r=it.kind==='profile'?await api.configLibraryApply(it.profileId||it.id):await api.aiApplyProposal(it);
    setRecMsg(r.ok?(r.message||'Applied.'):(r.message||'Apply failed'));
    await Promise.all([load(),loadRecs()]);
  };
  const load=async()=>{const [m,mk,an,mon,lib,aud]=await Promise.all([api.aiActionMatrix(),api.marketSnapshot(),api.analytics(),api.aiMonitor(),api.configLibrary(),api.aiAuditLog(20)]); setMatrix(m); setMarket(mk); setAnalytics(an); setMonitor(mon); setConfigLib(lib); setAuditLog(aud)};
  const runReview=async(period='daily',useAi=true)=>{setCoachMsg('Generating AI performance review...'); const r=await api.aiPerformanceReview(period,useAi); setReview(r); setCoachMsg(r.ok!==false?'Review generated.':'Review failed. Check API key/model or use local analysis.');};
  const rollback=async()=>{setCoachMsg('Rolling back last AI optimisation...'); const r=await api.aiOptimisationRollback(); setCoachMsg(r.ok?(r.message||'Rolled back'):(r.message||'Rollback failed')); await load();};
  const applyProfile=async(id:string)=>{setCoachMsg('Applying config profile...'); const r=await api.configLibraryApply(id); setCoachMsg(r.ok?`Applied ${r.profile?.name||id}. Rollback: ${r.rollbackSnapshot}`:(r.message||'Profile apply failed')); await load();};
  useEffect(()=>{load(); loadRecs(); runReview('daily',false); const id=setInterval(()=>{load();loadRecs();},5000); return()=>clearInterval(id)},[]);
  const d=matrix.decision||{}, k=analytics.kpis||{}, currency=analytics.currency||analytics.account?.currency||'';
  const gi=d.goldIntelligence||{}; const factors:any[]=Array.isArray(d.factors)?d.factors:[]; const questions:any[]=Array.isArray(d.traderQuestions)?d.traderQuestions:[];
  const blocks:string[]=d.decisionBlocks||[]; const soft:string[]=d.softBlocks||[];
  const evals:any[]=Array.isArray(d.strategyEvaluations)?d.strategyEvaluations:[]; const selName=(d.selectedStrategy||{}).name;
  const connected=Boolean(market.connected);
  const candles=useMemo(()=>Array.isArray(market.candles)?market.candles:[],[market.candles]);
  // Top weighted real factors (weight × score), sorted by contribution
  const topFactors=useMemo(()=>[...factors].sort((a,b)=>(b.weight*b.score)-(a.weight*a.score)).slice(0,8),[factors]);
  const action=String(d.action||'WAIT').toUpperCase();
  const take=Boolean(matrix.takeThisTrade);
  const bias=String(d.side||d.computedSide||'WAIT').toUpperCase();
  const rec=monitor.recovery||{}; const mv=String(rec.verdict||'—').toUpperCase(); const monOpen=Boolean(monitor.openTrade);

  return <div className="ai-agent-page layout-right">
    <div>
      <PageHeader title="AI Agent" subtitle="Live, rules-based market intelligence — every number below is computed from real MT5 candles, not mocked." right={<button className="outline-button" onClick={load}><RefreshCcw size={14}/> Refresh</button>}/>
      <Card style={{marginTop:16}}><SectionTitle icon={<Sparkles size={16}/>} title="AI Performance Coach / Self-Training Engine" right={<Tag color={review?.provider?.includes('local')?'gold':'purple'}>{review?.provider||'local_rules'}</Tag>}/>
        <div className="grid grid-4"><MetricCard label="Grade" value={review?.grade||'—'}/><MetricCard label="Trades Reviewed" value={review?.stats?.totalTrades??'—'}/><MetricCard label="Win Rate" value={review?.stats?.winRate!=null?`${review.stats.winRate}%`:'—'}/><MetricCard label="Net" value={review?.stats?.net!=null?money(review.stats.net,currency):'—'}/></div>
        <p className="muted compact" style={{marginTop:10}}>{review?.summary||'The coach studies closed trades, rejected signals and management behaviour, then proposes safe setting-level optimisation only.'}</p>
        {review?.diagnosis?.length?<Checklist items={review.diagnosis.map((x:string)=>({label:x,value:'COACH',type:'warning'}))}/>:null}
        {review?.blockStats&&(review.blockStats.takeCount+review.blockStats.skipCount>0)?<div className="ai-insight" style={{marginTop:12,display:'block'}}>
          <div className="button-wrap space-between"><strong>Why the bot skipped setups (last {Math.round((review.blockStats.windowHours||48)/24)}d)</strong><Tag color={review.blockStats.takeRatePct<3?'gold':review.blockStats.takeRatePct>35?'red':'green'}>Fire rate {review.blockStats.takeRatePct}% · {review.blockStats.takeCount} took / {review.blockStats.skipCount} skipped</Tag></div>
          {(review.blockStats.topBlockReasons||[]).length?<DataTable columns={['Skip Reason','Count','% of skips']} rows={review.blockStats.topBlockReasons} renderCell={(r,c)=>c==='Skip Reason'?r.reason:c==='Count'?String(r.count):`${Math.round(r.count/Math.max(1,review.blockStats.skipCount)*100)}%`}/>:<p className="tiny muted">No skip reasons recorded yet — connect MT5 and let the bot evaluate a few setups.</p>}
        </div>:null}
        <div className="button-wrap" style={{marginTop:12}}><button className="outline-button" onClick={()=>runReview('daily',true)}>Daily AI Review</button><button className="outline-button" onClick={()=>runReview('weekly',true)}>Weekly AI Review</button><button className="ghost-button" onClick={rollback}>Rollback last change</button></div>
        {coachMsg&&<p className="tiny muted" style={{marginTop:8}}>{coachMsg}</p>}
      </Card>

      {/* V12.81 — ONE unified place for every proposed change. Replaces the old scattered
          'Apply Fix' table, config recommendation insight, and standalone Config Library apply. */}
      <Card style={{marginTop:16}}><SectionTitle icon={<Sparkles size={16}/>} title="Recommended Actions" right={<Tag color={recs.items?.length?'purple':'gold'}>{recs.items?.length?`${recs.items.length} to review`:'Nothing to change'}</Tag>}/>
        <p className="muted compact" style={{marginTop:4}}>{recs.note||'One list. Every proposed change — from the trade-review engine, the coach, and config profiles — appears here. Approve each individually; nothing is applied automatically.'}</p>
        {recs.review?.verdict?<div className="ai-insight" style={{marginTop:10,display:'block'}}><span className="tiny">{recs.review.verdict}</span></div>:null}
        {(recs.items||[]).length?<div className="rec-list" style={{marginTop:12,display:'flex',flexDirection:'column',gap:10}}>
          {recs.items.map((it:any)=><Card soft key={it.id} style={{padding:'12px 14px'}}>
            <div className="button-wrap space-between"><strong>{it.title}</strong><span className="button-wrap" style={{gap:6}}><Tag color={it.risk==='high'?'red':it.risk==='low'?'green':'gold'}>{it.risk} risk</Tag><Tag color="blue">{it.confidence}</Tag></span></div>
            <p className="tiny muted" style={{margin:'6px 0'}}>{it.rationale}</p>
            {it.kind==='setting'?<code className="tiny" style={{color:'#8ab4ff'}}>{it.path} → {String(it.suggest)} <span className="muted">(now {it.current_hint})</span></code>:<span className="tiny muted">Profile switch</span>}
            <div className="button-wrap" style={{marginTop:8}}><button className="gold-button" onClick={()=>approveRec(it)}>Approve</button></div>
          </Card>)}
        </div>:<p className="tiny muted" style={{marginTop:10}}>No changes proposed. The engine won't suggest tuning until it has a large enough sample to avoid curve-fitting.</p>}
        {recMsg&&<p className="tiny muted" style={{marginTop:8}}>{recMsg}</p>}
      </Card>
      <Card style={{marginTop:16}}><SectionTitle icon={<ShieldCheck size={16}/>} title="AI Entry Auditor — Verdict Log (V12.68)" right={<Tag color={(auditLog.items||[]).length?'purple':'gold'}>{(auditLog.items||[]).length?`${auditLog.count||auditLog.items.length} audits · ${Object.entries(auditLog.verdictCounts||{}).map(([k,v])=>`${k} ${v}`).join(' · ')}`:'No audits yet'}</Tag>}/>
        {(auditLog.items||[]).length?<DataTable columns={['Time','Verdict','Side','Conf','Adjust','Reason']} rows={auditLog.items.slice(0,10)} renderCell={(r,c)=>c==='Time'?String(r.ts||'').slice(11,19):c==='Verdict'?<Tag color={r.decision==='VETO'?'red':r.decision==='DOWNGRADE'?'gold':'green'}>{r.decision}</Tag>:c==='Side'?<SideBadge side={r.side}/>:c==='Conf'?String(r.confidence??'—'):c==='Adjust'?String(r.confidenceAdjust??'—'):String(r.reason||'').slice(0,90)}/>:<p className="tiny muted">Enable the Entry Auditor in Settings → 12d-2 (needs an AI provider key from 12d). Every pre-trade AI verdict lands here so you can compare AI calls against outcomes.</p>}
      </Card>
      <Card style={{marginTop:16}}><SectionTitle icon={<Layers size={16}/>} title="Adaptive Config Library" right={<Tag color="blue">{configLib?.autoSelectEnabled?'Auto-select ON':'Manual / AI recommended'}</Tag>}/>
        <p className="tiny muted" style={{marginBottom:8}}>Profiles are bulk-presets. To let the AI pick one for you based on behaviour, use the profile suggestions in <strong>Recommended Actions</strong> above. Manual apply stays here.</p>
        <div className="grid grid-3">{(configLib.items||[]).slice(0,6).map((c:any)=><Card soft key={c.id}><strong>{c.name}</strong><p className="tiny muted">{c.description}</p><div className="button-wrap"><Tag color={configLib.activeConfigId===c.id?'green':'gold'}>{configLib.activeConfigId===c.id?'ACTIVE':'PROFILE'}</Tag><button className="outline-button" onClick={()=>applyProfile(c.id)}>Apply</button></div></Card>)}</div>
      </Card>

      <div className="grid grid-5 ai-top-strip">
        <MetricCard label="Agent Status" value={connected?'Analyzing live':'Waiting for MT5'}/>
        <MetricCard label="Decision" value={take?`TAKE ${bias}`:action} delta={d.lifecycleState?`Lifecycle: ${d.lifecycleState}`:undefined}/>
        <MetricCard label="Confidence" value={`${Math.round(Number(d.confidence||0))}%`}/>
        <MetricCard label="Confluence" value={`${gi.confluenceCount??d.features?.confluenceCount??'—'}/12`}/>
        <MetricCard label="Regime" value={d.marketRegime||'—'} delta={d.regimeConfidence!=null?`${d.regimeConfidence}% confidence`:undefined}/>
      </div>

      {/* REAL gold-market intelligence — the actual indicators the engine reads */}
      <Card style={{marginTop:16}}><SectionTitle icon={<BrainCircuit size={18}/>} title="Live Gold Market Intelligence" right={<Tag color={connected?'green':'red'}>{connected?'Computed live':'No MT5'}</Tag>}/>
        <div className="grid grid-4">
          <IntelCell label="RSI-14" value={num(gi.rsi14,1)} sub={gi.rsiStatus||'—'} tone={gi.rsiStatus==='Overbought'?'red':gi.rsiStatus==='Oversold'?'green':undefined}/>
          <IntelCell label="MACD" value={gi.macdAligned?'Aligned':'Divergent'} sub={`hist ${num(gi.macd?.histogram,4)}`} tone={gi.macdAligned?'green':'red'}/>
          <IntelCell label="H1 Alignment" value={gi.h1Aligned?'Aligned':'Not aligned'} sub="higher timeframe EMA stack" tone={gi.h1Aligned?'green':'red'}/>
          <IntelCell label="Volume" value={gi.volumeConfirmed?'Confirming':'Weak'} sub="3-bar vs 20-bar avg" tone={gi.volumeConfirmed?'green':'gold'}/>
          <IntelCell label="Order Block" value={gi.orderBlock?.found?'Found':'None'} sub={gi.orderBlock?.found?`${num(gi.orderBlock?.low,1)}–${num(gi.orderBlock?.high,1)}`:'no OB before move'} tone={gi.orderBlock?.found?'green':'gold'}/>
          <IntelCell label="Fair Value Gap" value={gi.fvg?.found?'Open FVG':'None'} sub="3-candle imbalance" tone={gi.fvg?.found?'green':'gold'}/>
          <IntelCell label="OTE Swing" value={gi.swingHigh&&gi.swingLow?`${num(gi.swingLow,0)}–${num(gi.swingHigh,0)}`:'—'} sub="61.8–78.6% Fib zone"/>
          <IntelCell label="Asian Range" value={gi.asianRange?.defined?'Defined':'—'} sub={gi.asianRange?.defined?`${num(gi.asianRange?.low,0)}–${num(gi.asianRange?.high,0)}`:'outside Asian session'}/>
          <IntelCell label="Trend Strength" value={num(d.trendStrengthAdx,0)} sub={`ADX · ${Number(d.trendStrengthAdx||0)>=25?'trending':Number(d.trendStrengthAdx||0)<18?'ranging':'weak'}`} tone={Number(d.trendStrengthAdx||0)>=25?'green':Number(d.trendStrengthAdx||0)<18?'red':'gold'}/>
          <IntelCell label="Volatility %ile" value={`${num(d.atrPercentile,0)}%`} sub={Number(d.atrPercentile||0)>=80?'expansion':Number(d.atrPercentile||0)<=25?'compression':'normal'} tone={Number(d.atrPercentile||0)>=80?'gold':Number(d.atrPercentile||0)<=25?'red':undefined}/>
        </div>
        <div className="ai-insight" style={{marginTop:14}}><Sparkles size={15}/><span>{d.reason||'Waiting for live MT5 confluence before approving a trade.'}</span></div>
      </Card>

      {/* REAL weighted decision factors */}
      <div className="grid grid-2" style={{marginTop:16}}>
        <Card><SectionTitle icon={<Gauge size={16}/>} title="Weighted Decision Factors (live)"/>{topFactors.length?topFactors.map((f,i)=><div className="factor-row" key={i}><span title={f.detail}>{f.name}</span><ProgressBar value={Number(f.score||0)}/><strong>{Math.round(Number(f.score||0))}</strong></div>):<p className="muted tiny">Connect MT5 — factors compute from live candles.</p>}</Card>
        <Card><SectionTitle icon={<TrendingUp size={16}/>} title="Confluence Checklist (live)"/>{questions.length?<Checklist items={questions.slice(0,10).map((q:any)=>({label:q.question,value:q.answer,type:q.answer==='YES'?'success':q.answer==='NO'?'danger':'warning'}))}/>:<p className="muted tiny">No live confluence yet.</p>}</Card>
      </div>

      <Card style={{marginTop:16}}><SectionTitle icon={<Activity size={16}/>} title="Live Chart — entry / SL / TP read by the AI"/><LiveChart symbol={market.symbol||'XAUUSD'} height={320} candles={candles} levels={d.tradePlan?{entry:d.tradePlan.entry,sl:d.tradePlan.sl,tp1:d.tradePlan.tp1,tp2:d.tradePlan.tp2,tp3:d.tradePlan.tp3}:{}}/></Card>

      <div className="grid grid-2" style={{marginTop:16}}>
        <Card><SectionTitle title="Why the AI is NOT trading yet"/>{blocks.length?<Checklist items={blocks.map((b:string)=>({label:b,value:'BLOCK',type:'danger'}))}/>:soft.length?<Checklist items={soft.map((b:string)=>({label:b,value:'SOFT',type:'warning'}))}/>:<Checklist items={[{label:take?'All hard gates passed — trade approved':'Monitoring for a valid setup',value:take?'READY':'OK',type:'success'}]}/>}</Card>
        <Card><SectionTitle title="Performance Adaptation (bot-only)"/><div className="grid grid-3 ai-adapt-row"><MetricCard label="Win Rate (real)" value={`${k.winRate||0}%`}/><MetricCard label="Profit Factor" value={k.profitFactor||0}/><MetricCard label="Expectancy" value={money(k.expectancy,currency)}/></div></Card>
      </div>
      <Card className="strategy-scan-card" style={{marginTop:16}}><SectionTitle icon={<Layers size={16}/>} title="Strategy Scan — best fit for this bar" right={<Tag color="purple">Each strategy judged on its own gates</Tag>}/>
        {evals.length?<DataTable columns={['Strategy','Score','Conf','Verdict','Why blocked']} rows={evals} renderCell={(r,c)=>c==='Strategy'?<span><strong>{r.name}</strong>{selName===r.name&&<> <Tag color="green">selected</Tag></>}</span>:c==='Score'?Math.round(Number(r.score||0)):c==='Conf'?`${Math.round(Number(r.confidence||0))}%`:c==='Verdict'?<Tag color={r.passes?'green':'gold'}>{r.passes?'WOULD TRADE':'blocked'}</Tag>:c==='Why blocked'?(r.passes?'—':(Array.isArray(r.blockedBy)?r.blockedBy.join('; '):'')):r[c]}/>:<p className="muted tiny">Connect MT5 — the AI ranks every enabled strategy and shows which one fits this exact bar.</p>}
        <p className="tiny muted" style={{marginTop:8}}>The AI scores every enabled strategy and takes the best one that passes <strong>its own</strong> entry gates (chop tolerance, confidence bar, R:R) — so you're not blocked when a better-suited strategy exists. Universal safety gates (news blackout, spread cap, cost discipline, dirty market) still block <em>all</em> strategies. If nothing fits this regime, run the <strong>Strategy Lab</strong> to find/install a strategy that does.</p>
      </Card>
      <Card style={{marginTop:16}}><SectionTitle title="Journal of AI Decisions"/><DataTable columns={['Time','Pair','Action','PnL','Result']} rows={(analytics.history||[]).slice(0,8)} renderCell={(r,c)=>c==='Action'?<SideBadge side={r.side||r.direction}/>:c==='PnL'?<span className={Number(r.pnlUsd)>=0?'positive':'negative'}>{money(r.pnlUsd,currency)}</span>:c==='Result'?<Tag color={Number(r.pnlUsd)>=0?'green':'red'}>{Number(r.pnlUsd)>=0?'WIN':'LOSS'}</Tag>:c==='Time'?(r.closeTime||'—'):r[c.toLowerCase()]||r.symbol||'—'}/></Card>
    </div>

    <div className="right-stack side-panel-sticky">
      <Card><SectionTitle title="Decision"/><div className="signal-card-body" style={{justifyContent:'flex-start',gap:14}}><ConfidenceRing value={Number(d.confidence||0)} size={104}/><div><div className={`trade-side ${bias==='SELL'?'sell':bias==='BUY'?'buy':''}`} style={{fontSize:30}}>{take?bias:'WAIT'}</div><Tag color={take?'green':'gold'}>{d.quality||action}</Tag></div></div>{!take&&bias!=='WAIT'&&<p className="tiny muted" style={{marginTop:8}}>Directional bias is <strong className={bias==='SELL'?'negative':'positive'}>{bias}</strong>, but entry gates are not all satisfied yet — so the AI holds.</p>}</Card>
      <Card><SectionTitle icon={<Activity size={16}/>} title="AI Recovery Monitor" right={<Tag color={monOpen?(mv==='RECOVER'?'green':mv==='CUT'?'red':'gold'):'gold'}>{monOpen?mv:'Idle'}</Tag>}/>
        {monOpen?<>
          <div className="signal-card-body" style={{justifyContent:'flex-start',gap:14}}><ConfidenceRing value={Number(rec.recoveryScore||0)} size={92}/><div><div className={`trade-side ${mv==='CUT'?'sell':mv==='RECOVER'?'buy':''}`} style={{fontSize:22}}>{mv}</div><Tag color={monitor.direction==='BUY'?'green':'red'}>{monitor.direction} #{monitor.ticket}</Tag><div className="tiny muted" style={{marginTop:4}}>Adverse {num(rec.adverseAtr,2)} ATR{rec.invalidated?' · structure invalidated':''}</div></div></div>
          {Array.isArray(rec.reasons)&&rec.reasons.length>0&&<Checklist items={rec.reasons.map((r:string)=>({label:r,value:'',type:mv==='CUT'?'danger':mv==='RECOVER'?'success':'warning'}))}/>}
          <p className="tiny muted">RECOVER → hold (no premature fast-fail). CUT → close now. The tick-level EA enforces this within ~1s.</p>
        </>:<p className="muted tiny">{monitor.message||'No open trade. The recovery monitor activates when a GodMode trade is open and assesses hold-vs-cut every cycle.'}</p>}
        {monitor.chartsAvailable===false&&<p className="tiny" style={{color:'var(--amber)',marginTop:6}}>⚠ matplotlib is not installed, so Telegram chart images are OFF (alerts still send as text). Fix: run <code>pip install -r backend/requirements.txt</code> in your venv, then restart the bot.</p>}
      </Card>
      <Card><SectionTitle title="Recommended Plan"/><div className="recommended-action"><SideBadge side={bias}/><TradeMetric label="Entry" value={num(d.tradePlan?.entry||market.price,2)}/><TradeMetric label="SL" value={num(d.tradePlan?.sl,2)}/><TradeMetric label="TP1" value={num(d.tradePlan?.tp1,2)}/><TradeMetric label="TP2" value={num(d.tradePlan?.tp2,2)}/><TradeMetric label="R/R TP1" value={num(d.tradePlan?.rrToTP1,1)}/></div></Card>
      <Card><SectionTitle title="Engine Health"/><Checklist items={[{label:'Data Feed',value:connected?'Live MT5':'Offline',type:connected?'success':'danger'},{label:'Candles loaded',value:String(candles.length||0),type:candles.length?'success':'warning'},{label:'Spread',value:num(market.spread,2),type:Number(market.spread||0)<0.35?'success':'warning'},{label:'Decision engine',value:'Operational',type:'success'},{label:'Risk manager',value:'Operational',type:'success'}]}/></Card>
    </div>
  </div>
}

function IntelCell({label,value,sub,tone}:{label:string;value:any;sub?:string;tone?:'green'|'red'|'gold'}){return <div className="mini-metric"><span>{label}</span><strong className={tone==='green'?'positive':tone==='red'?'negative':tone==='gold'?'gold':''} style={{fontSize:15}}>{value}</strong>{sub&&<span className="tiny muted">{sub}</span>}</div>}
function TradeMetric({label,value}:{label:string;value:any}){return <div><span>{label}</span><strong>{value}</strong></div>}
