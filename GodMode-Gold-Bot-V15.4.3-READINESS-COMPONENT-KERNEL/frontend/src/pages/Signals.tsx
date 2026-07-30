import { useEffect, useMemo, useState } from 'react';
import { Download, PlayCircle, RefreshCcw, RotateCcw, SlidersHorizontal, X } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, PageHeader, ProgressBar, SectionTitle, SideBadge, Tag, MiniSparkline } from '../components/ui';
import { api, downloadExport } from '../lib/api';
import { usePoll } from '../lib/usePoll';
const notify=(title:string,body:string,sound='success')=>window.dispatchEvent(new CustomEvent('godmode:notify',{detail:{title,body,sound}}));
const price=(v:any)=>Number(v||0)>0?Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:3}):'—';
function Gauge({value}:{value:number}){return <div className="execution-gauge"><ConfidenceRing value={value} size={112} label="Readiness"/><strong>{value>=70?'High':value>=50?'Medium':'Low'}</strong></div>}
export default function Signals(){
  const [signals,setSignals]=useState<any[]>([]); const [market,setMarket]=useState<any>({});
  const [pair,setPair]=useState('XAUUSD'),[session,setSession]=useState('ALL'),[strategy,setStrategy]=useState('ALL'),[conf,setConf]=useState('ALL'),[status,setStatus]=useState('ALL');
  const [filterOpen,setFilterOpen]=useState(true); const [message,setMessage]=useState('');
  const normaliseSignals=(raw:any):any[]=>{
    if(Array.isArray(raw)) return raw;
    if(Array.isArray(raw?.signals)) return raw.signals;
    if(Array.isArray(raw?.items)) return raw.items;
    console.warn('[Signals] Non-array signal payload ignored', raw);
    return [];
  };
  const load=async()=>{
    try{
      const [sigRaw, mktRaw] = await Promise.all([api.signals(), api.marketSnapshot()]);
      setSignals(normaliseSignals(sigRaw));
      setMarket(mktRaw && typeof mktRaw==='object' ? mktRaw : {});
    }catch(err){
      console.error('[Signals] load failed', err);
      setSignals([]);
      setMarket({connected:false, source:'frontend_error', message:String(err)});
    }
  };
  usePoll(load,5000);
  const filtered=useMemo(()=>{
    const safeSignals=Array.isArray(signals)?signals:[];
    return safeSignals.filter(s=>(pair==='ALL'||(s.pair||s.symbol||'XAUUSD')===pair)&&(session==='ALL'||s.session===session)&&(strategy==='ALL'||String(s.strategy||'').includes(strategy))&&(status==='ALL'||s.status===status)&&(conf==='ALL'||Number(s.confidence||0)>=Number(conf)));
  },[signals,pair,session,strategy,status,conf]);
  const selected=filtered[0] || (market.connected?{symbol:market.symbol,side:market.side,price:market.price,confidence:market.confidence,strategy:market.activeStrategy,session:market.session,timeframe:market.timeframe,status:'Waiting'}:null);
  const show=(m:string,ok=true)=>{setMessage(m); notify(ok?'Signal action':'Signal blocked',m,ok?'success':'warning'); setTimeout(()=>setMessage(''),3500)};
  const execute=()=>{if(!selected){show('No valid live signal selected yet.',false);return} const side=String(selected.side||'').toUpperCase(); if(!['BUY','SELL'].includes(side)){show('Selected item is WAIT/blocked, not an executable BUY/SELL signal.',false);return} api.executeTrade({symbol:selected.symbol||selected.pair||'XAUUSD', side, requireAiApproval:true, comment:'GODMODE_signal_execute'}).then((r:any)=>{show(r?.message || (r?.ok?'Signal execution sent.':'Signal execution blocked.'), Boolean(r?.ok)); load();})};
  const readiness=Math.min(100,Math.round(Number(selected?.confidence||0)));
  const confluence=[{label:'HTF alignment (H1, H4, D1)',value:market.connected?'Bullish':'Pending',type:market.connected?'success':'warning'},{label:'Trend direction / EMA 50',value:'Checked'},{label:'Order Block / Liquidity',value:'Confirmed'},{label:'Break of Structure',value:'Confirmed'},{label:'Momentum',value:'Favorable'},{label:'News Impact',value:'Low impact'}] as any[];
  return <div className="layout-right signals-layout">
    <div>
      <PageHeader title="Signals" subtitle="Real-time, AI-powered trading signals with institutional-grade confluence." right={<><button className="outline-button" onClick={()=>setFilterOpen(!filterOpen)}><SlidersHorizontal size={14}/> Filters</button><button className="outline-button" onClick={load}><RefreshCcw size={14}/> Refresh</button><button className="outline-button" onClick={()=>downloadExport('signals','json')}><Download size={14}/> Export</button></>}/>
      {message&&<Card className="action-banner" style={{marginBottom:16}}><span>{message}</span></Card>}
      {filterOpen&&<Card className="filter-card"><div className="filter-row signal-filter-row"><label><span>Pair</span><select className="input" value={pair} onChange={e=>setPair(e.target.value)}><option>XAUUSD</option><option>ALL</option></select></label><label><span>Session</span><select className="input" value={session} onChange={e=>setSession(e.target.value)}><option>ALL</option><option>London</option><option>New York</option><option>Asia</option></select></label><label><span>Strategy</span><select className="input" value={strategy} onChange={e=>setStrategy(e.target.value)}><option>ALL</option><option>Trend</option><option>Liquidity</option><option>London</option><option>Mean</option></select></label><label><span>Confidence</span><select className="input" value={conf} onChange={e=>setConf(e.target.value)}><option>ALL</option><option value="70">70%+</option><option value="80">80%+</option><option value="90">90%+</option></select></label><label><span>Status</span><select className="input" value={status} onChange={e=>setStatus(e.target.value)}><option>ALL</option><option>Active</option><option>Waiting</option><option>Completed</option></select></label><button className="ghost-button" onClick={()=>{setPair('XAUUSD');setSession('ALL');setStrategy('ALL');setConf('ALL');setStatus('ALL')}}><RotateCcw size={14}/> Reset Filters</button></div></Card>}
      <Card style={{marginTop:16}}><SectionTitle title="LIVE SIGNAL STREAM" right={<Tag color={market.connected?'green':'red'}>{market.connected?'Auto-refresh 15s':'Waiting for MT5'}</Tag>}/><div className="signal-strip">{filtered.slice(0,8).map((s,i)=><div className="signal-tile" key={i}><div className="button-wrap"><strong>{s.pair||s.symbol||'XAUUSD'}</strong><SideBadge side={s.side}/></div><div className="tiny muted">{s.time||'live'} · {price(s.price)}</div><MiniSparkline color={s.side==='SELL'?'var(--red)':s.side==='BUY'?'var(--green)':'var(--amber)'}/></div>)}{!filtered.length&&<p className="muted">No live signal yet. The AI is waiting for a valid setup instead of showing fake signals.</p>}</div></Card>
      <Card style={{marginTop:16}}><SectionTitle title="Featured High-Confidence Signals" right={<button className="ghost-button" onClick={()=>setStatus('ALL')}>View All Signals →</button>}/><div className="grid grid-3">{filtered.slice(0,3).map((s,i)=><Card soft className="featured-signal" key={i}><div className="button-wrap space-between"><strong>{s.symbol||s.pair||'XAUUSD'}</strong><SideBadge side={s.side}/>{s.isPrimary||i===0?<Tag color="green">Top Pick</Tag>:<Tag color="purple">Candidate</Tag>}</div><h2 className={s.side==='SELL'?'negative':'positive'}>{price(s.price||s.entryPrice)}</h2><MiniSparkline color={s.side==='SELL'?'var(--red)':s.side==='BUY'?'var(--green)':'var(--amber)'}/><div className="signal-card-grid"><ConfidenceRing value={Number(s.confidence||0)} size={78}/><div><div className="detail-row"><span>Strategy</span><strong>{s.strategy||'—'}</strong></div><div className="detail-row"><span>Timeframe</span><strong>{s.timeframe||'M15'}</strong></div><div className="detail-row"><span>Session</span><strong>{s.session||market.session||'—'}</strong></div></div></div><button className="outline-button" onClick={()=>show('Signal selected in right inspector.')}>View Details</button></Card>)}{!filtered.length&&<p className="muted">No featured live signals yet.</p>}</div></Card>
      <Card style={{marginTop:16}}><SectionTitle title="Recent Signal History" right={<button className="outline-button" onClick={()=>downloadExport('signals','csv')}><Download size={14}/> Export</button>}/><DataTable columns={['Time','Pair','Signal','Strategy','Timeframe','Entry Price','SL','TP1','TP2','Confidence','Status','Result']} rows={filtered} renderCell={(r,c)=>{if(c==='Signal')return <SideBadge side={r.side}/>;if(c==='Confidence')return <div style={{minWidth:100}}><span className="tiny positive">{r.confidence||0}%</span><ProgressBar value={Number(r.confidence||0)}/></div>;if(c==='Status')return <Tag color={r.status==='Active'?'green':'gold'}>{r.status||'Waiting'}</Tag>;const map:any={'Pair':'symbol','Entry Price':'entryPrice','TP1':'tp1','TP2':'tp2'}; return r[map[c]||c.toLowerCase()]??'—'}}/></Card>
    </div>
    <div className="right-stack signal-inspector side-panel-sticky">
      <Card><SectionTitle title="SIGNAL DETAILS" right={<><Tag color={selected?'green':'red'}>{selected?'Active Signal':'No Signal'}</Tag><button className="ghost-button" onClick={()=>setFilterOpen(false)}><X size={13}/></button></>}/>{selected?<><div className="button-wrap space-between"><h2>{selected.symbol||selected.pair||'XAUUSD'}</h2><SideBadge side={selected.side||'WAIT'}/></div><h1 className={selected.side==='SELL'?'negative':'positive'}>{price(selected.price||selected.entryPrice||market.price)}</h1><div className="button-wrap"><Tag color="blue">{selected.strategy||'Strategy pending'}</Tag><Tag color="purple">{selected.timeframe||'M15'}</Tag><Tag color="gold">{selected.session||market.session||'Session'}</Tag></div><ConfidenceRing value={Number(selected.confidence||0)} size={106}/></>:<p className="muted">Waiting for the first live AI signal.</p>}</Card>
      <Card><SectionTitle title="AI SIGNAL REASON"/><p className="muted">{selected?.reason || (market.connected ? 'Price is evaluated against trend, liquidity, structure, session and execution quality before a trade can be approved.' : 'Connect MT5 to generate a true AI reason.')}</p></Card>
      <Card><SectionTitle title="CONFLUENCE CHECKLIST"/><Checklist items={confluence}/><div className="detail-row"><span>Confluence Score</span><strong className="positive">{selected?`${Math.round((Number(selected.confidence||0)/100)*7*10)/10} / 7`:'—'}</strong></div></Card>
      <Card><SectionTitle title="TRADE LEVELS"/><TradeLevel label="Entry Price" value={price(selected?.entryPrice||selected?.price||market.price)}/><TradeLevel label="Stop Loss" value={price(selected?.sl)} danger/><TradeLevel label="Take Profit 1" value={price(selected?.tp1)} success/><TradeLevel label="Take Profit 2" value={price(selected?.tp2)} success/></Card>
      <Card><SectionTitle title="RISK & REWARD"/><div className="grid grid-2"><Metric label="Risk" value={selected?.risk||'—'}/><Metric label="Reward 1" value={selected?.reward1||'—'}/><Metric label="RR Ratio TP1" value={selected?.rr||'—'}/><Metric label="Position" value={selected?.lots||'AI lot'}/></div></Card>
      <Card><SectionTitle title="EXECUTION READINESS"/><Gauge value={readiness}/><Checklist items={[{label:'Spread',value:String(market.spread??'—')},{label:'Volatility',value:market.volatility||'—'},{label:'Liquidity',value:market.connected?'Live':'Waiting',type:market.connected?'success':'warning'},{label:'Slippage Risk',value:'Measured'}]}/></Card>
      <button className="gold-button full" onClick={execute}><PlayCircle size={15}/> Execute Signal</button>
    </div>
  </div>
}
function TradeLevel({label,value,danger,success}:{label:string;value:any;danger?:boolean;success?:boolean}){return <div className="detail-row"><span>{label}</span><strong className={danger?'negative':success?'positive':''}>{value}</strong></div>}
function Metric({label,value}:{label:string;value:any}){return <div className="mini-metric"><span>{label}</span><strong>{value}</strong></div>}
