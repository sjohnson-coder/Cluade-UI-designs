import { useEffect, useMemo, useState } from 'react';
import { Activity, BrainCircuit, Gauge, Layers, RefreshCcw, Sparkles, TrendingUp } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, SideBadge, Tag } from '../components/ui';
import { LiveChart } from '../components/LiveChart';
import { api } from '../lib/api';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const num=(v:any,d=1)=>Number(v||0).toFixed(d);

export default function AIAgent(){
  const [matrix,setMatrix]=useState<any>({}); const [market,setMarket]=useState<any>({}); const [analytics,setAnalytics]=useState<any>({kpis:{}}); const [monitor,setMonitor]=useState<any>({});
  const load=async()=>{const [m,mk,an,mon]=await Promise.all([api.aiActionMatrix(),api.marketSnapshot(),api.analytics(),api.aiMonitor()]); setMatrix(m); setMarket(mk); setAnalytics(an); setMonitor(mon)};
  useEffect(()=>{load(); const id=setInterval(load,5000); return()=>clearInterval(id)},[]);
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
      <div className="grid grid-5 ai-top-strip">
        <MetricCard label="Agent Status" value={connected?'Analyzing live':'Waiting for MT5'}/>
        <MetricCard label="Decision" value={take?`TAKE ${bias}`:action}/>
        <MetricCard label="Confidence" value={`${Math.round(Number(d.confidence||0))}%`}/>
        <MetricCard label="Confluence" value={`${gi.confluenceCount??d.features?.confluenceCount??'—'}/12`}/>
        <MetricCard label="Regime" value={d.marketRegime||'—'}/>
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
