import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Bell, Search, Sun, Moon, Monitor, Volume2, VolumeX, LayoutDashboard, Radio, SlidersHorizontal, Bot, ShieldCheck, BarChart3, BookOpen, Settings, Zap, UserRound, ChevronDown } from 'lucide-react';
import { useThemeStore } from '../store/themeStore';
import { useSoundStore } from '../store/soundStore';
import { useGodModeSounds } from './SoundManager';
import { api } from '../lib/api';
import crownUrl from '../assets/godmode-crown.svg';

const nav = [
  ['dashboard','Dashboard',LayoutDashboard], ['signals','Signals',Radio], ['strategies','Strategies',Search], ['trades','Trades',SlidersHorizontal], ['ai','AI Agent',Bot], ['risk','Risk',ShieldCheck], ['analytics','Analytics',BarChart3], ['journal','Journal',BookOpen], ['settings','Settings',Settings],
] as const;

function readUser(){try{return JSON.parse(localStorage.getItem('godmode_user')||'{}')}catch{return {}}}

export function AppShell({ current, onNavigate, children }: { current:string; onNavigate:(p:string)=>void; children:ReactNode }) {
  const { theme, setTheme } = useThemeStore();
  const { enabled: soundEnabled, toggleSound, play } = useSoundStore();
  const [status, setStatus] = useState<any>({ mt5Connected: false, marketSession: 'Unknown', mt5: {} });
  const [user,setUser]=useState<any>(readUser());
  const [notice,setNotice]=useState<any>({unread:0,items:[]});
  const [noticeOpen,setNoticeOpen]=useState(false);
  useGodModeSounds();

  const loadNotifications=async()=>setNotice(await api.notifications());
  useEffect(()=>{const onStorage=()=>setUser(readUser());window.addEventListener('storage',onStorage);return()=>window.removeEventListener('storage',onStorage)},[]);
  const [spread, setSpread] = useState<number|null>(null);
  useEffect(() => {let active=true; const load=async()=>{const [fresh,notes,mkt]=await Promise.all([api.status(), api.notifications(), api.marketSnapshot()]); if(active){setStatus(fresh);setNotice(notes);setSpread(typeof mkt?.spread==='number'?mkt.spread:null)}}; load(); const id=window.setInterval(load,5000); return()=>{active=false; window.clearInterval(id)}}, []);
  useEffect(()=>{const onNotify=(ev:any)=>{play(ev?.detail?.sound||'success');loadNotifications()};window.addEventListener('godmode:notify',onNotify);return()=>window.removeEventListener('godmode:notify',onNotify)},[play]);

  const mt5 = status?.mt5 || {};
  const connected = Boolean(status?.mt5Connected || mt5.connected);
  const isDemo = Boolean(status?.demo || mt5.demo || status?.source === 'demo');
  const liveTrading = Boolean(mt5.liveTradingEnabled);
  const session = status?.marketSession || mt5.session || 'Unknown';
  const profile = useMemo(()=>({name:user?.name || 'Alex Trader', plan:user?.plan || (liveTrading?'Live Mode':'Premium Pro')}),[user,liveTrading]);
  const clearNotes=async()=>{const n=await api.clearNotifications(); setNotice(n); setNoticeOpen(false)};

  return <div className="app-frame">
    <div className="app-shell">
      <aside className="sidebar">
        <div className="logo"><img className="logo-crown" src={crownUrl}/><div><div className="logo-title">GODMODE</div><div className="logo-sub">GOLD TRADING BOT</div></div></div>
        <nav className="nav">{nav.map(([id,label,Icon]) => <button key={id} data-sound="navigate" onClick={() => onNavigate(id)} className={`nav-item ${current===id?'active':''}`}><Icon size={18}/><span className="label">{label}</span></button>)}</nav>
        <div className="sidebar-spacer"/>
        <div className="elite-card"><img src={crownUrl}/><h3>GODMODE ELITE</h3><p>Unlock full power</p><button className="gold-button" data-sound="success" onClick={()=>onNavigate('settings')}>Upgrade Now</button></div>
        <div className="sidebar-footer">© 2026 GodMode Gold Bot<br/>All rights reserved.</div>
      </aside>
      <main className="main">
        <header className="topbar">
          <StatusChip label="Live Connection" value={connected ? (isDemo ? 'DEMO' : 'LIVE') : 'STANDBY'} tone={connected ? 'green' : 'gold'}/>
          <StatusChip label="MT5" value={connected ? (isDemo ? 'Demo Mode' : 'Connected') : 'Waiting'} tone={connected ? 'green' : 'red'} dropdown/>
          <StatusChip label="Market Session" value={session} tone="gold" dropdown/>
          {spread !== null && <StatusChip label="XAUUSD Spread" value={spread.toFixed(2)} tone={spread < 0.35 ? 'green' : 'red'}/>}
          <div className="search"><Search size={15}/><input placeholder="Search markets, pairs, strategies..."/></div>
          <div className="topbar-right">
            <div className="theme-toggle" data-sound="toggle" role="group" aria-label="Theme mode">
              <button className={theme==='light'?'active':''} onClick={() => setTheme('light')}><Sun size={14}/> Light</button>
              <button className={theme==='dark'?'active':''} onClick={() => setTheme('dark')}><Moon size={14}/> Dark</button>
              <button className={theme==='system'?'active':''} onClick={() => setTheme('system')}><Monitor size={14}/> System</button>
            </div>
            <button className="bell" onClick={toggleSound} title={soundEnabled ? 'UI sound on' : 'UI sound muted'} data-sound="toggle">{soundEnabled ? <Volume2 size={19}/> : <VolumeX size={19}/>}</button>
            <div className="notice-box">
              <button className="bell" title="System alerts" onClick={() => setNoticeOpen(!noticeOpen)}><Bell size={19}/>{Number(notice?.unread||0)>0&&<span className="badge-count">{notice.unread}</span>}</button>
              {noticeOpen&&<div className="notice-menu"><div className="notice-head"><strong>Notifications</strong><button className="ghost-button" onClick={clearNotes}>Mark read</button></div>{(notice.items||[]).length?notice.items.slice(0,6).map((n:any)=><div className={`notice-item ${n.kind||''}`} key={n.id}><strong>{n.title}</strong><span>{n.message}</span><small>{n.time}</small></div>):<p className="muted tiny">No bot notifications yet.</p>}</div>}
            </div>
            <button className="profile" onClick={()=>onNavigate('login')} title="Open profile/login"><div className="avatar"><UserRound size={18}/></div><div><strong>{profile.name}</strong><span className="premium"><Zap size={11}/> {profile.plan}</span></div><ChevronDown size={15}/></button>
          </div>
        </header>
        {children}
      </main>
    </div>
  </div>
}

function StatusChip({ label, value, tone='green', dropdown=false }: { label:string; value:string; tone?:'green'|'red'|'gold'; dropdown?: boolean }) {
  return <div className="status-chip"><span className={`live-dot ${tone==='red'?'red':tone==='gold'?'gold':''}`}/><div><span>{label}</span><strong>{value}</strong></div>{dropdown ? <ChevronDown size={13} color="var(--text-muted)"/> : <small>{(value==='LIVE'||value==='DEMO')?value:''}</small>}</div>
}
