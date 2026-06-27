import { useEffect, useMemo, useState } from 'react';
import { Activity, BrainCircuit, CalendarDays, Moon, Network, RefreshCcw, ShieldCheck, WifiOff } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, Tag } from '../components/ui';
import { EquityCurve, MiniCandleBlock } from '../components/Charts';
import { LiveChart } from '../components/LiveChart';
import { api } from '../lib/api';
import aiNode from '../assets/godmode-ai-node.svg';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const price=(v:any)=>Number(v||0)>0?Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:3}):'—';

function StrategyChip({s,active}:{s:any;active?:boolean}){return <Tag color={active?'green':'gold'}>{s?.name || s?.id || 'Waiting'}</Tag>}
function TradeLine({label,value,tone}:{label:string;value:any;tone?:'green'|'red'|'gold'}){return <div className="trade-line"><span>{label}</span><strong className={tone==='green'?'positive':tone==='red'?'negative':tone==='gold'?'gold':''}>{value}</strong></div>}

// Parse a "YYYY-MM-DD HH:MM:SS UTC" string to unix seconds
function toUnix(s:any):number{ if(!s) return 0; const t=Date.parse(String(s).replace(' UTC','Z').replace(' ','T')); return Number.isNaN(t)?0:Math.floor(t/1000); }
// Snap a timestamp to the nearest candle time so markers land on a bar
function snapToCandle(ts:number,candles:any[]):number{ if(!candles?.length) return ts; let best=candles[0].time,diff=Infinity; for(const c of candles){const d=Math.abs(c.time-ts); if(d<diff){diff=d;best=c.time}} return best; }

export default function Dashboard(){
 const [data,setData]=useState<any>(null),[strategies,setStrategies]=useState<any[]>([]),[loading,setLoading]=useState(true);
 // Silent polls after first load — prevents chart remount on each refresh
 const load=async(initial=false)=>{if(initial)setLoading(true); const [d,s]=await Promise.all([api.dashboard(),api.strategies()]); setData(d); setStrategies(Array.isArray(s)?s:[]); if(initial)setLoading(false)};
 useEffect(()=>{load(true); const id=setInterval(()=>load(false),5000); return()=>clearInterval(id)},[]);
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
 const sl=Number(decision.sl||market.sl||(bias==='SELL'?priceNow+6:priceNow-6)); const tp1=Number(decision.tp1||market.tp1||(bias==='SELL'?priceNow-8:priceNow+8)); const tp2=Number(decision.tp2||market.tp2||(bias==='SELL'?priceNow-14:priceNow+14)); const tp3=Number(decision.tp3||market.tp3||(bias==='SELL'?priceNow-22:priceNow+22));
 const levels=[] as any[]; if(priceNow){levels.push({label:'ENTRY',price:priceNow,color:'var(--blue)'}); if(sl>0)levels.push({label:'SL',price:sl,color:'var(--red)'}); if(tp1>0)levels.push({label:'TP1',price:tp1,color:'var(--green)'}); if(tp2>0)levels.push({label:'TP2',price:tp2,color:'var(--gold)'}); if(tp3>0)levels.push({label:'TP3',price:tp3,color:'var(--gold-dark)'})}
 const why=(data?.why||decision?.reasons||[]).slice(0,6);
 const spread=Number(market.spread||0);
 const spreadDisplay=spread>0?spread.toFixed(2):'—';
 const gi=decision.goldIntelligence||{};
 const candles=useMemo(()=>Array.isArray(market.candles)?market.candles:[],[market.candles]);

 // Live entry markers: active trades + recently closed trades, snapped to candle bars
 const chartMarkers=useMemo(()=>{
   const out:any[]=[];
   const active=trades.active||[]; const hist=(trades.history||[]).slice(0,12);
   for(const t of active){const ts=snapToCandle(toUnix(t.openTime),candles); if(ts)out.push({time:ts,side:t.direction||t.side||'BUY',text:`${(t.direction||t.side||'BUY')} ${t.lots||t.volume||''}`})}
   for(const t of hist){const ts=snapToCandle(toUnix(t.closeTime||t.openTime),candles); if(ts)out.push({time:ts,side:t.direction||t.side||'BUY',text:Number(t.pnlUsd)>=0?'WIN':'LOSS'})}
   // live AI bias marker on the latest bar (shows direction even while waiting for trigger)
   if(bias!=='WAIT'&&candles.length){out.push({time:candles[candles.length-1].time,side:bias,text:side==='WAIT'?`Bias ${bias}`:`AI ${bias}`})}
   return out;
 },[trades.active,trades.history,candles,bias,side]);

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

 return <>
  <PageHeader title="Dashboard" subtitle="Institutional XAUUSD command center for live MT5 execution, AI confluence, risk and trade management." right={<button className="outline-button" onClick={()=>load(true)}><RefreshCcw size={14}/> {loading?'Refreshing':'Refresh'}</button>}/>
  {(decision?.marketOpen===false||action==='MARKET_CLOSED')&&<Card className="alert-card" style={{marginBottom:16,borderColor:'var(--red)'}}><SectionTitle icon={<Moon size={18}/>} title="Market Closed" right={<Tag color="red">Standby</Tag>}/><p className="muted">{decision?.marketStatus||decision?.reason||'XAUUSD is outside trading hours.'}<br/>The bot is on standby — no new entries or wait-signals until the market reopens. Open trades stay protected by their broker SL.</p></Card>}
  {!connected&&<Card className="alert-card" style={{marginBottom:16}}><SectionTitle icon={<WifiOff size={18}/>} title="MT5 is not connected" right={<Tag color="gold">Demo data active</Tag>}/><p className="muted">Demo data is active — charts, signals and trades are fully populated. Connect MetaTrader 5, log in, then use Settings → Auto-detect Running MT5 to switch to live account data.</p></Card>}
  <div className="dashboard-top exact-top">
    <Card className="strategy-engine-card"><div className="engine-content"><div><SectionTitle icon={<BrainCircuit size={18}/>} title="Adaptive Strategy Engine" right={<Tag color="purple">AI</Tag>}/><p className="muted compact">AI analyzes live market conditions and automatically selects the best strategy from enabled strategies only.</p><div className="engine-row"><span>Mode:</span><Tag color="purple">Auto-select from Arsenal</Tag></div><div className="engine-row"><span>Active Strategy:</span><Tag color="green">{selected.name||decision.strategy||'Waiting for live confirmation'}</Tag></div><div className="strategy-chip-row">{activeDisplay.map((s:any,i:number)=><StrategyChip s={s} active={i===0} key={s.id||i}/>)}</div></div><img className="ai-node-img" src={aiNode} /></div></Card>
    <Card><SectionTitle title="Why this trade?"/><Checklist items={(why.length?why:['Waiting for live MT5 candle data before approving a trade.']).map((x:string)=>({label:x,value:connected?'Valid':'Pending',type:connected?'success':'warning'}))}/></Card>
    <Card className="signal-card"><SectionTitle title={`${market.symbol||'XAUUSD'} Signal`} right={<Tag color={connected?'green':'red'}>{connected?'Live':'Waiting'}</Tag>}/><div className="signal-card-body"><ConfidenceRing value={Math.round(Number(decision.confidence||market.confidence||0))} size={126}/><div className="signal-main"><div className={`trade-side ${marketClosed?'':side==='SELL'?'sell':side==='BUY'?'buy':''}`}>{marketClosed?'CLOSED':side}</div>{marketClosed?<span className="tiny muted" style={{marginTop:-6}}>Market closed — standby</span>:side==='WAIT'&&bias!=='WAIT'&&<span className="tiny muted" style={{marginTop:-6}}>Bias: <strong className={bias==='SELL'?'negative':'positive'}>{bias}</strong> · waiting for entry trigger</span>}<div className="button-wrap"><Tag color="green">{market.regime||'Regime Pending'}</Tag><Tag color="purple">AI Gate</Tag><Tag color="blue">{market.session||'Session'}</Tag></div>{spread>0&&<div className="spread-chip"><span>Spread</span><strong style={{color:spread>0.35?'var(--red)':'var(--green)'}}>{spreadDisplay}</strong></div>}</div></div></Card>
  </div>
  <div className="dashboard-main pixel-command-grid">
    <div className="grid command-left">
      <Card className="chart-card" style={{padding:'14px 14px 10px'}}>
        <SectionTitle title={`${market.symbol||'XAUUSD'} · Gold / U.S. Dollar`} right={<><Tag color={connected?'green':'gold'}>{connected?(market.demo?'DEMO':'LIVE'):'WAITING'}</Tag><span className="muted tiny" style={{marginLeft:4}}>{market.session||''}</span>{spread>0&&<span className="muted tiny" style={{marginLeft:8}}>Spread: <strong style={{color:spread>0.35?'var(--red)':'var(--text)'}}>{spreadDisplay}</strong></span>}</>}/>
        <LiveChart
          symbol={market.symbol||'XAUUSD'}
          height={500}
          candles={candles}
          markers={chartMarkers}
          levels={hasActiveTrade?{entry:Number(activeTrade.entryPrice),sl:Number(activeTrade.sl),tp1:Number(activeTrade.tp1||activeTrade.tp),tp2:Number(activeTrade.tp2),tp3:Number(activeTrade.tp3)}:(side!=='WAIT'?{entry:priceNow,sl,tp1,tp2,tp3}:{})}
        />
      </Card>
      <Card><SectionTitle title="AI Agent Journal" right={<Tag color="purple">Live reasoning</Tag>}/><div className="grid grid-4 compact-journal"><Card soft><MiniCandleBlock/><p className="tiny muted">Market interpretation</p><strong>{market.regime||'Waiting'}</strong></Card><Card soft><p className="label">Decision</p><h3>{decision.action||'WAIT'}</h3><p className="tiny muted">{decision.quality||'No proven setup yet'}</p></Card><Card soft><p className="label">Optimisation Notes</p><p className="muted">Only GodMode magic/comment trades are used for learning.</p></Card><Card soft><p className="label">Model Confidence</p><ProgressBar value={Number(decision.confidence||0)}/><strong>{Math.round(Number(decision.confidence||0))}%</strong></Card></div></Card>
      <div className="grid grid-2"><Card><SectionTitle title="Analytics Overview"/><EquityCurve data={data?.equityCurve||[]} height={190}/></Card><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Enabled','Win Rate','Status']} rows={(data?.topStrategies?.length?data.topStrategies:enabledStrategies).slice(0,5)} renderCell={(r,c)=>{if(c==='Enabled')return <Tag color={r.enabled!==false?'green':'red'}>{r.enabled!==false?'ON':'OFF'}</Tag>;if(c==='Status')return <Tag color="green">Selectable</Tag>;if(c==='Strategy')return r.name||r.Strategy||'—';if(c==='Win Rate'){const wr=r.winRate??r['Win Rate'];return wr===undefined||wr===null?'—':(typeof wr==='number'?`${wr}%`:String(wr))}return '—'}}/></Card></div>
    </div>
    <div className="right-stack command-right">
      <Card><SectionTitle icon={<Network size={16}/>} title="Multi-Timeframe Confluence" right={<Tag color={connected?'green':'gold'}>{connected?'Live':'Demo'}</Tag>}/><DataTable columns={['Layer','M15','H1','RSI','MACD','Volume']} rows={mtfRows} renderCell={(r,c)=>{if(c==='Layer')return <strong>{r.Layer}</strong>;const v=r[c==='Volume'?'Vol':c];return <span style={{color:v==='↗'?'var(--green)':v==='↘'?'var(--red)':'var(--text-muted)',fontWeight:700}}>{v}</span>}}/></Card>
      <Card><SectionTitle icon={<Network size={16}/>} title="Higher-Timeframe Bias (H4 · D1)" right={<Tag color={gi.htfDailyBias==='BUY'?'green':gi.htfDailyBias==='SELL'?'red':'gold'}>{gi.htfDailyBias||'—'}</Tag>}/><Checklist items={[{label:'Daily (D1) trend',value:gi.d1Trend||'—',type:String(gi.d1Trend||'').includes('Bull')?'success':String(gi.d1Trend||'').includes('Bear')?'danger':'warning'},{label:'H4 trend',value:gi.h4Trend||'—',type:String(gi.h4Trend||'').includes('Bull')?'success':String(gi.h4Trend||'').includes('Bear')?'danger':'warning'},{label:'Trade aligned with HTF',value:gi.htfBiasAligned===false?'No':'Yes',type:gi.htfBiasAligned===false?'danger':'success'}]}/></Card>
      <Card className="management-card"><SectionTitle title="Trade Management" right={<Tag color={hasActiveTrade?'green':'gold'}>{hasActiveTrade?'Active trade':'No active trade'}</Tag>}/>{hasActiveTrade?<><TradeLine label="Entry Price" value={price(activeTrade.entryPrice)} /><TradeLine label="Current Price" value={price(activeTrade.currentPrice)} tone="green"/><TradeLine label="Stop Loss" value={price(activeTrade.sl)} tone="red"/><TradeLine label="Take Profit 1" value={price(activeTrade.tp1||activeTrade.tp)} tone="green"/><TradeLine label="R:R" value={activeTrade.rr||'Dynamic'}/><TradeLine label="Position Size" value={activeTrade.lots||activeTrade.volume}/><TradeLine label="Trailing Stop" value={activeTrade.trailingStop?'Active':'Armed'} tone="green"/><TradeLine label="Break-even" value={activeTrade.beMoved?'Moved to BE':'Armed'} tone={activeTrade.beMoved?'green':'gold'}/><TradeLine label="Market Spread" value={spreadDisplay} tone={spread>0.35?'red':'green'}/><TradeLine label="Execution Quality" value={activeTrade.executionQuality||'Measured'} tone="green"/></>:<div className="empty-state compact"><strong>No active GodMode trade</strong><span className="muted tiny">Trade management timeline, BE and trailing controls activate only after a bot trade is open.</span></div>}</Card>
      <Card><SectionTitle icon={<ShieldCheck size={18}/>} title="Account & Risk Overview" right={<button className="ghost-button" onClick={()=>{window.location.hash='/risk'}}>Manage Risk</button>}/><div className="grid grid-2"><MetricCard label="Balance" value={money(account.balance,account.currency)}/><MetricCard label="Equity" value={money(account.equity,account.currency)}/><MetricCard label="Daily PnL" value={money(account.dailyPnl,account.currency)}/><MetricCard label="Open Risk" value={money(account.openRisk,account.currency)}/></div><div style={{marginTop:12}}><ProgressBar value={Number(account.marginHealth||0)}/></div></Card>
      <div className="grid grid-2 mini-side"><Card><SectionTitle icon={<CalendarDays size={16}/>} title="Session Awareness"/><Checklist items={[{label:'Session',value:market.session||'—'},{label:'Spread',value:spreadDisplay,type:spread>0&&spread<0.35?'success':'warning'},{label:'Liquidity',value:connected?'Measured':'Waiting',type:connected?'success':'warning'}]}/></Card><Card><SectionTitle title="Economic News Filter"/><Checklist items={[{label:'High-impact news',value:'Filtered'},{label:'Next event',value:'—'}]}/></Card></div>
      <Card><SectionTitle icon={<Activity size={16}/>} title="MT5 Connection Health"/><Checklist items={[{label:'Source',value:market.source||'not_connected',type:connected?'success':'warning'},{label:'Price',value:price(market.price)},{label:'Spread',value:spreadDisplay,type:spread>0&&spread<0.35?'success':'warning'},{label:'Volatility',value:market.volatility||'—'},{label:'ATR 14',value:String(market.atr14||'—')}]}/></Card>
    </div>
  </div>
 </>
}
