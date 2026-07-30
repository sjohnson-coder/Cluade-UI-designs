import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, ColorType, CrosshairMode, LineStyle, IChartApi, ISeriesApi, IPriceLine, UTCTimestamp } from 'lightweight-charts';

interface Candle { time:number; open:number; high:number; low:number; close:number; volume?:number; tick_volume?:number }
interface Marker { time:number; side:string; text?:string }
interface Levels { entry?:number; sl?:number; tp1?:number; tp2?:number; tp3?:number }
interface LiveTrade { direction?:string; side?:string; entryPrice?:number; lots?:number; volume?:number; pnlUsd?:number; ticket?:any }
interface Props {
  candles?: Candle[];
  markers?: Marker[];
  levels?: Levels;
  liveTrade?: LiveTrade | null;
  height?: number;
  symbol?: string;
}

const TFS = ['M1','M5','M15','M30','H1','H4','D1'] as const;
type TF = typeof TFS[number];

function isDarkTheme(){ return document.documentElement.getAttribute('data-theme') !== 'light'; }

/**
 * LiveChart V13.1 — TradingView-grade rebuild.
 *
 * What changed vs the old chart, and why:
 *  • REALTIME TICK: the old chart called setData() on every poll (full series rewrite). Now the
 *    forming bar is pushed through series.update(), which is how a real tape ticks — the last
 *    candle and everything anchored to price moves live. setData only runs on TF switch or gaps.
 *  • NO FLICKER: entry/SL/TP price lines used to be destroyed and re-created every poll. They are
 *    now persistent IPriceLine handles updated via applyOptions() — they GLIDE, never blink.
 *  • MARKERS = LIVE TRADE ONLY: no more historical WIN/LOSS confetti or bias arrows. One entry
 *    marker + price lines exist exactly while a trade is open, and vanish on close.
 *  • LIVE P&L BADGE: a floating badge rides the current price line (series.priceToCoordinate on
 *    every tick + pane resize), showing the open trade's live P&L — green in profit, red in
 *    drawdown. This is the "marker that moves in realtime with price".
 *  • TF SWITCHER: M1..D1 fetched from /api/market/candles (per-TF cached backend) without
 *    touching the global trading timeframe.
 *  • Volume histogram, watermark, OHLC legend on crosshair — the standard TradingView furniture.
 */
export function LiveChart({ candles=[], markers=[], levels={}, liveTrade=null, height=480, symbol='XAUUSD' }: Props){
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi|null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'>|null>(null);
  const volRef = useRef<ISeriesApi<'Histogram'>|null>(null);
  const lineRefs = useRef<Record<string, IPriceLine|null>>({});
  const lastBarTimeRef = useRef<number>(0);
  const badgeRef = useRef<HTMLDivElement|null>(null);
  const lastPriceRef = useRef<number>(0);
  const liveTradeRef = useRef<LiveTrade|null>(null);
  liveTradeRef.current = liveTrade;
  const [tf, setTf] = useState<TF>('M15');
  const [tfCandles, setTfCandles] = useState<Candle[]|null>(null);   // null = use prop candles (settings TF)
  const [legend, setLegend] = useState<string>('');

  const data = tfCandles ?? candles;

  // ---- chart creation: ONCE ----
  useEffect(()=>{
    if(!containerRef.current) return;
    const dark = isDarkTheme();
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { type: ColorType.Solid, color: dark ? '#0a0e14' : '#f7f5f0' },
                textColor: dark ? '#a7b0be' : '#5b6472', fontFamily: 'Inter, system-ui, sans-serif' },
      grid: { vertLines: { color: dark ? 'rgba(148,163,184,.06)' : 'rgba(31,41,55,.05)' },
              horzLines: { color: dark ? 'rgba(148,163,184,.06)' : 'rgba(31,41,55,.05)' } },
      crosshair: { mode: CrosshairMode.Normal,
        vertLine: { labelBackgroundColor: '#C9A961' }, horzLine: { labelBackgroundColor: '#C9A961' } },
      rightPriceScale: { borderColor: dark ? 'rgba(148,163,184,.14)' : 'rgba(31,41,55,.10)', scaleMargins: { top: 0.08, bottom: 0.22 } },
      timeScale: { borderColor: dark ? 'rgba(148,163,184,.14)' : 'rgba(31,41,55,.10)', timeVisible: true, secondsVisible: false, rightOffset: 6 },
      autoSize: true,
    });
    const series = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    const vol = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });

    chartRef.current = chart; seriesRef.current = series; volRef.current = vol;

    // OHLC legend follows the crosshair — the TradingView reading experience
    chart.subscribeCrosshairMove((p)=>{
      const d:any = p?.seriesData?.get(series);
      if(d && d.open!=null) setLegend(`O ${d.open.toFixed(2)}  H ${d.high.toFixed(2)}  L ${d.low.toFixed(2)}  C ${d.close.toFixed(2)}`);
      else setLegend('');
    });

    const reposition = ()=>positionBadge();
    chart.timeScale().subscribeVisibleLogicalRangeChange(reposition);

    const ro = new ResizeObserver(()=>{ if(containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth }); reposition(); });
    ro.observe(containerRef.current);
    const mo = new MutationObserver(()=>{
      const d = isDarkTheme();
      chart.applyOptions({ layout: { background: { type: ColorType.Solid, color: d ? '#0a0e14' : '#f7f5f0' }, textColor: d ? '#a7b0be' : '#5b6472' } });
    });
    mo.observe(document.documentElement, { attributes:true, attributeFilter:['data-theme'] });

    return ()=>{ ro.disconnect(); mo.disconnect(); chart.remove(); chartRef.current=null; seriesRef.current=null; volRef.current=null; lineRefs.current={}; lastBarTimeRef.current=0; };
  }, [height]);

  // ---- TF switcher: fetch its own candles; settings-TF uses the live prop stream ----
  useEffect(()=>{
    let dead=false;
    if(tf==='M15'){ setTfCandles(null); return; }        // default TF rides the dashboard's live stream
    const load=async()=>{
      try{
        const r=await fetch(`/api/market/candles?tf=${tf}&count=500`);
        const j=await r.json();
        if(!dead && Array.isArray(j.candles)) setTfCandles(j.candles);
      }catch{/* keep whatever we have */}
    };
    load();
    const iv=setInterval(()=>{if(!document.hidden) void load()}, tf==='M1'?5000: tf==='M5'?8000: 30000);
    return ()=>{ dead=true; clearInterval(iv); };
  }, [tf]);

  // ---- candles: realtime tick path ----
  useEffect(()=>{
    const series=seriesRef.current, vol=volRef.current;
    if(!series || !data?.length) return;
    const seen=new Set<number>();
    const clean=data.filter(c=>c&&c.time&&c.close&&!seen.has(c.time)&&(seen.add(c.time),true))
                    .sort((a,b)=>a.time-b.time);
    if(!clean.length) return;
    const last=clean[clean.length-1];
    lastPriceRef.current=last.close;

    const prevLast=lastBarTimeRef.current;
    const sameSeries = prevLast>0 && (last.time===prevLast || clean.some(c=>c.time===prevLast));
    if(sameSeries && last.time>=prevLast){
      // realtime: only push bars at/after the previous head — the tape ticks, no rewrite
      try{
        for(const c of clean.filter(c=>c.time>=prevLast)){
          series.update({ time:c.time as UTCTimestamp, open:c.open, high:c.high, low:c.low, close:c.close });
          vol?.update({ time:c.time as UTCTimestamp, value:Number(c.volume??c.tick_volume??0), color: c.close>=c.open?'rgba(34,197,94,.35)':'rgba(239,68,68,.35)' });
        }
      }catch{ /* discontinuity -> full reload below */ lastBarTimeRef.current=0; }
    }
    if(!sameSeries || lastBarTimeRef.current===0){
      try{
        series.setData(clean.map(c=>({ time:c.time as UTCTimestamp, open:c.open, high:c.high, low:c.low, close:c.close })));
        vol?.setData(clean.map(c=>({ time:c.time as UTCTimestamp, value:Number(c.volume??c.tick_volume??0), color: c.close>=c.open?'rgba(34,197,94,.35)':'rgba(239,68,68,.35)' })));
        chartRef.current?.timeScale().fitContent();
      }catch{}
    }
    lastBarTimeRef.current=last.time;
    positionBadge();
  }, [data]);

  // ---- price lines: persistent, applyOptions in place (glide, never blink) ----
  useEffect(()=>{
    const series=seriesRef.current; if(!series) return;
    const live=Boolean(liveTrade?.ticket);
    const want:{k:string;price?:number;color:string;title:string;style:LineStyle}[] = live?[
      {k:'entry', price:levels.entry, color:'#3b82f6', title:'ENTRY', style:LineStyle.Solid},
      {k:'sl',    price:levels.sl,    color:'#ef4444', title:'SL',    style:LineStyle.Dashed},
      {k:'tp1',   price:levels.tp1,   color:'#22c55e', title:'TP1',   style:LineStyle.Dashed},
      {k:'tp2',   price:levels.tp2,   color:'#16a34a', title:'TP2',   style:LineStyle.Dashed},
      {k:'tp3',   price:levels.tp3,   color:'#15803d', title:'TP3',   style:LineStyle.Dashed},
    ]:[];
    const wanted=new Set(want.filter(w=>w.price&&w.price>0).map(w=>w.k));
    // remove lines that should no longer exist (e.g. trade closed)
    for(const k of Object.keys(lineRefs.current)){
      if(!wanted.has(k)&&lineRefs.current[k]){ try{ series.removePriceLine(lineRefs.current[k]!); }catch{} lineRefs.current[k]=null; }
    }
    // create-or-move the rest
    for(const w of want){
      if(!w.price||w.price<=0) continue;
      const ex=lineRefs.current[w.k];
      if(ex){ try{ ex.applyOptions({ price:w.price }); }catch{} }
      else { try{ lineRefs.current[w.k]=series.createPriceLine({ price:w.price, color:w.color, lineWidth:1, lineStyle:w.style, axisLabelVisible:true, title:w.title }); }catch{} }
    }
  }, [levels.entry, levels.sl, levels.tp1, levels.tp2, levels.tp3, liveTrade?.ticket]);

  // ---- entry marker: exists ONLY while a trade is live ----
  useEffect(()=>{
    const series=seriesRef.current; if(!series) return;
    const live=Boolean(liveTrade?.ticket);
    const m=(live?markers:[]).filter(x=>x&&x.time).map(x=>({
      time:x.time as UTCTimestamp,
      position:(String(x.side).toUpperCase()==='SELL'?'aboveBar':'belowBar') as any,
      color:String(x.side).toUpperCase()==='SELL'?'#ef4444':'#22c55e',
      shape:(String(x.side).toUpperCase()==='SELL'?'arrowDown':'arrowUp') as any,
      text:x.text||String(x.side).toUpperCase(),
    }));
    try{ series.setMarkers(m); }catch{}
  }, [markers, liveTrade?.ticket]);

  // ---- the moving part: live P&L badge riding the price ----
  const positionBadge=useCallback(()=>{
    const series=seriesRef.current, el=badgeRef.current;
    if(!series||!el) return;
    const lt=liveTradeRef.current;
    const live=Boolean(lt?.ticket)&&lastPriceRef.current>0;
    if(!live){ el.style.display='none'; return; }
    const y=series.priceToCoordinate(lastPriceRef.current);
    if(y==null){ el.style.display='none'; return; }
    const pnl=Number(lt?.pnlUsd??0);
    el.style.display='block';
    el.style.top=`${Math.max(4, y-12)}px`;
    el.textContent=`${(lt?.direction||lt?.side||'').toUpperCase()} ${lt?.lots||lt?.volume||''}  ${pnl>=0?'+':''}${pnl.toFixed(2)} USD`;
    el.style.background=pnl>=0?'rgba(34,197,94,.92)':'rgba(239,68,68,.92)';
  }, []);
  useEffect(()=>{ positionBadge(); }, [positionBadge, data, liveTrade?.pnlUsd, liveTrade?.ticket]);

  return (
    <div style={{ position:'relative', width:'100%', height, borderRadius:12, overflow:'hidden', border:'1px solid var(--border)' }}>
      {/* header rail: symbol + TF switcher + crosshair legend */}
      <div style={{ position:'absolute', left:12, top:8, zIndex:3, display:'flex', alignItems:'center', gap:10, pointerEvents:'none' }}>
        <span style={{ fontFamily:'Archivo,sans-serif', fontSize:13.5, fontWeight:800, color:'var(--gold)', opacity:.75 }}>{symbol}</span>
        <div style={{ display:'flex', gap:2, pointerEvents:'auto' }}>
          {TFS.map(t=>(
            <button key={t} onClick={()=>setTf(t)} style={{
              padding:'2px 7px', fontSize:11, fontWeight:600, borderRadius:5, cursor:'pointer',
              border:'1px solid '+(t===tf?'rgba(201,169,97,.55)':'transparent'),
              background:t===tf?'rgba(201,169,97,.16)':'transparent',
              color:t===tf?'var(--gold)':'var(--text-muted)',
            }}>{t}</button>
          ))}
        </div>
        {legend&&<span style={{ fontSize:11, fontVariantNumeric:'tabular-nums', color:'var(--text-muted)' }}>{legend}</span>}
      </div>
      {/* live P&L badge — rides the price, exists only while a trade is open */}
      <div ref={badgeRef} style={{ position:'absolute', right:76, zIndex:4, display:'none', padding:'3px 8px',
        borderRadius:6, fontSize:11.5, fontWeight:700, color:'#0a0e14', fontVariantNumeric:'tabular-nums',
        boxShadow:'0 2px 10px rgba(0,0,0,.35)', pointerEvents:'none', transition:'top 120ms linear' }} />
      <div ref={containerRef} style={{ width:'100%', height:'100%' }}/>
      {(!data||data.length===0)&&(
        <div style={{ position:'absolute', inset:0, display:'grid', placeItems:'center', color:'var(--text-muted)', pointerEvents:'none' }}>
          <div style={{ textAlign:'center' }}>
            <div style={{ fontWeight:600, fontSize:13 }}>Waiting for live candle data…</div>
            <div style={{ fontSize:11, marginTop:4 }}>Connect MT5 to stream {symbol} candles.</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LiveChart;
