import { useEffect, useRef, useState } from 'react';

interface TvSignal {
  side?: string;
  entry?: number;
  sl?: number;
  tp1?: number;
  tp2?: number;
  tp3?: number;
  confidence?: number;
  strategy?: string;
  session?: string;
  regime?: string;
}

interface Props {
  symbol?: string;
  interval?: string;
  signal?: TvSignal;
  height?: number;
  showSignalPanel?: boolean;
}

declare global {
  interface Window { TradingView?: any; _tvScriptLoaded?: boolean }
}

// Load the TradingView widget script once globally
function loadTVScript(): Promise<void> {
  return new Promise((resolve) => {
    if (window.TradingView || window._tvScriptLoaded) { resolve(); return; }
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/tv.js';
    s.async = true;
    s.onload = () => { window._tvScriptLoaded = true; resolve(); };
    s.onerror = () => resolve(); // fail silently, show fallback
    document.head.appendChild(s);
  });
}

function SignalOverlay({ signal, price }: { signal: TvSignal; price?: number }) {
  if (!signal || !signal.entry) return null;
  const side = (signal.side || 'BUY').toUpperCase();
  const isBuy = side === 'BUY';
  const priceFmt = (v?: number) => v ? v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
  const conf = signal.confidence || 0;
  const confColor = conf >= 80 ? 'var(--green)' : conf >= 65 ? 'var(--amber)' : 'var(--red)';
  return (
    <div style={{ display:'grid', gap:10 }}>
      <div style={{ textAlign:'center', padding:'12px 0 4px' }}>
        <div style={{ fontSize:28, fontWeight:900, fontFamily:'Archivo,sans-serif',
          color: isBuy ? 'var(--green)' : 'var(--red)', letterSpacing:'-0.02em' }}>
          {side} ↗
        </div>
        {signal.strategy && <div style={{ fontSize:11, color:'var(--text-muted)', fontWeight:700, marginTop:2 }}>{signal.strategy}</div>}
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
        {[
          { l:'Entry', v: priceFmt(signal.entry), c:'var(--gold-dark)' },
          { l:'Stop Loss', v: priceFmt(signal.sl), c:'var(--red)' },
          { l:'TP 1', v: priceFmt(signal.tp1), c:'var(--green)' },
          { l:'TP 2', v: priceFmt(signal.tp2), c:'var(--green)' },
        ].map(({l,v,c})=>(
          <div key={l} style={{ background:'var(--surface-soft)', borderRadius:10, padding:'8px 10px', border:'1px solid var(--border)' }}>
            <div style={{ fontSize:10, color:'var(--text-muted)', fontWeight:800, textTransform:'uppercase', letterSpacing:'.06em' }}>{l}</div>
            <div style={{ fontSize:14, fontWeight:800, color:c, fontFamily:'Geist Mono,ui-monospace,monospace', marginTop:3 }}>{v}</div>
          </div>
        ))}
      </div>
      <div style={{ background:'var(--surface-soft)', borderRadius:10, padding:'10px 12px', border:'1px solid var(--border)' }}>
        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
          <span style={{ fontSize:11, color:'var(--text-muted)', fontWeight:800 }}>AI Confidence</span>
          <span style={{ fontSize:12, fontWeight:900, color: confColor }}>{conf}%</span>
        </div>
        <div style={{ height:6, borderRadius:3, background:'var(--surface-muted)', overflow:'hidden' }}>
          <div style={{ height:'100%', width:`${conf}%`, background: confColor, borderRadius:3, transition:'width .4s ease' }}/>
        </div>
      </div>
      {signal.session && (
        <div style={{ fontSize:11, color:'var(--text-muted)', display:'flex', gap:8, flexWrap:'wrap' }}>
          <span>📍 {signal.session}</span>
          {signal.regime && <span>🧭 {signal.regime}</span>}
          {signal.tp2 && signal.entry && signal.sl && (
            <span>⚖️ R/R {Math.abs((signal.tp2 - signal.entry) / Math.abs(signal.entry - signal.sl)).toFixed(1)}</span>
          )}
        </div>
      )}
    </div>
  );
}

export function TradingViewChart({ symbol='OANDA:XAUUSD', interval='15', signal, height=500, showSignalPanel=true }: Props) {
  const containerId = useRef(`tv_${Math.random().toString(36).slice(2)}`);
  const widgetRef   = useRef<any>(null);
  const [loaded, setLoaded]   = useState(false);
  const [error, setError]     = useState(false);
  const [isDark, setIsDark]   = useState(document.documentElement.getAttribute('data-theme') !== 'light');
  const [tf, setTf]           = useState(interval);
  const [sym, setSym]         = useState(symbol);

  // Track theme changes
  useEffect(() => {
    const obs = new MutationObserver(() => {
      setIsDark(document.documentElement.getAttribute('data-theme') !== 'light');
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);

  // Build the widget
  useEffect(() => {
    let cancelled = false;
    loadTVScript().then(() => {
      if (cancelled || !window.TradingView) { setError(true); return; }
      // Cleanup previous widget
      const el = document.getElementById(containerId.current);
      if (!el) { setError(true); return; }
      el.innerHTML = '';
      try {
        widgetRef.current = new window.TradingView.widget({
          autosize:           true,
          symbol:             sym,
          interval:           tf,
          timezone:           'Etc/UTC',
          theme:              isDark ? 'dark' : 'light',
          style:              '1',            // Candlestick
          locale:             'en',
          toolbar_bg:         isDark ? '#0a0e14' : '#f7f5f0',
          enable_publishing:  false,
          withdateranges:     true,
          hide_legend:        false,
          hide_top_toolbar:   false,
          hide_side_toolbar:  false,
          allow_symbol_change:true,
          save_image:         true,
          details:            true,
          hotlist:            false,
          calendar:           false,
          studies: [
            'RSI@tv-basicstudies',
            'MACD@tv-basicstudies',
            'MASimple@tv-basicstudies',
          ],
          studies_overrides: {
            'moving average.length': 20,
          },
          overrides: {
            'mainSeriesProperties.candleStyle.upColor':        '#22c55e',
            'mainSeriesProperties.candleStyle.downColor':      '#ef4444',
            'mainSeriesProperties.candleStyle.borderUpColor':  '#22c55e',
            'mainSeriesProperties.candleStyle.borderDownColor':'#ef4444',
            'mainSeriesProperties.candleStyle.wickUpColor':    '#22c55e',
            'mainSeriesProperties.candleStyle.wickDownColor':  '#ef4444',
            'paneProperties.background':                       isDark ? '#0a0e14' : '#f7f5f0',
            'paneProperties.gridProperties.color':             isDark ? 'rgba(148,163,184,.07)' : 'rgba(31,41,55,.06)',
            'scalesProperties.textColor':                      isDark ? '#a7b0be' : '#5b6472',
          },
          container_id: containerId.current,
          loading_screen: { backgroundColor: isDark ? '#0a0e14' : '#f7f5f0', foregroundColor: '#d8a33a' },
        });
        setLoaded(true);
      } catch(e) {
        console.error('[GodMode TV]', e);
        setError(true);
      }
    });
    return () => { cancelled = true; };
  }, [sym, tf, isDark]);

  const timeframes = [
    { label:'1m',  tv:'1' }, { label:'5m',  tv:'5' }, { label:'15m', tv:'15' },
    { label:'1H',  tv:'60'}, { label:'4H',  tv:'240'},{ label:'1D',  tv:'D' },
  ];

  return (
    <div style={{ display:'grid', gridTemplateColumns: showSignalPanel && signal?.entry ? '1fr 220px' : '1fr', gap:12, height }}>
      {/* Chart panel */}
      <div style={{ display:'flex', flexDirection:'column', gap:8, minWidth:0 }}>
        {/* Timeframe + symbol bar */}
        <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
          <div style={{ display:'flex', gap:4 }}>
            {timeframes.map(t => (
              <button key={t.tv} onClick={() => setTf(t.tv)} style={{
                height:28, padding:'0 9px', border:'1px solid var(--border)',
                borderRadius:8, background: tf===t.tv ? 'var(--gold-soft)' : 'var(--surface)',
                color: tf===t.tv ? 'var(--gold-dark)' : 'var(--text-muted)',
                fontWeight:800, fontSize:11, cursor:'pointer',
                borderColor: tf===t.tv ? 'var(--gold-border)' : undefined,
              }}>{t.label}</button>
            ))}
          </div>
          <div style={{ marginLeft:'auto', display:'flex', gap:6, alignItems:'center' }}>
            <span style={{ fontSize:11, color:'var(--text-muted)', fontWeight:700 }}>Symbol:</span>
            {['OANDA:XAUUSD','OANDA:EURUSD','OANDA:GBPUSD'].map(s => (
              <button key={s} onClick={() => setSym(s)} style={{
                height:26, padding:'0 8px', border:'1px solid var(--border)',
                borderRadius:7, background: sym===s ? 'var(--gold-soft)' : 'var(--surface)',
                color: sym===s ? 'var(--gold-dark)' : 'var(--text-muted)',
                fontWeight:800, fontSize:10, cursor:'pointer',
              }}>{s.split(':')[1]}</button>
            ))}
          </div>
        </div>
        {/* Chart container */}
        <div style={{ flex:1, position:'relative', borderRadius:12, overflow:'hidden', border:'1px solid var(--border)', background: isDark ? '#0a0e14' : '#f7f5f0', minHeight: Math.max(320, height - 50) }}>
          {!loaded && !error && (
            <div style={{ position:'absolute', inset:0, display:'grid', placeItems:'center', zIndex:2, pointerEvents:'none' }}>
              <div style={{ textAlign:'center', color:'var(--text-muted)' }}>
                <div style={{ width:36, height:36, border:'3px solid var(--gold)', borderTopColor:'transparent', borderRadius:'50%', animation:'spin 1s linear infinite', margin:'0 auto 12px' }}/>
                <div style={{ fontWeight:700, fontSize:13 }}>Loading TradingView chart…</div>
              </div>
            </div>
          )}
          {error && (
            <div style={{ position:'absolute', inset:0, display:'grid', placeItems:'center', zIndex:2 }}>
              <div style={{ textAlign:'center', color:'var(--text-muted)', padding:24 }}>
                <div style={{ fontSize:32, marginBottom:8 }}>📊</div>
                <div style={{ fontWeight:700, marginBottom:6 }}>Chart loading…</div>
                <div style={{ fontSize:12 }}>
                  <a href={`https://www.tradingview.com/chart/?symbol=${sym.replace(':','%3A')}&interval=${tf}`}
                     target="_blank" rel="noopener noreferrer"
                     style={{ color:'var(--gold-dark)', textDecoration:'underline' }}>
                    Open full chart on TradingView ↗
                  </a>
                </div>
              </div>
            </div>
          )}
          <div id={containerId.current} style={{ width:'100%', height:'100%', minHeight: Math.max(320, height - 50) }}/>
        </div>
      </div>
      {/* Signal panel */}
      {showSignalPanel && signal?.entry && (
        <div style={{ display:'flex', flexDirection:'column', gap:8, minWidth:0 }}>
          <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:12, padding:'12px 14px', height:'100%', overflow:'auto' }}>
            <div style={{ fontSize:11, fontWeight:800, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'.08em', marginBottom:10 }}>
              Live Signal
            </div>
            <SignalOverlay signal={signal}/>
          </div>
        </div>
      )}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

export default TradingViewChart;
