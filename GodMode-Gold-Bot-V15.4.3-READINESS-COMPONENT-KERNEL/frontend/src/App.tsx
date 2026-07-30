import { Component, Suspense, type ErrorInfo, type ReactNode, useEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import { pages } from './router';
import { ActionCenter } from './components/ActionCenter';
import { api } from './lib/api';
import { usePoll } from './lib/usePoll';

function getInitialPage(){return window.location.hash.replace('#/','')||'dashboard'}

class PageErrorBoundary extends Component<{page:string; children:ReactNode}, {hasError:boolean; message:string}> {
  constructor(props:{page:string; children:ReactNode}){
    super(props);
    this.state={hasError:false,message:''};
  }
  static getDerivedStateFromError(error:Error){
    return {hasError:true,message:error?.message||'Unknown page error'};
  }
  componentDidCatch(error:Error, info:ErrorInfo){
    console.error('[GodMode UI page crash]', this.props.page, error, info);
    try{window.dispatchEvent(new CustomEvent('godmode:notify',{detail:{title:'Page recovered',body:`${this.props.page} page hit a render error. Use Reload Page after backend reconnects.`,sound:'warning'}}));}catch{}
  }
  componentDidUpdate(prev:{page:string}){
    if(prev.page!==this.props.page && this.state.hasError){
      this.setState({hasError:false,message:''});
    }
  }
  render(){
    if(this.state.hasError){
      return <div className="page"><div className="card" style={{padding:20}}><h2>Page recovered instead of going blank</h2><p className="muted">The {this.props.page} page received unexpected/stale data or a temporary backend response.</p><p className="tiny muted">{this.state.message}</p><div className="button-wrap"><button className="gold-button" onClick={()=>this.setState({hasError:false,message:''})}>Reload Page</button><button className="outline-button" onClick={()=>{window.location.hash='/dashboard'}}>Go Dashboard</button></div></div></div>;
    }
    return this.props.children;
  }
}

export default function App(){
  const[page,setPage]=useState(getInitialPage());
  const[stale,setStale]=useState<{path:string;age:number}|null>(null);
  const[safety,setSafety]=useState<'LIVE'|'STALE'|'OFFLINE'|'AUTH_REQUIRED'|'DEGRADED'>('OFFLINE');
  const[tradingReadiness,setTradingReadiness]=useState<{ready:boolean;warnings:string[];reasons:string[];executionAuthority:any}>({ready:false,warnings:[],reasons:[],executionAuthority:null});
  // api.readiness() publishes godmode:safety-state / godmode:trading-readiness as a side effect;
  // the banners below are driven by those events, which is why the result is not read here.
  usePoll(()=>api.readiness(), 8000);
  const Page=pages[page]||pages.dashboard;
  useEffect(()=>{const onHash=()=>setPage(getInitialPage());window.addEventListener('hashchange',onHash);return()=>window.removeEventListener('hashchange',onHash)},[]);
  useEffect(()=>{const onStale=(e:Event)=>{const d=(e as CustomEvent).detail||{};setStale({path:String(d.path||'API'),age:Number(d.staleAgeMs||0)});setSafety('STALE');};const onLive=()=>{setStale(null);setSafety('LIVE');};const onSafety=(e:Event)=>setSafety(((e as CustomEvent).detail?.state||'OFFLINE'));window.addEventListener('godmode:stale-data',onStale);window.addEventListener('godmode:live-data',onLive);window.addEventListener('godmode:safety-state',onSafety);return()=>{window.removeEventListener('godmode:stale-data',onStale);window.removeEventListener('godmode:live-data',onLive);window.removeEventListener('godmode:safety-state',onSafety)}},[]);
  useEffect(()=>{const onTradingReadiness=(e:Event)=>{const d=(e as CustomEvent).detail||{};setTradingReadiness({ready:d.tradingReady===true,warnings:Array.isArray(d.warnings)?d.warnings.map(String):[],reasons:Array.isArray(d.reasons)?d.reasons.map(String):[],executionAuthority:d.executionAuthority||null});};window.addEventListener('godmode:trading-readiness',onTradingReadiness);return()=>window.removeEventListener('godmode:trading-readiness',onTradingReadiness);},[]);
  const navigate=(next:string)=>{window.location.hash=`/${next}`;setPage(next)};
  const authorityBlockers=Array.isArray(tradingReadiness.executionAuthority?.blockers)?tradingReadiness.executionAuthority.blockers.map(String):[];
  const tradingDetail=[...authorityBlockers,...tradingReadiness.reasons,...tradingReadiness.warnings].filter((v,i,a)=>v&&a.indexOf(v)===i).join(' · ');
  return <AppShell current={page} onNavigate={navigate}>{safety!=='LIVE'&&<div style={{position:'sticky',top:0,zIndex:9999,padding:'10px 16px',background:safety==='AUTH_REQUIRED'?'#92400e':'#7f1d1d',color:'white',fontWeight:700}}>TRADING EXECUTION PROTECTED: {safety}. {stale?`Cached data is ${Math.round(stale.age/1000)}s old for ${stale.path}.`:'Navigation and settings remain available; order-entry actions stay blocked until backend readiness is confirmed.'}</div>}{safety==='LIVE'&&!tradingReadiness.ready&&<div style={{position:'sticky',top:0,zIndex:9998,padding:'10px 16px',background:'#92400e',color:'white',fontWeight:700}}>EXECUTION AUTHORITY NOT ARMED. {tradingDetail||'Enable and validate live execution when you are ready; dry-run controls remain available.'}</div>}<PageErrorBoundary page={page}><Suspense fallback={<div className="page"><div className="card">Loading secured dashboard module…</div></div>}><div key={page} className="page"><Page/><div className="footer-risk">The GodMode Gold Trading Bot is for educational purposes only. Trading involves risk.</div></div></Suspense></PageErrorBoundary><ActionCenter/></AppShell>
}
