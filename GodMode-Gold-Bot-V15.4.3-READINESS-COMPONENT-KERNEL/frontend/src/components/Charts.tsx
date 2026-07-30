import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi } from 'lightweight-charts';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts';
import { CandlestickPreview, Tag } from './ui';

type Candle = { time?: string | number; open?: number; high?: number; low?: number; close?: number; ema20?: number; ema50?: number; ema200?: number };
type Level = { label:string; price:number; color?:string; style?:number };

function cssVar(name:string){return getComputedStyle(document.documentElement).getPropertyValue(name).trim()}
function normalizeTime(t:any, index:number){
  if (typeof t === 'number' && Number.isFinite(t)) return t;
  if (typeof t === 'string') { const parsed = Date.parse(t); if (Number.isFinite(parsed)) return Math.floor(parsed/1000); }
  return Math.floor(Date.now()/1000) - (120-index)*900;
}
export function EmptyChart({ message='Waiting for live MT5 data' }: { message?: string }) {return <div className="empty-state"><strong>{message}</strong><span className="muted tiny">Open MetaTrader 5, log in, and keep the backend running.</span></div>}

/**
 * LiveTradeViewChart.
 *
 * The previous implementation listed `JSON.stringify(rows.slice(-120))` as an effect dependency
 * and called `createChart` inside that effect. Two consequences, both severe on a page that polls
 * every 1.8 seconds with a position open:
 *
 *  • Two full JSON serialisations of the candle set ran on EVERY React render just to compute the
 *    dependency string, whether or not anything had changed.
 *  • Whenever any candle value moved — which is what "live" means — the whole chart was destroyed
 *    (`chart.remove()`) and rebuilt from scratch: new canvas, new series, new price lines, new
 *    ResizeObserver. That is the most expensive operation this component can perform, and it also
 *    threw away the user's zoom and pan, so the chart could not actually be explored while live.
 *
 * The chart is now created once and fed through `setData`, which is what lightweight-charts is
 * designed for. Series handles are kept in refs; theme changes re-apply options in place.
 */
export function LiveTradeViewChart({data=[],levels=[]}:{data?:Candle[];levels?:Level[]}){
  const ref=useRef<HTMLDivElement|null>(null);
  const chartRef=useRef<IChartApi|null>(null);
  const candleRef=useRef<any>(null);
  const emaRefs=useRef<Record<string,any>>({});
  const priceLinesRef=useRef<any[]>([]);
  const [chartError,setChartError]=useState<string>('');

  const rows=useMemo(()=>(data||[]).map((c,i)=>({time: normalizeTime(c.time,i),open:Number(c.open??c.close??0),high:Number(c.high??c.close??0),low:Number(c.low??c.close??0),close:Number(c.close??0),ema20:Number(c.ema20??c.close??0),ema50:Number(c.ema50??c.close??0),ema200:Number(c.ema200??c.close??0)})).filter(x=>Number.isFinite(x.open)&&Number.isFinite(x.high)&&Number.isFinite(x.low)&&Number.isFinite(x.close)&&x.open>0&&x.high>0&&x.low>0&&x.close>0),[data]);

  const applyTheme=(chart:IChartApi)=>{
    const isDark=document.documentElement.getAttribute('data-theme')!=='light';
    chart.applyOptions({
      layout:{background:{type:ColorType.Solid,color:cssVar('--surface')||'#fff'},textColor:cssVar('--text-muted')||'#6f7787'},
      grid:{vertLines:{color:cssVar('--chart-grid')||'rgba(148,163,184,.14)'},horzLines:{color:cssVar('--chart-grid')||'rgba(148,163,184,.14)'}},
      rightPriceScale:{borderColor:cssVar('--border-soft')||'#eadfcb'},
      timeScale:{borderColor:cssVar('--border-soft')||'#eadfcb'},
    });
    emaRefs.current.ema200?.applyOptions({color:isDark?'#7b8494':'#c1b7a5'});
  };

  // ---- create once ----
  useEffect(()=>{
    if(!ref.current) return;
    try{
      const chart=createChart(ref.current,{autoSize:true,layout:{background:{type:ColorType.Solid,color:cssVar('--surface')||'#fff'},textColor:cssVar('--text-muted')||'#6f7787',fontFamily:'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',fontSize:11},grid:{vertLines:{color:cssVar('--chart-grid')||'rgba(148,163,184,.14)'},horzLines:{color:cssVar('--chart-grid')||'rgba(148,163,184,.14)'}},rightPriceScale:{borderColor:cssVar('--border-soft')||'#eadfcb'},timeScale:{borderColor:cssVar('--border-soft')||'#eadfcb',timeVisible:true,secondsVisible:false,fixLeftEdge:true,fixRightEdge:true},crosshair:{mode:1},handleScroll:true,handleScale:true});
      chartRef.current=chart;
      candleRef.current=chart.addCandlestickSeries({upColor:cssVar('--green')||'#22c55e',downColor:cssVar('--red')||'#ef4444',borderUpColor:cssVar('--green')||'#22c55e',borderDownColor:cssVar('--red')||'#ef4444',wickUpColor:cssVar('--green')||'#22c55e',wickDownColor:cssVar('--red')||'#ef4444',priceLineVisible:false});
      emaRefs.current.ema20=chart.addLineSeries({color:cssVar('--green')||'#22c55e',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
      emaRefs.current.ema50=chart.addLineSeries({color:cssVar('--blue')||'#3b82f6',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
      emaRefs.current.ema200=chart.addLineSeries({color:'#7b8494',lineWidth:1,priceLineVisible:false,lastValueVisible:false});
      applyTheme(chart);
      // autoSize installs the library's own resize handling; a second ResizeObserver calling
      // applyOptions({width}) on top of it just doubles the reflow work on every resize.
      const mo=new MutationObserver(()=>applyTheme(chart));
      mo.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
      return()=>{mo.disconnect(); chart.remove(); chartRef.current=null; candleRef.current=null; emaRefs.current={}; priceLinesRef.current=[]};
    }catch(e:any){console.error('[GodMode chart]', e); setChartError(e?.message||'Chart rendering failed');}
  },[]);

  // ---- feed data in place ----
  useEffect(()=>{
    const candle=candleRef.current;
    if(!candle||!rows.length) return;
    try{
      setChartError('');
      candle.setData(rows.map(({time,open,high,low,close})=>({time,open,high,low,close})) as any);
      for(const key of ['ema20','ema50','ema200'] as const){
        emaRefs.current[key]?.setData(rows.map(r=>({time:r.time,value:Number((r as any)[key]||r.close)})).filter(x=>Number.isFinite(x.value)&&x.value>0) as any);
      }
    }catch(e:any){console.error('[GodMode chart data]', e); setChartError(e?.message||'Chart rendering failed');}
  },[rows]);

  // ---- price lines: recreated only when the levels themselves change ----
  const levelKey=useMemo(()=>levels.map(l=>`${l.label}:${l.price}:${l.color||''}`).join('|'),[levels]);
  useEffect(()=>{
    const candle=candleRef.current;
    if(!candle) return;
    try{
      priceLinesRef.current.forEach(line=>{try{candle.removePriceLine(line)}catch{ /* already gone */ }});
      priceLinesRef.current=levels
        .filter(l=>Number.isFinite(l.price)&&l.price>0)
        .map(l=>candle.createPriceLine({price:l.price,color:l.color||cssVar('--gold')||'#c9972f',lineWidth:1,lineStyle:(l.style||2) as any,axisLabelVisible:true,title:l.label}));
    }catch{ /* price lines are decoration; never let them break the chart */ }
  },[levelKey]);
  if(!rows.length) return <div className="chart-shell empty-chart-shell"><EmptyChart message="No live XAUUSD candles received"/><CandlestickPreview height={180}/></div>;
  if(chartError) return <div className="chart-shell fallback-chart"><div className="chart-watermark">XAUUSD</div><CandlestickPreview height={260}/><p className="muted tiny">Live chart fallback active: {chartError}</p></div>;
  return <div className="chart-shell"><div className="chart-watermark">XAUUSD</div><div className="chart-overlay-panel"><Tag color="gold">EMA 20 / 50 / 200</Tag><Tag color="green">Entry</Tag><Tag color="red">SL</Tag><Tag color="blue">TP zones</Tag></div><div ref={ref} className="chart-tvlw"/></div>
}
export const MarketChart=LiveTradeViewChart;

export function EquityCurve({height=220,data=[]}:{height?:number;data?:any[]}){if(!data.length)return <EmptyChart message="No bot-only equity history yet"/>;return <ResponsiveContainer width="100%" height={height}><AreaChart data={data}><defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--purple)" stopOpacity={.55}/><stop offset="100%" stopColor="var(--purple)" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="var(--border-soft)" vertical={false}/><XAxis dataKey="date" tick={{fill:'var(--text-muted)',fontSize:11}} axisLine={false} tickLine={false}/><YAxis tick={{fill:'var(--text-muted)',fontSize:11}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'var(--surface)',border:'1px solid var(--border)',color:'var(--text)'}}/><Area type="monotone" dataKey="equity" stroke="var(--purple)" fill="url(#eq)" strokeWidth={3}/><Line type="monotone" dataKey="benchmark" stroke="var(--text-faint)" strokeDasharray="4 4" dot={false}/></AreaChart></ResponsiveContainer>}
export function ReturnsHeatmap({data=[]}:{data?:any[]}){const days=['Mon','Tue','Wed','Thu','Fri']; if(!data.length) return <p className="muted tiny">No returns yet.</p>; return <div style={{display:'grid',gap:7,minWidth:0}}>{data.map(row=><div key={row.week} style={{display:'grid',gridTemplateColumns:'minmax(40px,64px) repeat(5,minmax(0,1fr))',gap:6,alignItems:'center',minWidth:0}}><span className="tiny muted" style={{minWidth:0,overflow:'hidden',textOverflow:'ellipsis'}}>{row.week}</span>{days.map(d=>{const v=(row as any)[d]||0;return <span key={d} style={{borderRadius:8,padding:'8px 4px',textAlign:'center',fontWeight:800,fontSize:11.5,minWidth:0,overflow:'hidden',color:v<0?'var(--red)':'var(--green)',background:v<0?'var(--red-soft)':'var(--green-soft)'}}>{v?`${v}%`:'—'}</span>})}</div>)}</div>}
// Aesthetic per-day RETURNS CALENDAR (Mon–Fri columns, weeks as rows). Click any day to see what the
// AI detected that day and the best optimisation for the next day. Falls back to a message if empty.
const DOW=['Mon','Tue','Wed','Thu','Fri'] as const;
export function ReturnsCalendar({data=[],currency=''}:{data?:any[];currency?:string}){
  const days=Array.isArray(data)?data:[];
  const withTrades=days.filter(d=>d&&d.trades>0);
  const [sel,setSel]=useState<string>('');
  useEffect(()=>{if(!sel&&withTrades.length)setSel(withTrades[withTrades.length-1].date)},[data]);// eslint-disable-line
  if(!days.length) return <p className="muted tiny">No returns yet — your day-by-day calendar fills in as the bot closes trades.</p>;
  // group into ordered weeks
  const weeks:string[]=[]; const grid:Record<string,Record<string,any>>={};
  days.forEach(d=>{if(!weeks.includes(d.week))weeks.push(d.week); (grid[d.week]||(grid[d.week]={}))[d.dow]=d;});
  const selected=days.find(d=>d.date===sel)|| withTrades[withTrades.length-1] || null;
  const maxAbs=Math.max(1,...days.map(d=>Math.abs(Number(d.pnl||0))));
  const cell=(d:any)=>{
    if(!d) return <div className="rc-cell rc-empty" key={Math.random()}/>;
    const v=Number(d.pnl||0); const has=d.trades>0; const mag=Math.min(1,Math.abs(v)/maxAbs);
    const bg=!has?'transparent':v>0?`color-mix(in srgb, var(--green) ${14+mag*46}%, transparent)`:v<0?`color-mix(in srgb, var(--red) ${14+mag*46}%, transparent)`:'var(--surface-muted)';
    const dn=String(d.date||'').slice(8,10);
    return <button key={d.date} className={`rc-cell${has?' rc-has':''}${sel===d.date?' rc-sel':''}`} style={{background:bg}} onClick={()=>setSel(d.date)} title={`${d.date} · ${d.trades} trade(s)`}>
      <span className="rc-dn">{dn}</span>
      <strong className={v>0?'positive':v<0?'negative':'muted'} style={{fontSize:13}}>{has?`${v>0?'+':''}${v}`:'·'}</strong>
      {has&&<span className="rc-tn">{d.wins}W·{d.losses}L</span>}
    </button>;
  };
  const fmtDate=(s:string)=>{try{return new Date(s+'T00:00:00').toLocaleDateString(undefined,{weekday:'long',month:'short',day:'numeric'})}catch{return s}};
  return <div className="returns-cal">
    <div className="rc-grid rc-head"><span className="rc-corner"/>{DOW.map(d=><span key={d} className="rc-dow">{d}</span>)}</div>
    {weeks.map(w=><div className="rc-grid" key={w}><span className="rc-wk">{w}</span>{DOW.map(d=>cell(grid[w][d]))}</div>)}
    {selected&&<div className="returns-detail">
      <div className="rc-detail-head">
        <div><strong>{fmtDate(selected.date)}</strong><div className="tiny muted">{selected.trades} trade(s) · {selected.wins}W / {selected.losses}L</div></div>
        <h3 className={Number(selected.pnl)>=0?'positive':'negative'} style={{margin:0}}>{Number(selected.pnl)>=0?'+':''}{currency?currency+' ':''}{selected.pnl}</h3>
      </div>
      <div className="rc-insight"><span className="rc-ilabel">🔍 What the AI detected</span><p>{selected.detected||'—'}</p></div>
      <div className="rc-insight"><span className="rc-ilabel gold">⚡ Best optimisation for the next day</span><p>{selected.optimization||'—'}</p></div>
    </div>}
  </div>;
}
export function Donut({value=0}:{value?:number}){return <ResponsiveContainer width="100%" height={150}><PieChart><Pie data={[{name:'value',value},{name:'rest',value:100-value}]} innerRadius={48} outerRadius={64} startAngle={90} endAngle={-270} dataKey="value"><Cell fill="var(--green)"/><Cell fill="var(--surface-muted)"/></Pie></PieChart></ResponsiveContainer>}
export function DrawdownChart({data=[]}:{data?:any[]}){if(!data.length)return <EmptyChart message="No drawdown data yet"/>;return <ResponsiveContainer width="100%" height={180}><AreaChart data={data}><CartesianGrid stroke="var(--border-soft)" vertical={false}/><XAxis dataKey="date" tick={{fill:'var(--text-muted)',fontSize:10}}/><YAxis tick={{fill:'var(--text-muted)',fontSize:10}}/><Area dataKey="value" stroke="var(--red)" fill="var(--red-soft)"/></AreaChart></ResponsiveContainer>}
export function BarDistribution({data=[]}:{data?:any[]}){if(!data.length)return <p className="muted tiny">No distribution yet.</p>;return <ResponsiveContainer width="100%" height={150}><BarChart data={data}><XAxis dataKey="x" tick={{fill:'var(--text-muted)',fontSize:10}}/><YAxis tick={{fill:'var(--text-muted)',fontSize:10}}/><Bar dataKey="v" fill="var(--green)" radius={[8,8,0,0]}/></BarChart></ResponsiveContainer>}
export function ScatterPerformance({data=[]}:{data?:any[]}){if(!data.length)return <EmptyChart message="No confidence/result sample yet"/>;return <ResponsiveContainer width="100%" height={180}><ScatterChart><CartesianGrid stroke="var(--border-soft)"/><XAxis dataKey="confidence" tick={{fill:'var(--text-muted)',fontSize:10}}/><YAxis dataKey="result" tick={{fill:'var(--text-muted)',fontSize:10}}/><Tooltip contentStyle={{background:'var(--surface)',border:'1px solid var(--border)'}}/><Scatter data={data} fill="var(--green)"/></ScatterChart></ResponsiveContainer>}
export function MiniCandleBlock({data,height=86,side}:{data?:any[];height?:number;side?:string}){
  const rows=(data||[]).filter(c=>Number.isFinite(Number(c.high))&&Number.isFinite(Number(c.low)));
  if(!rows.length) return <div className="journal-thumb" style={{height}}><CandlestickPreview height={height}/></div>;
  const highs=rows.map(c=>Number(c.high)),lows=rows.map(c=>Number(c.low));
  const max=Math.max(...highs),min=Math.min(...lows),range=Math.max(0.0001,max-min);
  const w=100/rows.length;const up=side==='SELL'?'var(--red)':'var(--green)';
  return <div className="journal-thumb" style={{height}}>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" width="100%" height="100%">
      {rows.map((c,i)=>{const o=Number(c.open),cl=Number(c.close),hi=Number(c.high),lo=Number(c.low);
        const y=(v:number)=>100-((v-min)/range)*92-4;const x=i*w+w/2;const green=cl>=o;
        const col=green?'var(--green)':'var(--red)';
        const bodyTop=y(Math.max(o,cl)),bodyBot=y(Math.min(o,cl));
        return <g key={i}><line x1={x} x2={x} y1={y(hi)} y2={y(lo)} stroke={col} strokeWidth={0.6}/><rect x={i*w+w*0.18} width={w*0.64} y={bodyTop} height={Math.max(1,bodyBot-bodyTop)} fill={col}/></g>;})}
    </svg>
  </div>;
}
