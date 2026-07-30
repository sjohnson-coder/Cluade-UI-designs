import { useEffect, useState, useCallback } from 'react';
import { Activity, RefreshCcw, PlugZap, Stethoscope, FileText, HeartPulse, Database, ArrowLeftRight, Cpu, NotebookPen, ShieldCheck, CalendarDays, Newspaper, Globe, Plug, Copy, Check, X } from 'lucide-react';
import { Card, PageHeader, Tag, SectionTitle, MetricCard, Checklist } from '../components/ui';
import { api } from '../lib/api';

const ICONS: Record<string, any> = { mt5: Plug, dataSource: Database, trading: ArrowLeftRight, scanLoop: Cpu, journal: NotebookPen, riskEngine: ShieldCheck, feedCalendar: CalendarDays, feedNews: Newspaper, feedMacro: Globe };
const tone = (s: string): 'green'|'red'|'gold' => s==='up'?'green':s==='down'?'red':'gold';
const lbl = (s: string) => (({up:'OK',warn:'CHECK',down:'DOWN',demo:'DEMO'} as any)[s] || '?');

// In-page GitHub-style JSON viewer with copy
function CodeViewer({ title, open, onClose, loader }: { title: string; open: boolean; onClose: ()=>void; loader: ()=>Promise<any> }) {
  const [body, setBody] = useState('Loading…');
  const [copied, setCopied] = useState(false);
  useEffect(() => { if (open) { setBody('Loading…'); loader().then(d => setBody(JSON.stringify(d, null, 2))).catch(e => setBody('Error: ' + String(e))); } }, [open]);
  if (!open) return null;
  const copy = async () => { try { await navigator.clipboard.writeText(body); setCopied(true); setTimeout(()=>setCopied(false), 1500); } catch {} };
  return (
    <div className="code-modal-overlay" onClick={onClose}>
      <div className="code-modal" onClick={e => e.stopPropagation()}>
        <div className="code-modal-head">
          <span className="code-modal-title"><FileText size={15}/> {title}</span>
          <div className="code-modal-actions">
            <button className="ghost-button" onClick={copy}>{copied ? <><Check size={14}/> Copied</> : <><Copy size={14}/> Copy</>}</button>
            <button className="ghost-button" onClick={onClose}><X size={14}/></button>
          </div>
        </div>
        <pre className="code-modal-body"><code>{body}</code></pre>
      </div>
    </div>
  );
}

export default function Health() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [viewer, setViewer] = useState<null | 'health' | 'log'>(null);
  const [toast, setToast] = useState<{msg:string; tone:'green'|'red'|'gold'}|null>(null);
  const [lastRefresh, setLastRefresh] = useState<string>('');
  const flash = (msg:string, tone:'green'|'red'|'gold'='green') => { setToast({msg,tone}); setTimeout(()=>setToast(null), 4000); };

  const load = useCallback(async (announce=false) => {
    try {
      const d = await api.health();
      setData(d);
      setLastRefresh(new Date().toLocaleTimeString());
      if (announce) flash(`Refreshed — ${d?.summary?.up ?? 0} up / ${d?.summary?.warn ?? 0} check / ${d?.summary?.down ?? 0} down`, (d?.summary?.down ? 'red' : d?.summary?.warn ? 'gold' : 'green'));
      return d;
    } catch {
      setData({ ok:false, overall:'critical', dataSource:'offline', isRealData:false, components:[], summary:{up:0,warn:0,down:0,criticalDown:[]} });
      setLastRefresh(new Date().toLocaleTimeString());
      if (announce) flash('Refresh failed — backend unreachable', 'red');
      return null;
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(()=>load(false), 15000); return () => clearInterval(t); }, [load]);

  const reconnect = async () => {
    setBusy('r');
    const before = !!data?.isRealData;
    let res:any = null;
    try { res = await api.mt5Reconnect(); } catch { res = { ok:false, message:'request failed' }; }
    await new Promise(r=>setTimeout(r,1500));
    const after = await load();
    setBusy('');
    const nowReal = !!after?.isRealData;
    if (nowReal && !before) flash('Reconnected — MT5 is now LIVE', 'green');
    else if (nowReal) flash('MT5 already connected — link verified', 'green');
    else flash(`Reconnect failed: ${res?.message || 'MT5 terminal not reachable. Is it running and logged in?'}`, 'red');
  };

  const overall = data?.overall || 'critical';
  const isReal = !!data?.isRealData;
  const ds = data?.dataSource || 'offline';
  const summary = data?.summary || { up:0, warn:0, down:0, criticalDown:[] };
  const components = data?.components || [];
  const oTone = overall==='healthy'?'green':overall==='degraded'?'gold':'red';
  const oText = loading?'Checking…':overall==='healthy'?'All systems operational':overall==='degraded'?'Running with warnings':'Critical issue detected';

  return (
    <div className="page">
      <PageHeader title="Health Center" subtitle="Live status of every subsystem — what is real, what is demo, what stopped working." right={
        <div className="button-wrap">
          <button className="outline-button" onClick={()=>load(true)} data-sound="navigate"><RefreshCcw size={14}/> Refresh</button>
          <button className="outline-button" onClick={reconnect} disabled={busy==='r'} data-sound="navigate"><PlugZap size={14}/> {busy==='r'?'Reconnecting…':'Reconnect MT5'}</button>
        </div>
      }/>

      {toast && <div className={`health-toast ${toast.tone}`}>{toast.msg}</div>}
      <Card className={`health-banner ${oTone}`}>
        <div className="health-banner-row">
          <div>
            <div className="health-banner-title"><span className={`live-dot ${oTone==='red'?'red':oTone==='gold'?'gold':''}`}/><strong>{oText}</strong></div>
            <p className="muted tiny" style={{margin:'6px 0 0'}}>{summary.criticalDown?.length ? `Down: ${summary.criticalDown.join(', ')}` : `build ${data?.build||'—'} · ${summary.up} up · ${summary.warn} check · ${summary.down} down`}</p>
          </div>
          {isReal ? <Tag color="green">● REAL MT5 DATA</Tag> : ds==='synthetic_demo' ? <Tag color="gold">● DEMO — NOT REAL</Tag> : <Tag color="red">● OFFLINE</Tag>}
        </div>
      </Card>

      <div className="metric-grid" style={{marginTop:16}}>
        <MetricCard label="Data Source" value={isReal?'LIVE MT5':ds==='synthetic_demo'?'DEMO':'OFFLINE'}/>
        <MetricCard label="Live Trading Allowed" value={data?.executionMode==='DRY_RUN'?'DRY RUN':data?.tradingAllowed?'YES':'NO'}/>
        <MetricCard label="Subsystems Up" value={`${summary.up}/${components.length}`}/>
        <MetricCard label="Build" value={data?.build||'—'}/>
      </div>

      <SectionTitle title="Subsystems"/>
      <div className="health-grid">
        {components.map((c: any) => {
          const Icon = ICONS[c.id] || Activity; const t = tone(c.status);
          return (
            <Card key={c.id} className="health-card">
              <div className="health-card-head"><Icon size={17}/><strong>{c.label}</strong><span className={`live-dot ${t==='red'?'red':t==='gold'?'gold':''}`}/></div>
              <Tag color={t}>{lbl(c.status)}{c.critical?' · critical':''}</Tag>
              <p className="muted tiny" style={{margin:'8px 0 0',lineHeight:1.5}}>{c.detail}</p>
            </Card>
          );
        })}
      </div>

      <SectionTitle title="Diagnostics"/>
      <Card>
        <div className="button-wrap">
          <button className="outline-button" onClick={()=>setViewer('health')}><Stethoscope size={14}/> Raw Diagnose</button>
          <button className="outline-button" onClick={()=>setViewer('log')}><FileText size={14}/> Decision Log</button>
        </div>
        {data?.config && (
          <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:12}}>
            <Tag color={data.config.conditionalTimeStop?'green':'gold'}>Time-stop {data.config.conditionalTimeStop?'ON':'off'}</Tag>
            <Tag color={data.config.convictionTiering?'green':'gold'}>Conviction tiering {data.config.convictionTiering?'ON':'off'}</Tag>
            <Tag color={data.config.htfAlignment?'green':'gold'}>HTF alignment {data.config.htfAlignment?'ON':'off'}</Tag>
          </div>
        )}
        <p className="muted tiny" style={{marginTop:12}}>Auto-refresh every 15s. Each status is read live from the bot — never a hardcoded green.</p>
      </Card>

      <CodeViewer title="/api/health/full" open={viewer==='health'} onClose={()=>setViewer(null)} loader={api.health}/>
      <CodeViewer title="/api/journal/decisions" open={viewer==='log'} onClose={()=>setViewer(null)} loader={()=>api.decisions?.() ?? fetch('/api/journal/decisions').then(r=>r.json())}/>
    </div>
  );
}
