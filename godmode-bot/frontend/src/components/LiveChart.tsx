import { useEffect, useRef } from 'react';
import { createChart, ColorType, CrosshairMode, LineStyle, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';

interface Candle { time:number; open:number; high:number; low:number; close:number }
interface Marker { time:number; side:string; text?:string }
interface Levels { entry?:number; sl?:number; tp1?:number; tp2?:number; tp3?:number }
interface Props {
  candles?: Candle[];
  markers?: Marker[];
  levels?: Levels;
  height?: number;
  symbol?: string;
}

function isDarkTheme(){ return document.documentElement.getAttribute('data-theme') !== 'light'; }

/**
 * Self-rendered candlestick chart fed by live MT5 candles. Replaces the external
 * TradingView iframe (which intermittently went white) and adds live entry/SL/TP
 * markers + price lines the embedded widget could never show.
 *
 * The chart instance is created ONCE and only updated via .setData / .setMarkers —
 * it never remounts on data polls, so there is no flicker or blank frame.
 */
export function LiveChart({ candles=[], markers=[], levels={}, height=480, symbol='XAUUSD' }: Props){
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi|null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'>|null>(null);
  const priceLinesRef = useRef<any[]>([]);

  // Create the chart once
  useEffect(()=>{
    if(!containerRef.current) return;
    const dark = isDarkTheme();
    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: dark ? '#0a0e14' : '#f7f5f0' },
        textColor: dark ? '#a7b0be' : '#5b6472',
        fontFamily: 'Inter, system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: dark ? 'rgba(148,163,184,.07)' : 'rgba(31,41,55,.06)' },
        horzLines: { color: dark ? 'rgba(148,163,184,.07)' : 'rgba(31,41,55,.06)' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: dark ? 'rgba(148,163,184,.14)' : 'rgba(31,41,55,.10)' },
      timeScale: { borderColor: dark ? 'rgba(148,163,184,.14)' : 'rgba(31,41,55,.10)', timeVisible: true, secondsVisible: false },
      autoSize: true,
    });
    const series = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });
    chartRef.current = chart;
    seriesRef.current = series;

    // Resize observer keeps the chart filling its container without remount
    const ro = new ResizeObserver(()=>{ if(containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth }); });
    ro.observe(containerRef.current);

    // React to theme changes without rebuilding the chart
    const mo = new MutationObserver(()=>{
      const d = isDarkTheme();
      chart.applyOptions({
        layout: { background: { type: ColorType.Solid, color: d ? '#0a0e14' : '#f7f5f0' }, textColor: d ? '#a7b0be' : '#5b6472' },
        grid: { vertLines: { color: d ? 'rgba(148,163,184,.07)' : 'rgba(31,41,55,.06)' }, horzLines: { color: d ? 'rgba(148,163,184,.07)' : 'rgba(31,41,55,.06)' } },
      });
    });
    mo.observe(document.documentElement, { attributes:true, attributeFilter:['data-theme'] });

    return ()=>{ ro.disconnect(); mo.disconnect(); chart.remove(); chartRef.current=null; seriesRef.current=null; };
  }, [height]);

  // Update candle data on every poll (no remount)
  useEffect(()=>{
    if(!seriesRef.current || !candles?.length) return;
    const data = candles
      .filter(c=>c && c.time && c.close)
      .map(c=>({ time: c.time as UTCTimestamp, open:c.open, high:c.high, low:c.low, close:c.close }));
    // de-dup + sort ascending (lightweight-charts requires strictly increasing time)
    const seen = new Set<number>();
    const clean = data.filter(d=>{ if(seen.has(d.time as number)) return false; seen.add(d.time as number); return true; })
                      .sort((a,b)=>(a.time as number)-(b.time as number));
    try { seriesRef.current.setData(clean); } catch {}
  }, [candles]);

  // Update entry markers
  useEffect(()=>{
    if(!seriesRef.current) return;
    const m = (markers||[]).filter(x=>x && x.time).map(x=>({
      time: x.time as UTCTimestamp,
      position: (String(x.side).toUpperCase()==='SELL'?'aboveBar':'belowBar') as any,
      color: String(x.side).toUpperCase()==='SELL'?'#ef4444':'#22c55e',
      shape: (String(x.side).toUpperCase()==='SELL'?'arrowDown':'arrowUp') as any,
      text: x.text || String(x.side).toUpperCase(),
    }));
    try { seriesRef.current.setMarkers(m); } catch {}
  }, [markers]);

  // Update entry / SL / TP price lines
  useEffect(()=>{
    const series = seriesRef.current;
    if(!series) return;
    // Clear old lines
    priceLinesRef.current.forEach(l=>{ try{ series.removePriceLine(l); }catch{} });
    priceLinesRef.current = [];
    const add = (price:number|undefined, color:string, title:string, style:LineStyle=LineStyle.Dashed)=>{
      if(!price || price<=0) return;
      try {
        priceLinesRef.current.push(series.createPriceLine({ price, color, lineWidth:1, lineStyle:style, axisLabelVisible:true, title }));
      } catch {}
    };
    add(levels.entry, '#3b82f6', 'ENTRY', LineStyle.Solid);
    add(levels.sl, '#ef4444', 'SL');
    add(levels.tp1, '#22c55e', 'TP1');
    add(levels.tp2, '#16a34a', 'TP2');
    add(levels.tp3, '#15803d', 'TP3');
  }, [levels.entry, levels.sl, levels.tp1, levels.tp2, levels.tp3]);

  return (
    <div style={{ position:'relative', width:'100%', height, borderRadius:12, overflow:'hidden', border:'1px solid var(--border)' }}>
      <div style={{ position:'absolute', left:14, top:10, zIndex:3, fontFamily:'Archivo,sans-serif', fontSize:14, fontWeight:800, color:'var(--gold)', opacity:.5, pointerEvents:'none' }}>{symbol} · 15m</div>
      <div ref={containerRef} style={{ width:'100%', height:'100%' }}/>
      {(!candles || candles.length===0) && (
        <div style={{ position:'absolute', inset:0, display:'grid', placeItems:'center', color:'var(--text-muted)', pointerEvents:'none' }}>
          <div style={{ textAlign:'center' }}>
            <div style={{ fontSize:28, marginBottom:6 }}>📈</div>
            <div style={{ fontWeight:600, fontSize:13 }}>Waiting for live candle data…</div>
            <div style={{ fontSize:11, marginTop:4 }}>Connect MT5 to stream {symbol} candles.</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LiveChart;
