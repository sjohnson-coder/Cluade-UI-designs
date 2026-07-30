import { useEffect, useMemo, useState } from 'react';
import { Activity, BrainCircuit, CalendarDays, Moon, Network, Newspaper, RefreshCcw, ShieldCheck, WifiOff } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, Tag } from '../components/ui';
import { EquityCurve, MiniCandleBlock } from '../components/Charts';
import { LiveChart } from '../components/LiveChart';
import { api } from '../lib/api';
import aiNode from '../assets/godmode-ai-node.svg';
import EconomicCalendar from './EconomicCalendar';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const price=(v:any)=>Number(v||0)>0?Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:3}):'—';
const readCache=(key:string,fallback:any=null)=>{try{const raw=localStorage.getItem(key);return raw?JSON.parse(raw):fallback}catch{return fallback}};
const writeCache=(key:string,value:any)=>{try{localStorage.setItem(key,JSON.stringify(value))}catch{}};

function StrategyChip({s,active}:{s:any;active?:boolean}){return <Tag color={active?'green':'gold'}>{s?.name || s?.id || 'Waiting'}</Tag>}
function TradeLine({label,value,tone}:{label:string;value:any;tone?:'green'|'red'|'gold'}){return <div className="trade-line"><span>{label}</span><strong className={tone==='green'?'positive':tone==='red'?'negative':tone==='gold'?'gold':''}>{value}</strong></div>}

// Parse a "YYYY-MM-DD HH:MM:SS UTC" string to unix seconds
function toUnix(s:any):number{ if(!s) return 0; const t=Date.parse(String(s).replace(' UTC','Z').replace(' ','T')); return Number.isNaN(t)?0:Math.floor(t/1000); }
// Snap a timestamp to the nearest candle time so markers land on a bar
function snapToCandle(ts:number,candles:any[]):number{ if(!candles?.length) return ts; let best=candles[0].time,diff=Infinity; for(const c of candles){const d=Math.abs(c.time-ts); if(d<diff){diff=d;best=c.time}} return best; }

export default function Dashboard(){
 const [data,setData]=useState<any>(()=>readCache('godmode.dashboardCache',null)),[strategies,setStrategies]=useState<any[]>(()=>readCache('godmode.strategiesCache',[])),[feeds,setFeeds]=useState<any>(()=>readCache('godmode.feedsStatus',null)),[loading,setLoading]=useState(()=>!readCache('godmode.dashboardCache',null));
 // V12.53: show cached Dashboard instantly when returning from another page, then refresh silently.
 // Heavy/slow side panels (strategies + feeds) no longer reload on every fast dashboard tick.
 const loadDashboard=async(initial=false)=>{if(initial&&!data)setLoading(true); const d=await api.dashboard(); setData(d); writeCache('godmode.dashboardCache',d); if(initial)setLoading(false)};
 const loadFeeds=async()=>{const f=await api.feedsStatus(); setFeeds(f); writeCache('godmode.feedsStatus',f)};
 const loadStrategies=async()=>{const s=await api.strategies(); if(Array.isArray(s)){setStrategies(s); writeCache('godmode.strategiesCache',s)}};
 // V13.5: derived from `data` (declared above) so the poll effect can read it WITHOUT
 // depending on activeTrade, which is declared further down.
 const hasOpenTrade=((data?.trades?.active)||[]).length>0;
 // V13.10 — missed-pump autopsy feed. Answers 'what did the bot miss, why, and what would
 // it have made?' directly on the dashboard instead of only in a jsonl file on disk.
 const [missed,setMissed]=useState<any>({items:[],totals:{}});
 const [missedShown,setMissedShown]=useState(5);
 const [predictorStatus,setPredictorStatus]=useState<any>({ok:false,earlyIntent:{runtimeStatus:'STARTING',probability:0},earlyImpulse:{runtimeStatus:'STARTING',probability:0},metrics:{}});
 const [diagFeedback,setDiagFeedback]=useState('');
 const [burstStatus,setBurstStatus]=useState<any>({ok:false,enabled:false,status:'STARTING',canFire:false,blocker:'Collecting live Burst gate evidence.',gates:[],sustained:{},beProgress:{},risk:{}});
 const loadMissed=async()=>{const r:any=await api.journalMissedPumps(12); if(r&&r.ok!==false) setMissed(r)};
 const loadPredictorStatus=async(manual=false)=>{if(manual)setDiagFeedback('Refreshing…'); const r:any=await api.fastSniperStatus(); setPredictorStatus(r||{}); if(manual){setDiagFeedback(r?.ok===false?'Refresh failed — retrying live feed.':`Updated ${new Date().toLocaleTimeString()}`); setTimeout(()=>setDiagFeedback(''),2500)}};
 const loadBurstStatus=async()=>{const r:any=await api.protectedBurstStatus(); setBurstStatus(r||{});};
 const load=async(initial=false)=>{await loadDashboard(initial); setTimeout(loadFeeds,50); setTimeout(loadStrategies,120)};
 useEffect(()=>{
   loadDashboard(true); setTimeout(loadFeeds,50); setTimeout(loadStrategies,120);
   // V13.5: 1.5s while a trade is open so the chart marker + live PnL badge track price;
   // 4s when flat. The old flat 4s sat on top of a 6s backend cache = up to 10s stale.
   // V13.7: 800ms while a trade is open. The backend hot path is ~1ms (_live_market 0.96ms,
   // _live_trades 0.18ms) and the engine now PUSHES both caches every ~1s loop, so the
   // browser poll was the binding constraint on how live the price marker felt.
   const dashId=setInterval(()=>{if(!document.hidden) void loadDashboard(false)},hasOpenTrade?1800:6000);
   const feedId=setInterval(()=>{if(!document.hidden) void loadFeeds()},120000);
   const stratId=setInterval(loadStrategies,90000);
   const missId=setInterval(()=>{if(!document.hidden) void loadMissed()},60000); loadMissed();
   return()=>{clearInterval(dashId);clearInterval(feedId);clearInterval(stratId);clearInterval(missId)};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[hasOpenTrade]);
 useEffect(()=>{
   void loadBurstStatus(); void loadPredictorStatus();
   const predictorId=setInterval(()=>{if(!document.hidden) void loadPredictorStatus()},1000);
   const burstId=setInterval(()=>{if(!document.hidden) void loadBurstStatus()},1000);
   return()=>{clearInterval(burstId);clearInterval(predictorId)};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 const account=data?.account||{}, market=data?.market||{}, trades=data?.trades||{active:[],pending:[],history:[]}, decision=data?.decision||{};
 const activeTrade=(trades.active||[])[0]; const hasActiveTrade=Boolean(activeTrade?.ticket);
 const connected=Boolean(market.connected||account.connected);
 const enabledStrategies=useMemo(()=>strategies.filter((s:any)=>s.enabled!==false),[strategies]);
 const selected=enabledStrategies.find((s:any)=>String(s.id)===String(decision.strategyId)||String(s.name)===String(decision.strategy))||enabledStrategies.find((s:any)=>String(s.name).toLowerCase().includes(String(market.activeStrategy||'').toLowerCase()))||enabledStrategies[0]||{};
 const aiActive=useMemo(()=>{const names=[selected?.id,selected?.name,decision?.strategy,decision?.selectedStrategy?.name,market?.activeStrategy].filter(Boolean).map((x:any)=>String(x).toLowerCase());return enabledStrategies.filter((s:any)=>names.some(n=>String(s.id||'').toLowerCase()===n || String(s.name||'').toLowerCase()===n || n.includes(String(s.name||'').toLowerCase()))).slice(0,4)},[enabledStrategies,selected,decision,market]);
 const activeDisplay=aiActive.length?aiActive:[selected].filter(Boolean);
 const priceNow=Number(market.price||0);
 // Directional bias (what the structure says) vs the GATED signal (whether to actually trade).
 // The Signals page shows the gated signal; the dashboard must match it to avoid the SELL-vs-WAIT conflict.
 const bias=(decision.side||market.side||'WAIT').toUpperCase();
 const action=String(decision.action||'WAIT').toUpperCase();
 const marketClosed=decision?.marketOpen===false||action==='MARKET_CLOSED';
 const side=action==='TAKE_TRADE'?bias:'WAIT';
 const sl=Number(decision.sl||market.sl||0); const tp1=Number(decision.tp1||market.tp1||0); const tp2=Number(decision.tp2||market.tp2||0); const tp3=Number(decision.tp3||market.tp3||0);
 // V12.99.3: only draw levels that are REAL. Previously these were drawn whenever a price
 // existed and fell back to fabricated priceNow±6/8/14, so the chart showed ENTRY/TP/SL lines
 // even with no open trade and no plan. Now: an open trade draws its actual levels; a live
 // TAKE_TRADE proposal draws a dashed PLAN; otherwise nothing is drawn.
 const levels=[] as any[];
 if(activeTrade&&Number(activeTrade.entry||activeTrade.entryPrice)>0){
   const e=Number(activeTrade.entry||activeTrade.entryPrice), asl=Number(activeTrade.sl||0), atp=Number(activeTrade.tp||0);
   levels.push({label:'ENTRY',price:e,color:'var(--blue)'});
   if(asl>0)levels.push({label:'SL',price:asl,color:'var(--red)'});
   if(atp>0)levels.push({label:'TP',price:atp,color:'var(--green)'});
 } else if(action==='TAKE_TRADE'&&sl>0&&tp1>0&&priceNow){
   levels.push({label:'PLAN',price:priceNow,color:'var(--blue)',dashed:true});
   levels.push({label:'SL',price:sl,color:'var(--red)',dashed:true});
   levels.push({label:'TP1',price:tp1,color:'var(--green)',dashed:true});
   if(tp2>0)levels.push({label:'TP2',price:tp2,color:'var(--gold)',dashed:true});
   if(tp3>0)levels.push({label:'TP3',price:tp3,color:'var(--gold-dark)',dashed:true});
 }
 const why=(data?.why||decision?.reasons||[]).slice(0,6);
 const spread=Number(market.spread||0);
 const spreadDisplay=spread>0?spread.toFixed(2):'—';
 const econ=feeds?.economicCalendar||{}; const mnews=feeds?.marketNews||{}; const macroFeed=feeds?.macro||{};
 const nextNews=econ.nextHighImpactUsdEvent||{}; const newsItems=mnews?.latestHeadline?[mnews.latestHeadline]:[];
 // V13.7: 'OFF' used to fire whenever `configured` was falsy — which included the case where
 // the request simply FAILED and the fallback blanked everything. A configured, working news
 // feed therefore read OFF. Now an unreachable backend says so honestly instead of lying.
 const feedsUnreachable=feeds?.unreachable===true||econ.status==='unknown';
 const newsLive=econ.status==='live'||mnews.status==='live';
 const newsStatusText=feedsUnreachable?'…':(newsLive?'LIVE':(econ.configured||mnews.configured?'CHECK':'OFF'));
 const gi=decision.goldIntelligence||{};
 const candles=useMemo(()=>Array.isArray(market.candles)?market.candles:[],[market.candles]);

 // Live entry markers: active trades + recently closed trades, snapped to candle bars
 const chartMarkers=useMemo(()=>{
   // V13.1: markers exist ONLY while a trade is live — its entry arrow, nothing else.
   // Historical WIN/LOSS confetti and AI-bias arrows are gone; the chart shows the market,
   // and decorates it only with the position you actually hold.
   const out:any[]=[];
   for(const t of (trades.active||[])){const ts=snapToCandle(toUnix(t.openTime),candles); if(ts)out.push({time:ts,side:t.direction||t.side||'BUY',text:`${(t.direction||t.side||'BUY')} ${t.lots||t.volume||''}`})}
   return out;
 },[trades.active,candles]);

 // Real multi-timeframe confluence from decision engine output
 const toArrow=(v:any,bull='↗',bear='↘')=>v===true||v==='bull'||v===1?bull:v===false||v==='bear'||v===-1?bear:'—';
 const m15Bull=Boolean(decision.computedBull ?? (bias==='BUY'));
 const h1Bull=Boolean(gi.h1Aligned);
 const rsiOk=Number(gi.rsi14||gi.rsi||50);
 const macdBull=Boolean(gi.macd?.bullish);
 const volOk=Boolean(gi.volumeConfirmed);
 const mtfRows=[
  {Layer:'Trend',     M15:connected?toArrow(m15Bull):'—', H1:connected?toArrow(h1Bull):'—', RSI:connected?(rsiOk>55?'↗':rsiOk<45?'↘':'→'):'—', MACD:connected?toArrow(macdBull):'—', Vol:connected?toArrow(volOk):'—'},
  {Layer:'Momentum',  M15:connected?(rsiOk>50?'↗':'↘'):'—', H1:connected?toArrow(h1Bull):'—', RSI:connected?`${Math.round(rsiOk)}`:'—', MACD:connected?toArrow(macdBull):'—', Vol:'—'},
  {Layer:'Structure', M15:connected?toArrow(gi.orderBlock?.found):'—', H1:connected?toArrow(h1Bull):'—', RSI:'—', MACD:'—', Vol:connected?toArrow(gi.fvg?.found):'—'},
  {Layer:'Volume',    M15:connected?toArrow(volOk):'—', H1:'—', RSI:'—', MACD:'—', Vol:'—'},
  {Layer:'Overall',   M15:connected?toArrow(m15Bull):'—', H1:connected?toArrow(h1Bull):'—', RSI:'—', MACD:'—', Vol:'—'},
 ];
 const vLabel=(v:string)=>v==='real_miss'?'REAL MISS':v==='would_have_hurt_first'?'WOULD HAVE HURT FIRST':v==='not_worth_it'?'NOT WORTH IT':v==='pending'?'SCORING…':v==='marginal'?'MARGINAL':'NO DATA';
 const vColor=(v:string)=>v==='real_miss'?'red':v==='would_have_hurt_first'?'amber':v==='pending'?'blue':'green';
 const missedCard=<Card className="missed-pump-card"><SectionTitle icon={<WifiOff size={16}/>} title="Missed Moves — Autopsy" right={<Tag color={(missed?.totals?.realMisses||0)>0?'red':'green'}>{(missed?.totals?.count||0)===0?'NONE LOGGED':`${missed?.totals?.realMisses||0} REAL / ${missed?.totals?.count||0}`}</Tag>}/>
  <p className="tiny muted">Every time gold prints pump-grade displacement and the bot does not enter, it records the first executable quote, then replays chronological broker bid/ask ticks. BUY replays enter at ask and exit at bid; SELL replays enter at bid and exit at ask. A move that went deeply against the entry before its best point is not counted as a clean miss.</p>
  {(missed?.items||[]).length>0&&<div className="grid grid-2" style={{marginTop:8}}>
    <Checklist items={[{label:'Real misses (big upside, small drawdown first)',value:String(missed?.totals?.realMisses??0),type:(missed?.totals?.realMisses||0)>0?'danger':'success'},{label:'Clean executable P/L (0.01 lot)',value:`$${Number(missed?.totals?.couldHaveMadeUsd||0).toFixed(2)}`,type:(missed?.totals?.couldHaveMadeUsd||0)>0?'warning':'success'},{label:'Gross executable P/L — all scored pumps',value:`$${Number(missed?.totals?.grossReachableUsd||0).toFixed(2)}`,type:(missed?.totals?.grossReachableUsd||0)>0?'warning':undefined}]}/>
    <Checklist items={[{label:'Logged (last 12)',value:String(missed?.totals?.count??0)},{label:'Would have hurt first',value:String(missed?.totals?.wouldHaveHurtFirst??0),type:'warning'},{label:'Still scoring (too recent)',value:String(missed?.totals?.pending??0),type:'warning'},{label:'No data / unscorable',value:String(missed?.totals?.noData??0),type:undefined}]}/>
  </div>}
  {(missed?.items||[]).length>0&&<div className="missed-scroll">
    {(missed?.items||[]).slice(0,missedShown).map((it:any,ix:number)=><div key={ix} className="missed-row">
      <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
        <Tag color={it.side==='BUY'?'green':'red'}>{it.side||'?'}</Tag>
        <strong className="tiny">{Number(it.price||0).toFixed(2)}</strong>
        <span className="tiny muted">{String(it.ts||'').replace('T',' ').replace('Z',' UTC')}</span>
        <span style={{flex:1}}/>
        <Tag color={vColor(String(it.verdict))}>{vLabel(String(it.verdict))}</Tag>
      </div>
      <p className="tiny muted" style={{marginTop:4}}>Blocked by: {String(it.blockedBy||'—').slice(0,150)}</p>
      {it.couldHaveMadeUsd!=null&&<p className="tiny" style={{marginTop:2}}>Could have reached <strong className={it.verdict==='real_miss'?'negative':'muted'}>${Number(it.couldHaveMadeUsd).toFixed(2)}</strong> · but first went <strong className="muted">${Number(it.worstFirstUsd||0).toFixed(2)}</strong> against · displacement {Number(it.displacementAtr||0).toFixed(2)} ATR</p>}
    </div>)}
  </div>}
  {(missed?.items||[]).length>0&&<div style={{marginTop:10}}>
    <button className="ghost-button" onClick={()=>{
      const its=missed?.items||[];
      const hdr=['ts','side','price','verdict','displacementAtr','couldHaveMadeUsd','worstFirstUsd','maxFavorableAtr','maxAdverseAtr','armedRetest','hadOpenPosition','sideInferred','blockedBy'];
      const rows=its.map((it:any)=>hdr.map(h=>`"${String(it[h]??'').replace(/"/g,'""')}"`).join(','));
      const csv=[hdr.join(','),...rows].join('\n');
      const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
      a.download=`missed_moves_${new Date().toISOString().slice(0,10)}.csv`;a.click();
    }}>⬇ Export CSV ({(missed?.items||[]).length})</button>
  </div>}
  {(missed?.items||[]).length>5&&<div className="missed-pager">
    <span className="tiny muted">Showing {Math.min(missedShown,(missed?.items||[]).length)} of {(missed?.items||[]).length}</span>
    <div className="button-wrap">
      {missedShown<(missed?.items||[]).length&&<button className="ghost-button" onClick={()=>setMissedShown((n:number)=>n+5)}>Show more</button>}
      {missedShown>5&&<button className="ghost-button" onClick={()=>setMissedShown(5)}>Collapse</button>}
    </div>
  </div>}
  {!(missed?.items||[]).length&&<p className="tiny muted" style={{marginTop:8}}>Nothing logged yet. A row appears only when displacement clears the counter-HTF bar and no entry was taken — if this stays empty while pumps happen, the bot is <em>taking</em> them, not missing them.</p>}
 </Card>;
 const newsCard=<Card className="news-status-card"><SectionTitle icon={<Newspaper size={16}/>} title="Live News & Calendar" right={<Tag color={feedsUnreachable?'amber':newsLive?'green':(econ.configured||mnews.configured)?'amber':'red'}>{newsStatusText}</Tag>}/><div className="grid grid-2 responsive-news-grid"><Checklist items={[{label:'Economic calendar',value:(econ.stale?'LIVE (cached)':econ.status)||'not configured',type:econ.status==='live'?'success':econ.configured?'warning':'danger'},{label:'USD blackout',value:econ.blackoutActive?'ACTIVE':'Clear',type:econ.blackoutActive?'danger':'success'},{label:'Next high-impact USD',value:nextNews.title?`${nextNews.title} (${Math.round(Number(nextNews.minutesToEvent||0))}m)`:'—',type:nextNews.title?'warning':'success'}]}/><Checklist items={[{label:'Market news',value:(mnews.stale?'LIVE (cached)':mnews.status)||'not configured',type:mnews.status==='live'?'success':mnews.configured?'warning':'danger'},{label:'Macro feed',value:(macroFeed.stale?'LIVE (cached)':macroFeed.status)||'not configured',type:macroFeed.status==='live'?'success':'warning'},{label:'Macro bias',value:macroFeed.goldBias||'NEUTRAL_GOLD',type:macroFeed.goldBias==='BULLISH_GOLD'?'success':macroFeed.goldBias==='BEARISH_GOLD'?'danger':'warning'}]}/></div>{newsItems[0]?.title&&<p className="tiny muted" style={{marginTop:8}}>Latest: <strong>{newsItems[0].title}</strong></p>}<p className="tiny muted" style={{marginTop:6}}>Persists across pages. Green = connected; amber = configured/error but cached if recently live; red = blank.</p></Card>;

 const burstGates=Array.isArray(burstStatus?.gates)?burstStatus.gates:[];
 const burstPassed=burstGates.filter((g:any)=>g?.passed===true).length;
 const burstRequired=Number(burstStatus?.sustained?.required||0);
 const burstCount=Number(burstStatus?.sustained?.count||0);
 const burstStatusText=String(burstStatus?.status||'STARTING').toUpperCase();
 const burstTone=burstStatusText==='FIRED'||burstStatus?.canFire?'green':burstStatusText==='BLOCKED'||burstStatusText==='FAILED'?'red':'gold';
 const burstCard=<Card className={`protected-burst-live-card burst-${burstStatusText.toLowerCase()}`}>
   <SectionTitle icon={<ShieldCheck size={18}/>} title="Protected Burst Intelligence" right={<Tag color={burstTone as any}>{burstStatus?.enabled?'ENGINE ON':'ENGINE OFF'} · {burstStatusText}</Tag>}/>
   <div className="burst-live-grid">
     <div className="burst-live-pulse"><span className="burst-orbit"/><strong>{Math.round(Number(burstStatus?.confidence||0))}%</strong><small>confidence</small></div>
     <Checklist items={[
       {label:'Deterministic BE arm',value:`${Math.round(Number(burstStatus?.beProgress?.progress||0)*100)}%`,type:burstStatus?.beProgress?.eligible?'success':'warning'},
       {label:'Sustained evidence',value:`${burstCount}/${burstRequired||'—'}`,type:burstStatus?.sustained?.stable?'success':'warning'},
       {label:'Continuation',value:`${Math.round(Number(burstStatus?.continuation||0))}%`,type:Number(burstStatus?.continuation||0)>=78?'success':'warning'},
       {label:'Immediate batch',value:burstStatus?.batchSize?`${burstStatus.batchSize} legs`:'Waiting',type:burstStatus?.batchSize?'success':'warning'},
       {label:'Gate trace',value:`${burstPassed}/${burstGates.length||0} passed`,type:burstStatus?.canFire?'success':'warning'},
       {label:'Account mode',value:String(burstStatus?.account?.accountTradeModeName||burstStatus?.account?.accountType||'UNKNOWN').toUpperCase(),type:['DEMO','CONTEST'].includes(String(burstStatus?.account?.accountTradeModeName||'').toUpperCase())?'success':'warning'},
     ]}/>
   </div>
   <div className="burst-blocker-line"><Activity size={14}/><span>{burstStatus?.blocker||'Evaluating every Burst gate.'}</span></div>
   <div className="burst-gate-trace">{burstGates.map((g:any,i:number)=><div key={`${g?.name||'gate'}-${i}`} className={g?.passed?'burst-gate-pass':'burst-gate-fail'}><span>{g?.passed?'✓':'×'}</span><strong>{g?.name||'Gate'}</strong><small>{g?.reason||''}</small></div>)}</div>
 </Card>;


 return <>
  <PageHeader title="Dashboard" subtitle="Institutional XAUUSD command center for live MT5 execution, AI confluence, risk and trade management." right={<button className="outline-button" onClick={()=>loadDashboard(true)}><RefreshCcw size={14}/> {loading?'Refreshing':'Refresh'}</button>}/>
  {(decision?.marketOpen===false||action==='MARKET_CLOSED')&&<Card className="alert-card" style={{marginBottom:16,borderColor:'var(--red)'}}><SectionTitle icon={<Moon size={18}/>} title="Market Closed" right={<Tag color="red">Standby</Tag>}/><p className="muted">{decision?.marketStatus||decision?.reason||'XAUUSD is outside trading hours.'}<br/>The bot is on standby — no new entries or wait-signals until the market reopens. Open trades stay protected by their broker SL.</p></Card>}
  {!connected&&<Card className="alert-card" style={{marginBottom:16}}><SectionTitle icon={<WifiOff size={18}/>} title="MT5 is not connected" right={<Tag color="gold">Demo data active</Tag>}/><p className="muted">Demo data is active — charts, signals and trades are fully populated. Connect MetaTrader 5, log in, then use Settings → Auto-detect Running MT5 to switch to live account data.</p></Card>}
  <div className="dashboard-top exact-top">
    <Card className="strategy-engine-card"><div className="engine-content"><div><SectionTitle icon={<BrainCircuit size={18}/>} title="Adaptive Strategy Engine" right={<Tag color="purple">AI</Tag>}/><p className="muted compact">AI analyzes live market conditions and automatically selects the best strategy from enabled strategies only.</p><div className="engine-row"><span>Mode:</span><Tag color="purple">Auto-select from Arsenal</Tag></div><div className="engine-row"><span>Active Strategy:</span><Tag color="green">{selected.name||decision.strategy||'Waiting for live confirmation'}</Tag></div><div className="strategy-chip-row">{activeDisplay.map((s:any,i:number)=><StrategyChip s={s} active={i===0} key={s.id||i}/>)}</div></div><img className="ai-node-img" src={aiNode} /></div></Card>
    <Card><SectionTitle title="Why this trade?"/><Checklist items={(why.length?why:['Waiting for live MT5 candle data before approving a trade.']).map((x:string)=>({label:x,value:connected?'Valid':'Pending',type:connected?'success':'warning'}))}/></Card>
    <Card className="signal-card"><SectionTitle title={`${market.symbol||'XAUUSD'} Signal`} right={<Tag color={connected?'green':'red'}>{connected?'Live':'Waiting'}</Tag>}/><div className="signal-card-body"><ConfidenceRing value={Math.round(Number(decision.confidence||market.confidence||0))} size={126}/><div className="signal-main"><div className={`trade-side ${marketClosed?'':side==='SELL'?'sell':side==='BUY'?'buy':''}`}>{marketClosed?'CLOSED':side}</div>{marketClosed?<span className="tiny muted" style={{marginTop:-6}}>Market closed — standby</span>:side==='WAIT'&&bias!=='WAIT'&&<span className="tiny muted" style={{marginTop:-6}}>Bias: <strong className={bias==='SELL'?'negative':'positive'}>{bias}</strong> · waiting for entry trigger</span>}<div className="button-wrap"><Tag color="green">{market.regime||'Regime Pending'}</Tag><Tag color="purple">AI Gate</Tag><Tag color="blue">{market.session||'Session'}</Tag></div>{spread>0&&<div className="spread-chip"><span>Spread</span><strong style={{color:spread>0.35?'var(--red)':'var(--green)'}}>{spreadDisplay}</strong></div>}</div></div></Card>
  </div>
  <div id="godmode-predictor-dashboard-anchor" />
  {burstCard}
  <div className="dashboard-main pixel-command-grid">
    <div className="grid command-left">
      <Card className="chart-card" style={{padding:'14px 14px 10px'}}>
        <SectionTitle title={`${market.symbol||'XAUUSD'} · Gold / U.S. Dollar`} right={<><Tag color={connected?'green':'gold'}>{connected?(market.demo?'DEMO':'LIVE'):'WAITING'}</Tag><span className="muted tiny" style={{marginLeft:4}}>{market.session||''}</span>{spread>0&&<span className="muted tiny" style={{marginLeft:8}}>Spread: <strong style={{color:spread>0.35?'var(--red)':'var(--text)'}}>{spreadDisplay}</strong></span>}</>}/>
        <LiveChart
          symbol={market.symbol||'XAUUSD'}
          height={500}
          candles={candles}
          markers={chartMarkers}
          liveTrade={hasActiveTrade?activeTrade:null}
          levels={hasActiveTrade?{entry:Number(activeTrade.entryPrice),sl:Number(activeTrade.sl),tp1:Number(activeTrade.tp1||activeTrade.tp),tp2:Number(activeTrade.tp2),tp3:Number(activeTrade.tp3)}:(side!=='WAIT'?{entry:priceNow,sl,tp1,tp2,tp3}:{})}
        />
      </Card>
      <Card><SectionTitle title="AI Agent Journal" right={<Tag color="purple">Live reasoning</Tag>}/><div className="grid grid-4 compact-journal"><Card soft><MiniCandleBlock/><p className="tiny muted">Market interpretation</p><strong>{market.regime||'Waiting'}</strong></Card><Card soft><p className="label">Decision</p><h3>{decision.action||'WAIT'}</h3><p className="tiny muted">{decision.quality||'No proven setup yet'}</p></Card><Card soft><p className="label">Optimisation Notes</p><p className="muted">Only GodMode magic/comment trades are used for learning.</p></Card><Card soft><p className="label">Model Confidence</p><ProgressBar value={Number(decision.confidence||0)}/><strong>{Math.round(Number(decision.confidence||0))}%</strong></Card></div></Card>
      <div className="grid grid-2"><Card><SectionTitle title="Analytics Overview"/><EquityCurve data={data?.equityCurve||[]} height={190}/></Card><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Enabled','Win Rate','Status']} rows={(data?.topStrategies?.length?data.topStrategies:enabledStrategies).slice(0,5)} renderCell={(r,c)=>{if(c==='Enabled')return <Tag color={r.enabled!==false?'green':'red'}>{r.enabled!==false?'ON':'OFF'}</Tag>;if(c==='Status')return <Tag color="green">Selectable</Tag>;if(c==='Strategy')return r.name||r.Strategy||'—';if(c==='Win Rate'){const wr=r.winRate??r['Win Rate'];return wr===undefined||wr===null?'—':(typeof wr==='number'?`${wr}%`:String(wr))}return '—'}}/></Card></div>
      {newsCard}
      {missedCard}
      <EconomicCalendar />
    </div>
    <div className="right-stack command-right">
      <Card><SectionTitle icon={<Network size={16}/>} title="Multi-Timeframe Confluence" right={<Tag color={connected?'green':'gold'}>{connected?'Live':'Demo'}</Tag>}/><DataTable columns={['Layer','M15','H1','RSI','MACD','Volume']} rows={mtfRows} renderCell={(r,c)=>{if(c==='Layer')return <strong>{r.Layer}</strong>;const v=r[c==='Volume'?'Vol':c];return <span style={{color:v==='↗'?'var(--green)':v==='↘'?'var(--red)':'var(--text-muted)',fontWeight:700}}>{v}</span>}}/></Card>
      <Card><SectionTitle icon={<Network size={16}/>} title="Higher-Timeframe Bias (H4 · D1)" right={<Tag color={gi.htfDailyBias==='BUY'?'green':gi.htfDailyBias==='SELL'?'red':'gold'}>{gi.htfDailyBias||'—'}</Tag>}/><Checklist items={[{label:'Daily (D1) trend',value:gi.d1Trend||'—',type:String(gi.d1Trend||'').includes('Bull')?'success':String(gi.d1Trend||'').includes('Bear')?'danger':'warning'},{label:'H4 trend',value:gi.h4Trend||'—',type:String(gi.h4Trend||'').includes('Bull')?'success':String(gi.h4Trend||'').includes('Bear')?'danger':'warning'},{label:'Trade aligned with HTF',value:gi.htfBiasAligned===false?'No':'Yes',type:gi.htfBiasAligned===false?'danger':'success'}]}/></Card>
      <Card className="management-card"><SectionTitle title="Trade Management" right={<Tag color={hasActiveTrade?'green':'gold'}>{hasActiveTrade?'Active trade':'No active trade'}</Tag>}/>{hasActiveTrade?<><TradeLine label="Entry Price" value={price(activeTrade.entryPrice)} /><TradeLine label="Current Price" value={price(activeTrade.currentPrice)} tone="green"/><TradeLine label="Stop Loss" value={price(activeTrade.sl)} tone="red"/><TradeLine label="Take Profit 1" value={price(activeTrade.tp1||activeTrade.tp)} tone="green"/><TradeLine label="R:R" value={activeTrade.rr||'Dynamic'}/><TradeLine label="Position Size" value={activeTrade.lots||activeTrade.volume}/><TradeLine label="AI Dynamic SL" value={activeTrade.aiDynamicStopLocked?'Locked / managing':'Armed'} tone={activeTrade.aiDynamicStopLocked?'green':'gold'}/><TradeLine label="Protected Floor" value={activeTrade.protectedFloor?price(activeTrade.protectedFloor):(activeTrade.beMoved?'BE floor active':'Waiting')} tone={activeTrade.beMoved?'green':'gold'}/><TradeLine label="Market Spread" value={spreadDisplay} tone={spread>0.35?'red':'green'}/><TradeLine label="Execution Quality" value={activeTrade.executionQuality||'Measured'} tone="green"/></>:<div className="empty-state compact"><strong>No active GodMode trade</strong><span className="muted tiny">Trade management timeline and AI Dynamic SL protection activate only after a bot trade is open.</span></div>}</Card>
      <Card><SectionTitle icon={<ShieldCheck size={18}/>} title="Account & Risk Overview" right={<button className="ghost-button" onClick={()=>{window.location.hash='/risk'}}>Manage Risk</button>}/><div className="grid grid-2"><MetricCard label="Balance" value={money(account.balance,account.currency)}/><MetricCard label="Equity" value={money(account.equity,account.currency)}/><MetricCard label="Daily PnL" value={money(account.dailyPnl,account.currency)}/><MetricCard label="Open Risk" value={money(account.openRisk,account.currency)}/></div><div style={{marginTop:12}}><ProgressBar value={Number(account.marginHealth||0)}/></div></Card>
      <Card><SectionTitle icon={<CalendarDays size={16}/>} title="Session Awareness"/><Checklist items={[{label:'Session',value:market.session||'—'},{label:'Spread',value:spreadDisplay,type:spread>0&&spread<0.35?'success':'warning'},{label:'Liquidity',value:connected?'Measured':'Waiting',type:connected?'success':'warning'}]}/></Card>
      <Card><SectionTitle icon={<Activity size={16}/>} title="MT5 Connection Health"/><Checklist items={[{label:'Source',value:market.source||'not_connected',type:connected?'success':'warning'},{label:'Price',value:price(market.price)},{label:'Spread',value:spreadDisplay,type:spread>0&&spread<0.35?'success':'warning'},{label:'Volatility',value:market.volatility||'—'},{label:'ATR 14',value:String(market.atr14||'—')}]}/></Card>
    </div>
  </div>
 </>
}
