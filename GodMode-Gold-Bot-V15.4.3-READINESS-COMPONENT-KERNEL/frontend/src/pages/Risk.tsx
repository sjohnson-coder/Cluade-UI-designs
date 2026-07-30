import { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCcw, Save, ShieldCheck } from 'lucide-react';
import { Card, Checklist, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, Tag, ToggleSwitch } from '../components/ui';
import { Donut } from '../components/Charts';
import { api } from '../lib/api';
import { usePoll } from '../lib/usePoll';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const pct=(v:any)=>`${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}%`;

function RiskCard({title,main,value,sub,onEdit}:{title:string;main:string;value:number;sub:string;onEdit:()=>void}){
  return <Card><SectionTitle title={title} right={<button className="ghost-button" onClick={onEdit}>Edit</button>}/><h2 className="value">{main}</h2><p className="muted tiny">{sub}</p><ProgressBar value={value}/></Card>;
}

export default function Risk(){
  const [data,setData]=useState<any>({account:{},trades:{active:[]},warnings:[],limits:{}});
  const [edit,setEdit]=useState<any|null>(null); const [message,setMessage]=useState('');
  const [caps,setCaps]=useState<Record<string,number>>({});
  const [refreshing,setRefreshing]=useState(false);
  const [alertsOpen,setAlertsOpen]=useState(false); const [notes,setNotes]=useState<any[]>([]);
  const load=async()=>setData(await api.risk());
  const refresh=async()=>{setRefreshing(true);await load();if(alertsOpen){const n:any=await api.notifications();setNotes(n?.items||[])}setMessage('Risk data refreshed.');setTimeout(()=>setMessage(''),1500);setRefreshing(false)};
  const viewAllAlerts=async()=>{if(!alertsOpen){const n:any=await api.notifications();setNotes(n?.items||[])}setAlertsOpen(o=>!o)};
  usePoll(load,7000);
  // Seed editable session caps once from the persisted limits (don't clobber edits on poll).
  useEffect(()=>{const sc=data?.limits?.sessionCaps; if(sc&&Object.keys(caps).length===0)setCaps(sc)},[data]);
  const acc=data.account||{}, currency=acc.currency||''; const active=data.trades?.active||[];
  const limits=data.limits||{}; const overrides=data.overrides||{}; const ruleOverrides=overrides.rules||{};
  const openRisk=Number(acc.openRiskPct??0); const margin=Number(acc.marginHealth||0); const telemetry=data.telemetry||{};
  const demo=acc.source==='demo';

  // Rules table is driven by the persisted structured limits + any saved row overrides.
  const baseRules:[string,string,string][]=[
    ['Max Daily Loss',pct(limits.maxDailyLossPct),`${money(acc.dailyPnl,currency)} (${pct(acc.dailyLossUsedPct||0)})`],
    ['Max Drawdown',pct(limits.maxDrawdownPct),pct(acc.drawdownPct||0)],
    ['Max Risk Per Trade',pct(limits.maxRiskPerTradePct),'—'],
    ['Max Open Risk',pct(limits.maxOpenRiskPct),pct(openRisk)],
    ['Max Exposure',`${pct(limits.maxExposurePct)} Equity`,'—'],
    ['Loss Streak Limit',`${limits.lossStreakLimit||5} consecutive losses`,String(telemetry.lossStreak??'Unavailable')],
    ['Circuit Breaker',pct(limits.circuitBreakerPct),telemetry.emergencyStopActive?'TRIPPED':'Armed'],
    ['News Filter (High Impact)',`${limits.newsFilterMinutes||15} min before/after`,telemetry.newsGuardEnabled?'Enabled':'Disabled'],
  ];
  const rows=baseRules.map(([rule,limit,current])=>{
    const o=ruleOverrides[rule];
    return {Rule:rule,Status:o?o.enabled!==false:true,Limit:o?.limit||limit,Current:current};
  });

  const saveEdit=async()=>{
    const r=await api.riskUpdate({rule:edit.rule||edit.title,limit:edit.limit||edit.main,enabled:edit.enabled!==false});
    setMessage(r?.ok?(r.message||'Risk rule saved and applied.'):'Risk save failed.');
    setEdit(null); await load(); setTimeout(()=>setMessage(''),3500);
  };
  // Persist a rule toggle/limit straight from the table (no modal needed).
  const saveRule=async(rule:string,limit:any,enabled:boolean)=>{
    const r=await api.riskUpdate({rule,limit,enabled});
    setMessage(r?.ok?(r.message||`Saved: ${rule}`):'Risk save failed.');
    await load(); setTimeout(()=>setMessage(''),3000);
  };
  // Save all session risk caps at once (sends the full merged map).
  const saveCaps=async()=>{
    const r=await api.riskUpdate({sessionCaps:caps});
    setMessage(r?.ok?'Session risk caps saved.':'Save failed.');
    await load(); setTimeout(()=>setMessage(''),3000);
  };

  return <div className="risk-page exact-risk">
    <PageHeader title="Risk Management Center" subtitle="Advanced risk controls, protection systems, and capital preservation engine." right={<><Tag color={acc.connected?'green':'gold'}>Risk Engine: {acc.connected?'LIVE':'NO BROKER'}</Tag><button className="outline-button" onClick={refresh} disabled={refreshing}><RefreshCcw size={14} className={refreshing?'spin':''}/> {refreshing?'Refreshing…':'Refresh'}</button></>}/>
    {demo&&<Card className="demo-banner"><ShieldCheck size={15}/><span>Demo data active — connect MetaTrader 5 for live account risk. Edits below persist and take effect on save.</span></Card>}
    {message&&<Card className="action-banner"><span>{message}</span></Card>}
    {edit&&<Card className="risk-edit-panel"><SectionTitle title={`Edit ${edit.rule||edit.title}`} right={<button className="ghost-button" onClick={()=>setEdit(null)}>Close</button>}/>
      <div className="grid grid-3"><label className="form-row"><span>Rule</span><input className="input" value={edit.rule||edit.title||''} onChange={e=>setEdit({...edit,rule:e.target.value})}/></label><label className="form-row"><span>Limit / Value</span><input className="input" value={edit.limit||edit.main||''} onChange={e=>setEdit({...edit,limit:e.target.value})}/></label><label className="form-row"><span>Enabled</span><ToggleSwitch checked={edit.enabled!==false} onChange={v=>setEdit({...edit,enabled:v})}/></label></div>
      <button className="gold-button" onClick={saveEdit} style={{marginTop:12}}><Save size={14}/> Save Risk Rule</button></Card>}
    <div className="risk-layout">
      <div>
        <div className="grid grid-4 risk-top"><MetricCard label="Account Balance" value={money(acc.balance,currency)}/><MetricCard label="Equity" value={money(acc.equity,currency)}/><MetricCard label="Daily PnL" value={money(acc.dailyPnl,currency)}/><MetricCard label="Free Margin" value={money(acc.freeMargin,currency)}/></div>
        <div className="grid grid-4" style={{marginTop:16}}>
          <RiskCard title="Max Daily Loss" main={pct(limits.maxDailyLossPct)} value={Number(acc.dailyLossUsedPct||0)} sub={`${money(acc.dailyPnl,currency)} used`} onEdit={()=>setEdit({rule:'Max Daily Loss',limit:pct(limits.maxDailyLossPct),enabled:true})}/>
          <RiskCard title="Drawdown Guard" main={pct(limits.maxDrawdownPct)} value={Number(acc.drawdownPct||0)} sub="Current DD" onEdit={()=>setEdit({rule:'Max Drawdown',limit:pct(limits.maxDrawdownPct),enabled:true})}/>
          <RiskCard title="Circuit Breaker" main={pct(limits.circuitBreakerPct)} value={Number(acc.drawdownPct||0)} sub="Daily loss trigger · Armed" onEdit={()=>setEdit({rule:'Circuit Breaker',limit:pct(limits.circuitBreakerPct),enabled:true})}/>
          <RiskCard title="Open Risk" main={pct(openRisk)} value={openRisk*8} sub="of equity" onEdit={()=>setEdit({rule:'Max Open Risk',limit:pct(limits.maxOpenRiskPct),enabled:true})}/>
        </div>
        <div className="grid grid-4" style={{marginTop:16}}>
          <Card><SectionTitle title="Exposure by Symbol"/><Donut value={active.length?Math.min(100,active.length*18):0}/><Checklist items={[{label:'XAUUSD',value:`${active.length} open`},{label:'Max allowed',value:`${pct(limits.maxExposurePct)}`}]}/></Card>
          <Card><SectionTitle title="Lot Sizing Rules" right={<button className="ghost-button" onClick={()=>setEdit({rule:'Max Risk Per Trade',limit:pct(limits.maxRiskPerTradePct),enabled:true})}>Edit</button>}/><Checklist items={[{label:'Base risk per trade',value:pct(limits.maxRiskPerTradePct)},{label:'Risk model',value:'ATR Based'},{label:'ATR multiplier',value:'1.25x'},{label:'Dynamic sizing',value:'Active',type:'success'}]}/></Card>
          <Card><SectionTitle title="Session Risk Caps" right={<button className="ghost-button" onClick={saveCaps}><Save size={13}/> Save</button>}/><div className="grid grid-2">{['London','New York','Asia','Overlap'].map(s=><label className="form-row" key={s}><span>{s}</span><input className="input" type="number" step="0.1" value={caps[s]??''} placeholder="%" onChange={e=>setCaps({...caps,[s]:Number(e.target.value)})}/></label>)}</div><p className="muted tiny">Max % risk per trade allowed during each session. Edits persist on Save.</p></Card>
          <Card><SectionTitle title="Spread & Slippage Guard"/><Checklist items={[{label:'Current spread',value:telemetry.spread==null?'Unavailable':String(telemetry.spread)},{label:'Configured max spread',value:String(limits.maxSpreadXau??'Unavailable')},{label:'Broker connected',value:acc.connected?'YES':'NO',type:acc.connected?'success':'warning'},{label:'Open-risk measurement',value:telemetry.openRiskKnown?'COMPLETE':'UNAVAILABLE / UNPROTECTED',type:telemetry.openRiskKnown?'success':'warning'}]}/></Card>
        </div>
        <div className="grid grid-4" style={{marginTop:16}}>
          <Card><SectionTitle title="Margin Health"/><div className="donut-wrap"><Donut value={margin}/><strong className="donut-center">{margin}%</strong></div></Card>
          <Card><SectionTitle title="Loss Streak Protection"/><Donut value={Math.min(100,Number(telemetry.lossStreak||0)/Math.max(1,Number(limits.lossStreakLimit||5))*100)}/><Checklist items={[{label:'Max loss streak',value:String(limits.lossStreakLimit||5)},{label:'Current streak',value:String(telemetry.lossStreak??'Unavailable')},{label:'Telemetry source',value:acc.connected?'BROKER HISTORY':'UNAVAILABLE',type:acc.connected?'success':'warning'}]}/></Card>
          <Card><SectionTitle title="Portfolio Correlation"/><Donut value={0}/><Checklist items={[{label:'Status',value:'N/A — single-symbol bot'},{label:'Instrument',value:'XAUUSD'},{label:'No fabricated score',value:'CONFIRMED',type:'success'}]}/></Card>
          <Card><SectionTitle title="Risk Engine Controls"/><Checklist items={[{label:'Global Risk Engine',value:telemetry.riskEngineEnabled?'ON':'OFF',type:telemetry.riskEngineEnabled?'success':'warning'},{label:'Volatility sizing',value:telemetry.volatilitySizingEnabled?'ON':'OFF',type:telemetry.volatilitySizingEnabled?'success':'warning'},{label:'News fail-closed',value:telemetry.newsGuardEnabled?'ON':'OFF',type:telemetry.newsGuardEnabled?'success':'warning'},{label:'Emergency stop',value:telemetry.emergencyStopActive?'ACTIVE':'CLEAR',type:telemetry.emergencyStopActive?'danger':'success'}]}/></Card>
        </div>
        <div className="grid grid-2" style={{marginTop:16}}>
          <Card><SectionTitle title="Risk Rules Editor"/><DataTable columns={['Rule','Status','Limit / Value','Current','Action']} rows={rows} renderCell={(r,c)=>c==='Status'?<ToggleSwitch checked={r.Status} onChange={(v)=>saveRule(r.Rule,r.Limit,v)}/>:c==='Action'?<button className="ghost-button" onClick={()=>setEdit({rule:r.Rule,limit:r.Limit,enabled:r.Status})}>Edit</button>:c==='Limit / Value'?r.Limit:r[c]}/></Card>
          <Card><SectionTitle title="Strategy Risk Limits"/><DataTable columns={['Strategy','Risk Per Trade','Max Daily Loss','Status']} rows={(data.strategies||[]).slice(0,6)} renderCell={(r,c)=>c==='Status'?<Tag color={r.enabled!==false?'green':'red'}>{r.enabled!==false?'Active':'Off'}</Tag>:c==='Risk Per Trade'?'1.00%':c==='Max Daily Loss'?'3.00%':r[c==='Strategy'?'name':c]??'—'}/></Card>
        </div>
      </div>
      <div className="right-stack side-panel-sticky">
        <Card><SectionTitle icon={<AlertTriangle size={16}/>} title="Live Warnings & Alerts" right={<button className="ghost-button" onClick={viewAllAlerts}>{alertsOpen?'Hide':'View All'}</button>}/>{(data.warnings||[]).length?<Checklist items={data.warnings.map((w:any)=>({label:w.title,value:w.time,type:w.type==='danger'?'danger':w.type==='success'?'success':'warning'}))}/>:<Checklist items={[{label:'System Status',value:'All Systems Operational',type:'success'}]}/>}{alertsOpen&&<div style={{marginTop:10,borderTop:'1px solid var(--border-soft)',paddingTop:10}}><p className="tiny muted" style={{marginBottom:6}}>Recent system alerts &amp; notifications</p>{notes.length?<Checklist items={notes.slice(0,25).map((n:any)=>({label:n.title||n.message||'Alert',value:String(n.time||'').slice(11,19)||'',type:n.kind==='danger'?'danger':n.kind==='success'?'success':'warning'}))}/>:<p className="tiny muted">No alerts recorded yet — the bot logs risk, fast-fail, break-even and circuit-breaker events here as they happen.</p>}</div>}</Card>
        <Card><SectionTitle icon={<ShieldCheck size={16}/>} title="Risk Engine Controls"/><Checklist items={[{label:'Broker telemetry',value:acc.connected?'LIVE':'UNAVAILABLE',type:acc.connected?'success':'warning'},{label:'Open-risk basis',value:telemetry.openRiskKnown?'KNOWN':'UNKNOWN',type:telemetry.openRiskKnown?'success':'warning'},{label:'News fail-closed',value:telemetry.newsGuardEnabled?'ON':'OFF',type:telemetry.newsGuardEnabled?'success':'warning'},{label:'Emergency Stop',value:telemetry.emergencyStopActive?'ACTIVE':'CLEAR',type:telemetry.emergencyStopActive?'danger':'success'}]}/><div className="detail-row"><span>Engine Status</span><strong className={acc.connected?'positive':'gold'}>{acc.connected?'ACTIVE':'WAITING FOR MT5'}</strong></div></Card>
      </div>
    </div>
  </div>;
}
