import { useEffect, useMemo, useState } from 'react';
import { Download, FileText, RefreshCcw, Gauge, FlaskConical, Sparkles, Rss, Play, RotateCcw } from 'lucide-react';
import { Card, Checklist, DataTable, MetricCard, PageHeader, ProgressBar, SectionTitle, Tag, ToggleSwitch } from '../components/ui';
import { BarDistribution, Donut, DrawdownChart, EquityCurve, ReturnsCalendar, ReturnsHeatmap, ScatterPerformance } from '../components/Charts';
import { api, downloadExport } from '../lib/api';
import { jobStore, useJob, type JobState } from '../lib/jobStore';
import { usePoll } from '../lib/usePoll';
// Progress + Stop for a background job. Reads from the module-level store, so it keeps showing the
// live run (and lets you Stop it) even after you switch tabs and come back.
function JobBar({job,onStop,label}:{job:JobState;onStop:()=>void;label:string}){
  if(!job.running && !job.error) return null;
  if(job.error) return <p className="negative tiny" style={{marginTop:8}}>{label}: {job.error}</p>;
  const eta=job.eta!=null?(job.eta>60?`~${Math.ceil(job.eta/60)} min left`:`~${job.eta}s left`):'';
  return <div style={{marginTop:10}}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:10,marginBottom:5,flexWrap:'wrap'}}>
      <span className="tiny muted">{label} — running in the background · you can switch tabs/pages and it keeps going</span>
      <button className="ghost-button" style={{height:28}} onClick={onStop}>■ Stop</button>
    </div>
    <ProgressBar value={job.pct||0}/>
    <p className="tiny muted" style={{marginTop:5,display:'flex',justifyContent:'space-between',gap:10}}><span>{job.stage||'Working…'}</span><span>{job.pct||0}% {eta}</span></p>
  </div>;
}
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
function Pagination({page,pages,setPage}:{page:number;pages:number;setPage:(n:number)=>void}){
  if(pages<=1) return null;
  return <div className="pagination" style={{marginTop:12,display:'flex',gap:6,alignItems:'center',justifyContent:'flex-end',flexWrap:'wrap'}}>
    <button className="ghost-button" disabled={page<=0} onClick={()=>setPage(0)}>« First</button>
    <button className="ghost-button" disabled={page<=0} onClick={()=>setPage(page-1)}>‹ Prev</button>
    <span className="tiny muted">Page {page+1} of {pages}</span>
    <button className="ghost-button" disabled={page>=pages-1} onClick={()=>setPage(page+1)}>Next ›</button>
    <button className="ghost-button" disabled={page>=pages-1} onClick={()=>setPage(pages-1)}>Last »</button>
  </div>;
}
function TradesTab({history}:{history:any[]}){
  const per=15; const [page,setPage]=useState(0);
  const pages=Math.max(1,Math.ceil(history.length/per));
  const safe=Math.min(page,pages-1);
  const rows=history.slice(safe*per,(safe+1)*per);
  return <Card><SectionTitle title="Bot-only trade sample" right={<span className="tiny muted">{history.length} trades · showing {rows.length}</span>}/>
    <div style={{overflowX:'auto'}}><DataTable columns={['symbol','direction','pnlUsd','closeTime','reason']} rows={rows}/></div>
    <Pagination page={safe} pages={pages} setPage={setPage}/>
  </Card>;
}
export default function Analytics(){
  const [data,setData]=useState<any>({kpis:{},history:[]}),[report,setReport]=useState<any|null>(null),[tab,setTab]=useState('Overview');
  const [dateFrom,setDateFrom]=useState(''),[dateTo,setDateTo]=useState(''),[account,setAccount]=useState('All Accounts');
  const load=async()=>setData(await api.analytics(dateFrom,dateTo));
  usePoll(load,10000,[dateFrom,dateTo]);
  const k=data.kpis||{}, currency=data.currency||data.account?.currency||'';
  const getReport=async()=>setReport(await api.docsInfo());
  const topRows=data.topStrategies||[];
  const history=useMemo(()=>{const rows=data.history||[];return rows.filter((r:any)=>{const d=String(r.closeTime||r.date||'').slice(0,10);if(dateFrom&&d<dateFrom)return false;if(dateTo&&d>dateTo)return false;return true})},[data,dateFrom,dateTo]);
  const tabs=['Overview','Performance','Trades','Strategies','Decisions','Backtest','Strategy Lab','Risk','Reports','Custom'];
  return <div className="analytics-page exact-analytics">
    <PageHeader title="Analytics" subtitle="Deep performance insights and system intelligence." right={<><input className="input date-control" type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/><input className="input date-control" type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/><select className="input account-filter" value={account} onChange={e=>setAccount(e.target.value)}><option>All Accounts</option><option>GodMode Bot Only</option></select><button className="outline-button" onClick={load}><RefreshCcw size={14}/> Refresh</button><button className="outline-button" onClick={()=>downloadExport('analytics','json')}><Download size={14}/> Export</button></>}/>
    <div className="tabs-line">{tabs.map(x=><button key={x} className={tab===x?'active':''} onClick={()=>setTab(x)}>{x}</button>)}</div>
    <div className="top-kpis analytics-kpis"><MetricCard label="Net Profit" value={money(k.netProfit,currency)} delta={`${k.returnPct||0}%`}/><MetricCard label="Total Trades" value={history.length || k.totalTrades || 0} delta="bot only"/><MetricCard label="Win Rate" value={`${k.winRate||0}%`}/><MetricCard label="Profit Factor" value={k.profitFactor||0}/><MetricCard label="Expectancy" value={money(k.expectancy,currency)}/><MetricCard label="Max Drawdown" value={`${k.maxDrawdown||0}%`}/></div>
    {tab==='Overview'&&<AnalyticsOverview data={data} k={k} currency={currency} report={report} getReport={getReport}/>} 
    {tab==='Performance'&&<div className="analytics-layout"><div className="analytics-grid"><Card className="span-2"><SectionTitle title="Equity Curve"/><EquityCurve data={data.equityCurve||[]} height={300}/></Card><Card><SectionTitle title="Drawdown Curve"/><DrawdownChart data={data.drawdown||[]}/></Card><Card><SectionTitle title="Returns"/><ReturnsHeatmap data={data.returns||[]}/></Card><Card><SectionTitle title="Execution Quality"/><BarDistribution data={data.executionQuality||[]}/></Card></div></div>}
    {tab==='Trades'&&<TradesTab history={history}/>}
    {tab==='Strategies'&&<div className="analytics-layout"><div className="analytics-grid"><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Net PnL','Win Rate','Trades']} rows={topRows}/></Card><Card><SectionTitle title="Expectancy vs Win Rate"/><ScatterPerformance data={data.expectancyScatter||[]}/></Card></div></div>}
    {tab==='Risk'&&<div className="analytics-layout"><div className="analytics-grid"><Card><SectionTitle title="Win Rate Breakdown"/><Donut value={Number(k.winRate||0)}/></Card><Card><SectionTitle title="Drawdown Curve"/><DrawdownChart data={data.drawdown||[]}/></Card><Card><SectionTitle title="Confidence vs Result"/><ScatterPerformance data={data.confidenceResult||[]}/></Card></div></div>}
    {tab==='Reports'&&<Card><SectionTitle title="Full Report" right={<button className="outline-button" onClick={getReport}><FileText size={14}/> View Full Report</button>}/>{report?<pre className="code-box">{JSON.stringify(report,null,2)}</pre>:<p className="muted">Press View Full Report to generate the backend/API report information.</p>}</Card>}
    {tab==='Decisions'&&<DecisionLogTab/>}
    {tab==='Strategy Lab'&&<StrategyLabTab/>}
    {tab==='Backtest'&&<><BacktestTab/><ExitLabWfoCards/></>}
    {tab==='Custom'&&<Card><SectionTitle title="Custom Analytics Builder"/><p className="muted">Custom filters use the selected date range and bot-only MT5 trade history. More report templates can be added here.</p></Card>}
  </div>
}

function BacktestTab(){
  const [res,setRes]=useState<any>(null),[opt,setOpt]=useState<any>(null),[val,setVal]=useState<any>(null),[loading,setLoading]=useState(''),[msg,setMsg]=useState('');
  const [bars,setBars]=useState(4000),[spread,setSpread]=useState(0.20),[commission,setCommission]=useState(0.05),[slippage,setSlippage]=useState(0.02),[apply,setApply]=useState(false),[tf,setTf]=useState('M15');
  const [sweepRes,setSweepRes]=useState<any>(null);
  const runJ=useJob('backtest'), valJ=useJob('validate'), sweepJ=useJob('sweep');
  // Restore the last result from the backend on mount — so a finished backtest is still here even if
  // you clicked away before it finished, or reloaded the page (same persistence as the Strategy Lab).
  useEffect(()=>{(async()=>{const s:any=await api.settings();const t=s?.trading?.timeframe;if(t)setTf(t);const bc=s?.brokerCosts;if(bc){if(bc.spread!=null)setSpread(Number(bc.spread));if(bc.commission!=null)setCommission(Number(bc.commission));if(bc.slippage!=null)setSlippage(Number(bc.slippage));}if(jobStore.get('backtest').result||jobStore.get('validate').result)return;const b:any=await api.backtestLast();if(b?.result){setRes(b.result);if(b.validation?.validation)setVal(b.validation)}})()},[]);
  // Save the current spread/commission/slippage as your broker profile, so every future Validate runs at
  // your real costs (and the live cost gate uses the same commission). One-time calibration.
  const saveBrokerCosts=async()=>{try{const s:any=await api.settings();const next={...s,brokerCosts:{spread,commission,slippage},ai:{...(s.ai||{}),commissionPrice:commission}};await api.saveSettings(next);setMsg(`Saved your broker costs (spread ${spread} · comm ${commission} · slip ${slippage}). Every Validate now uses these.`);}catch{setMsg('Could not save broker costs.')}};
  // Capture job results into the view when they finish (survives tab switches via the store).
  useEffect(()=>{const r=runJ.result;if(r){setRes(r);if(r.ok===false)setMsg(r.message||'Backtest failed.')}},[runJ.result]);
  useEffect(()=>{const r=valJ.result;if(r){if(r.ok){setVal(r);setRes(r)}else setMsg(r.message||'Validation failed.')}},[valJ.result]);
  useEffect(()=>{const r=sweepJ.result;if(r){if(r.ok)setSweepRes(r);else setMsg(r.message||'Efficiency sweep failed.')}},[sweepJ.result]);
  const run=()=>{setMsg('');jobStore.start('backtest',()=>api.backtestRunAsync({bars,spread,commission,slippage,timeframe:tf}))};
  const validate=()=>{setMsg('');jobStore.start('validate',()=>api.backtestValidateAsync({slippage,timeframe:tf}))};
  // One-click efficiency sweep: re-runs the cost-aware backtest at a range of trend-efficiency floors using
  // YOUR editable spread/commission/slippage above, so you can see which floor maximises expectancy on your
  // own data before committing it in Settings → 4. Strategy & Confluence → Trend-efficiency by mode.
  const sweep=()=>{setMsg('');jobStore.start('sweep',()=>api.efficiencySweepAsync({bars,spread,commission,slippage,timeframe:tf}))};
  // One-click research preset: validate on H1 (bigger move per trade ⇒ spread is a far smaller % of risk)
  // and apply the free ForexFactory news link. Research only — it does NOT change live trading on its own.
  const researchPreset=async()=>{setTf('H1');setBars(14000);try{const s:any=await api.settings();const next={...s,dataFeeds:{...(s.dataFeeds||{}),economicCalendarUrl:(s.dataFeeds||{}).economicCalendarUrl||'https://nfs.faireconomy.media/ff_calendar_thisweek.json'}};await api.saveSettings(next);}catch{};setMsg('Research preset set: timeframe H1 + free ForexFactory news link applied. Click “Validate My Edge” to test it on your history. This does NOT change live trading — to TRADE H1 live, set Settings → 5. Trading Defaults → Timeframe = H1 only if Validate says GO.');};
  const optimize=async()=>{setLoading('opt');setMsg('');const r:any=await api.backtestOptimizeWeights({bars:Math.max(bars,5000),spread,commission,apply});setOpt(r);setLoading('');setMsg(r?.ok?(r.message||`Optimizer recommendation: ${r.recommendation}`):(r?.message||'Optimize failed'))};
  const applyVerdicts=async()=>{if(!res?.strategies)return;const r:any=await api.backtestApplyVerdicts({strategies:res.strategies});setMsg(r?.message||'Applied.')};
  const resetW=async()=>{const r:any=await api.backtestWeightsReset();setMsg(r?.message||'Reset to defaults.')};
  const k=res?.overall||{};
  return <div className="analytics-layout solo"><div className="analytics-grid">
    <Card className="span-2"><SectionTitle title="Cost-Aware Backtest & Walk-Forward" right={<Tag color="purple">Replays the real engine</Tag>}/>
      <div style={{display:'flex',gap:14,flexWrap:'wrap',alignItems:'flex-end',marginTop:6}}>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:100}}><span className="tiny muted">Timeframe</span><select className="input" value={tf} onChange={e=>setTf(e.target.value)}><option>M5</option><option>M15</option><option>H1</option><option>H4</option></select></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:110}}><span className="tiny muted">{tf} bars</span><input className="input" type="number" value={bars} onChange={e=>setBars(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:110}}><span className="tiny muted">Spread (USD)</span><input className="input" type="number" step="0.01" value={spread} onChange={e=>setSpread(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Commission (USD)</span><input className="input" type="number" step="0.01" value={commission} onChange={e=>setCommission(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Slippage/fill (USD)</span><input className="input" type="number" step="0.01" value={slippage} onChange={e=>setSlippage(Number(e.target.value))}/></div>
        <button className="gold-button" onClick={run} disabled={runJ.running} style={{height:38}}>{runJ.running?'Running…':'Run Backtest'}</button>
        <button className="gold-button" onClick={validate} disabled={valJ.running} style={{height:38,display:'inline-flex',alignItems:'center',gap:6}} title="Replays the real engine over ~2 years of your MT5 history and gives a GO / CAUTION / NO-GO">{valJ.running?'Validating…':<><Gauge size={15}/> Validate My Edge</>}</button>
        <button className="outline-button" onClick={researchPreset} style={{height:38}} title="Set timeframe to H1 + apply the free news link, then Validate — research only, doesn't change live trading">⚡ Research preset: H1 + news</button>
        <button className="ghost-button" onClick={saveBrokerCosts} style={{height:38}} title="Save these spread/commission/slippage as your broker profile — every future Validate uses them, and the live cost gate uses the same commission">💾 Save as my broker costs</button>
        <button className="outline-button" onClick={sweep} disabled={sweepJ.running} style={{height:38}} title="Re-run the backtest at several trend-efficiency floors using the costs you typed above, and see which floor maximises expectancy on your own data">{sweepJ.running?'Sweeping…':'🧪 Efficiency sweep'}</button>
      </div>
      <p className="tiny muted" style={{marginTop:6}}>“Validate My Edge” replays the engine over ~2 years of your real MT5 history at the selected <strong>timeframe</strong> and returns GO / CAUTION / NO-GO. <strong>Higher timeframe (H1/H4) = bigger move per trade, so the spread is a far smaller % of your risk</strong> — the main lever to flip a cost-dragged edge. The “Research preset” button sets H1 + the free news link to test that here; it does <em>not</em> change live trading (to trade H1 live, set Settings → 5. Trading Defaults → Timeframe). Connect MT5 for a real verdict.</p>
      <div style={{display:'flex',gap:14,flexWrap:'wrap',alignItems:'center',marginTop:12}}>
        <div style={{display:'flex',gap:8,alignItems:'center'}}><span className="tiny muted">Apply if improved</span><ToggleSwitch checked={apply} onChange={setApply}/></div>
        <button className="outline-button" onClick={optimize} disabled={loading==='opt'} style={{height:38}}>{loading==='opt'?'Optimizing…':'Optimize Weights'}</button>
        <button className="ghost-button" onClick={resetW} style={{height:38}}>Reset Weights</button>
      </div>
      <JobBar job={runJ} onStop={()=>jobStore.stop('backtest')} label="Backtest"/>
      <JobBar job={valJ} onStop={()=>jobStore.stop('validate')} label="Validate My Edge"/>
      <JobBar job={sweepJ} onStop={()=>jobStore.stop('sweep')} label="Efficiency sweep"/>
      {msg&&<p className="muted tiny" style={{marginTop:8}}>{msg}</p>}
      {res?.note&&<p className="gold tiny" style={{marginTop:6}}>{res.note}</p>}
      {res?.ok&&<p className="muted tiny" style={{marginTop:6}}>Source: <strong>{res.dataSource}</strong> · <strong>{res.timeframe||tf}</strong> · {res.span} · {res.candles} candles · costs spread {res.costs?.spreadPrice} + comm {res.costs?.commissionPrice} + slip {res.costs?.slippagePrice??0}×2 (set these to your broker's real XAUUSD costs)</p>}
    </Card>
    {sweepRes?.ok&&<Card className="span-2"><SectionTitle title="Trend-efficiency sweep — net of your costs" right={<Tag color="purple">{sweepRes.best!=null?`Best floor ${sweepRes.best}`:'No edge yet'}</Tag>}/>
      <p className="tiny muted">Same engine, same {sweepRes.candles} candles, replayed at each trend-efficiency floor using the costs you typed above (spread {sweepRes.costs?.spreadPrice} + comm {sweepRes.costs?.commissionPrice} + slip {sweepRes.costs?.slippagePrice}×2). The floor with the highest expectancy is your sweet-spot — set it in <strong>Settings → 4 → Trend-efficiency by mode</strong> for the active mode (<strong>{sweepRes.activeMode}</strong>).</p>
      <div style={{overflowX:'auto'}}><DataTable columns={['efficiency','trades','expectancyR','winRate','profitFactor','maxDrawdownR','oos','verdict']}
        rows={(sweepRes.rows||[]).map((r:any)=>({_r:r,efficiency:r.efficiency,trades:r.trades,expectancyR:`${r.expectancyR}R`,winRate:`${r.winRate}%`,profitFactor:r.profitFactor,maxDrawdownR:`${r.maxDrawdownR}R`,oos:`${r.oosConsistencyPct}%`,verdict:r.verdict}))}
        renderCell={(row:any,c:string)=>c==='verdict'?<Tag color={row._r.verdict==='GO'?'green':row._r.verdict==='CAUTION'?'gold':row._r.verdict==='LOW SAMPLE'?'blue':'red'}>{row._r.verdict}</Tag>:c==='efficiency'?<strong className={sweepRes.best===row._r.efficiency?'gold':''}>{row._r.efficiency}{sweepRes.best===row._r.efficiency?' ◀ best':''}</strong>:c==='expectancyR'?<span className={Number(row._r.expectancyR)>=0?'positive':'negative'}>{row.expectancyR}</span>:row[c]}/></div>
      <p className="tiny muted" style={{marginTop:8}}>Source: <strong>{sweepRes.dataSource}</strong> · {sweepRes.timeframe} · {sweepRes.span}</p>
      {sweepRes.note&&<p className="gold tiny" style={{marginTop:6}}>{sweepRes.note}</p>}
    </Card>}
    {val?.ok&&val.validation&&(()=>{const v=val.validation;const go=String(v.decision).startsWith('GO');const cau=v.decision==='CAUTION';const col=go?'green':cau?'gold':'red';return <Card className="span-2"><SectionTitle title="Edge Validation Verdict" right={<Tag color={col as any}>{v.decision}</Tag>}/><p style={{marginTop:6,fontWeight:600}}>{v.headline}</p><div className="top-kpis" style={{marginTop:10}}><MetricCard label="Data" value={v.dataSource==='mt5_history'?'Real MT5':'Synthetic'}/><MetricCard label="Trades" value={v.trades}/><MetricCard label="Expectancy" value={`${v.expectancyR}R`}/><MetricCard label="Profit Factor" value={v.profitFactor}/><MetricCard label="Win Rate" value={`${v.winRatePct}%`}/><MetricCard label="Folds +ve" value={`${v.oosConsistencyPct}%`}/></div><p className="tiny muted" style={{marginTop:8}}>Timeframe: <strong>{v.timeframe||'M15'}</strong> · Span: {v.span||'—'} · Max DD: {v.maxDrawdownR}R</p><ul className="tiny muted" style={{marginTop:8,paddingLeft:18}}>{(v.checklist||[]).map((c:string,i:number)=><li key={i} style={{marginBottom:3}}>{c}</li>)}</ul></Card>})()}
    {res?.ok&&<Card className="span-2"><SectionTitle title="Overall — net of costs" right={res.assessment&&<Tag color={res.assessment.edge==='strong'?'green':res.assessment.edge==='marginal'?'gold':'red'}>{res.assessment.worthLive?'Worth trading':res.assessment.edge==='marginal'?'Refine first':'No edge yet'}</Tag>}/><div className="top-kpis"><MetricCard label="Trades" value={res.totalTrades}/><MetricCard label="Expectancy" value={`${k.expectancyR}R`}/><MetricCard label="Win Rate" value={`${k.winRate}%`}/><MetricCard label="Profit Factor" value={k.profitFactor}/><MetricCard label="Max DD" value={`${k.maxDrawdownR}R`}/><MetricCard label="OOS Consistency" value={`${res.oosConsistencyPct}%`}/></div>{res.assessment&&<p className="muted" style={{marginTop:10}}><strong>Verdict:</strong> {res.assessment.message}</p>}</Card>}
    {res?.ok&&<Card><SectionTitle title="Per-Strategy Edge" right={<button className="ghost-button" onClick={applyVerdicts}>Disable no-edge</button>}/><DataTable columns={['Strategy','trades','expectancyR','profitFactor','winRate','verdict']} rows={res.strategies||[]} renderCell={(r,c)=>c==='verdict'?<Tag color={r.verdict==='KEEP'?'green':r.verdict==='DISABLE'?'red':'gold'}>{r.verdict}</Tag>:c==='Strategy'?r.strategy:c==='winRate'?`${r.winRate}%`:r[c]}/></Card>}
    {res?.ok&&<Card><SectionTitle title="Walk-Forward Folds (out-of-sample)"/><DataTable columns={['fold','trades','expectancyR','winRate','profitFactor']} rows={res.walkForward||[]} renderCell={(r,c)=>c==='winRate'?`${r.winRate}%`:r[c]}/></Card>}
    {opt?.ok&&<Card className="span-2"><SectionTitle title="Confidence Factor Weight Optimization" right={<Tag color={opt.outOfSample?.improved?'green':'gold'}>{opt.recommendation}</Tag>}/>
      <p className="muted tiny">Trained on {opt.trainedOn} trades, validated on {opt.validatedOn}. Out-of-sample score↔outcome correlation: {opt.outOfSample?.before?.scoreOutcomeCorr} → {opt.outOfSample?.after?.scoreOutcomeCorr}. {opt.applied?'Applied & persisted to the live engine.':'Not applied (toggle "Apply if improved").'}</p>
      <DataTable columns={['factor','correlation','weight']} rows={opt.factorContributions||[]} renderCell={(r,c)=>c==='correlation'?<span className={Number(r.correlation)>=0?'positive':'negative'}>{r.correlation}</span>:r[c]}/></Card>}
    {res&&!res.ok&&<Card className="span-2"><p className="muted">{res.message||'Backtest unavailable.'}</p></Card>}
  </div></div>;
}
function StrategyLabTab(){
  const [res,setRes]=useState<any>(null),[loading,setLoading]=useState(false),[msg,setMsg]=useState(''),[installed,setInstalled]=useState<any>(null);
  const labJ=useJob('lab');
  useEffect(()=>{(async()=>{const s:any=await api.labStatus();if(s?.result)setRes(s.result);if(s?.installed)setInstalled(s.installed)})()},[]);
  useEffect(()=>{const r=labJ.result;if(r){setRes(r);if(r.ok===false)setMsg(r.message||'Lab run failed.')}},[labJ.result]);
  const run=()=>{setMsg('');jobStore.start('lab',()=>api.labRunAsync({}))};
  const install=async(id:string,name:string)=>{const r:any=await api.labInstall(id);if(r?.ok){setInstalled(r.installed);const e=r.evidence;setMsg(`✓ Installed ${name}. ${e?`Evidence: ${e.expectancyR}R/trade · PF ${e.profitFactor} · ${e.oosConsistencyPct}% folds positive · ${e.trades} trades.`:''} ${r.thesis||''}`)}else setMsg(r?.message||'Install failed.')};
  const uninstall=async()=>{const r:any=await api.labUninstall();if(r?.ok){setInstalled(null);setMsg(`↩ ${r.message}`)}else setMsg(r?.message||'Uninstall failed.')};
  const genAI=async()=>{setLoading(true);setMsg('');const r:any=await api.labGenerate({});setLoading(false);if(r?.ok){setMsg(`🤖 ${r.message}`);run()}else setMsg(r?.message||'AI generation failed. Configure it in Settings → AI Strategy Generator.')};
  const fetchFeed=async()=>{setLoading(true);setMsg('');const r:any=await api.labFetchFeed();setLoading(false);if(r?.ok){setMsg(`📡 ${r.message}`);run()}else setMsg(r?.message||'Feed fetch failed. Set a URL in Settings → Strategy Lab.')};
  const rec=res?.recommendation; const base=res?.baseline||{};
  const rows=[{name:res?.baseline?.name||'Your current config',...base,_base:true},...(res?.candidates||[])];
  return <div className="analytics-layout solo"><div className="analytics-grid">
    <Card className="span-2"><SectionTitle title="AI Strategy Lab" right={<Tag color="purple">Tests candidate styles on YOUR data</Tag>}/>
      <p className="tiny muted">The agent back- and forward-tests a library of candidate trading STYLES against your own MT5 history and head-to-head with your live config. It only recommends an upgrade that genuinely beats your current setup out-of-sample — and nothing is applied until you click Install. Connect MT5 for a real verdict (otherwise it runs on synthetic data).</p>
      <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap',marginTop:10}}>
        <button className="gold-button" onClick={run} disabled={labJ.running||!!loading} style={{height:38,display:'inline-flex',alignItems:'center',gap:6}}>{labJ.running?'Working…':<><FlaskConical size={15}/> Run Strategy Lab</>}</button>
        <button className="outline-button" onClick={genAI} disabled={labJ.running||!!loading} style={{height:38,display:'inline-flex',alignItems:'center',gap:6}} title="Ask your configured Claude/ChatGPT to propose new candidate styles (Settings → AI Strategy Generator)"><Sparkles size={15}/> Generate with AI</button>
        <button className="outline-button" onClick={fetchFeed} disabled={labJ.running||!!loading} style={{height:38,display:'inline-flex',alignItems:'center',gap:6}} title="Pull candidate profiles from your trusted feed URL (Settings → Strategy Lab)"><Rss size={15}/> Fetch feed</button>
        {installed&&<span className="tiny muted">Installed: <strong>{installed.name}</strong> · competes in your rotation with its own gates (your global strictness is untouched)</span>}
        {installed&&<button className="ghost-button" style={{height:34,display:'inline-flex',alignItems:'center',gap:6}} onClick={uninstall} title="Remove this tuning and restore the strictness you had before installing it"><RotateCcw size={14}/> Uninstall &amp; revert</button>}
      </div>
      {res?.span&&<p className="muted tiny" style={{marginTop:6}}>Source: <strong>{res.dataSource}</strong> · {res.span} · {res.candles} candles</p>}
      <JobBar job={labJ} onStop={()=>jobStore.stop('lab')} label="Strategy Lab"/>
      {msg&&<p className="gold tiny" style={{marginTop:6}}>{msg}</p>}
    </Card>
    {rec&&<Card className="span-2"><SectionTitle title="Recommended upgrade" right={<Tag color="green">Beats your current config</Tag>}/>
      <p style={{fontWeight:600,marginTop:4}}>{rec.name}</p>
      <p className="muted" style={{marginTop:4}}>{rec.why}</p>
      {rec.thesis&&<p className="tiny muted" style={{marginTop:4}}>{rec.thesis}</p>}
      <button className="gold-button" style={{marginTop:8,height:36}} onClick={()=>install(rec.id,rec.name)}>Install {rec.name}</button>
    </Card>}
    {res?.ok&&<Card className="span-2 fullscreen-card"><SectionTitle title="Candidates vs your current config — net of costs"/>
      <div style={{overflowX:'auto'}}><DataTable columns={['name','trades','expectancyR','vsBaseline','profitFactor','winRate','oos','install']} rows={rows.map((r:any)=>({_r:r,name:r.name,trades:r.trades,expectancyR:`${r.expectancyR}R`,vsBaseline:r._base?'—':`${Number(r.expectancyVsBaseline)>=0?'+':''}${r.expectancyVsBaseline}R`,profitFactor:r.profitFactor,winRate:`${r.winRate}%`,oos:`${r.oosConsistencyPct||0}%`,install:''}))}
        renderCell={(row:any,c:string)=>c==='vsBaseline'&&!row._r._base?<span className={Number(row._r.expectancyVsBaseline)>=0?'positive':'negative'}>{row.vsBaseline}</span>:c==='install'?(row._r._base?<Tag color="blue">baseline</Tag>:(installed&&(installed.id===row._r.id||installed.strategyId===`lab-${row._r.id}`)?<span style={{display:'inline-flex',gap:6,alignItems:'center'}}><Tag color="green">✓ installed</Tag><button className="ghost-button" style={{height:28}} onClick={uninstall} title="Remove and restore your previous strictness">Uninstall</button></span>:<button className="ghost-button" style={{height:28}} onClick={()=>install(row._r.id,row._r.name)}>Install</button>)):c==='name'?<span><strong>{row.name}</strong>{row._r.thesis?<><br/><span className="tiny muted">{row._r.thesis}</span></>:null}</span>:row[c]}/></div>
    </Card>}
    {res&&!res.ok&&<Card className="span-2"><p className="muted">{res.message||'Run the lab to test candidate strategies against your history.'}</p></Card>}
  </div></div>;
}

function ExitLabWfoCards(){
  // V13.12 — UI for Phase 1 (Exit Lab) + Phase 2 (real Walk-Forward). The engines shipped in
  // V13.11 as API-only; these cards make them visible without curl.
  const [lab,setLab]=useState<any>(null),[wfo,setWfo]=useState<any>(null),[wfoMsg,setWfoMsg]=useState('');
  const [wfoBars,setWfoBars]=useState(6000),[wfoTrain,setWfoTrain]=useState(2000),[wfoTest,setWfoTest]=useState(500);
  const wfoJ=useJob('walkforward');
  useEffect(()=>{(async()=>{const r:any=await api.exitLab(); setLab(r)})()},[]);
  useEffect(()=>{const r=wfoJ.result;if(r){setWfo(r);if(r.ok===false)setWfoMsg(r.message||'Walk-forward failed.')}},[wfoJ.result]);
  const runWfo=()=>{setWfoMsg('');setWfo(null);jobStore.start('walkforward',()=>api.walkForwardAsync({bars:wfoBars,trainBars:wfoTrain,testBars:wfoTest}))};
  const sweep=(lab?.lossCapSweep)||[];
  return <div className="analytics-grid" style={{marginTop:16}}>
    <Card><SectionTitle title="Exit Lab — the scraps question, answered by data" right={<Tag color={lab?.status==='ok'?'green':lab?.status==='insufficient_data'?'amber':'red'}>{lab?.status==='ok'?'LIVE':lab?.status==='insufficient_data'?`${lab?.instrumented||0}/${lab?.minSample||30} TRADES`:'…'}</Tag>}/>
      <p className="tiny muted">Uses maeR/mfeR recorded on every close: (1) would a hard loss cap have paid, counting the winners it would have killed; (2) how much of the winners' peak the trail actually banks. Refuses to answer below {lab?.minSample||30} instrumented trades — small-sample answers are how bots get overfit.</p>
      {lab?.status==='insufficient_data'&&<p className="tiny" style={{marginTop:8}}>{lab.message}</p>}
      {lab?.status==='ok'&&<>
        <Checklist items={[
          {label:'Loss cap verdict',value:String(lab?.lossCap?.verdict||'—').slice(0,80),type:lab?.lossCap?.recommend?'warning':'success'},
          {label:'Trail giveback',value:String(lab?.trailGiveback?.verdict||'—').slice(0,80),type:(lab?.trailGiveback?.medianBankedFractionOfPeak??1)<0.55?'danger':'success'},
          {label:'Winners banking fraction of peak',value:lab?.trailGiveback?.medianBankedFractionOfPeak!=null?`${Math.round(lab.trailGiveback.medianBankedFractionOfPeak*100)}% of ${lab.trailGiveback.medianPeakR}R`:'—'},
        ]}/>
        {sweep.length>0&&<DataTable columns={['Cap (R)','Losers cut','Saved R','Winners killed','Cost R','Net R']} rows={sweep.map((r:any)=>({'Cap (R)':r.capR,'Losers cut':r.losersCut,'Saved R':r.savedR,'Winners killed':r.winnersKilled,'Cost R':r.killedCostR,'Net R':r.netR}))}/>}
      </>}
    </Card>
    <Card><SectionTitle title="Walk-Forward — does the edge survive unseen data?" right={<Tag color={wfo?.summary?.robust?'green':wfo?'amber':'blue'}>{wfo?wfo?.summary?.verdict?.split(' — ')[0]||'RAN':'NOT RUN'}</Tag>}/>
      <p className="tiny muted">Optimizes on one window, validates on the NEXT unseen window, rolls, and judges ONLY the concatenated out-of-sample line. Fewer than 5 cycles = treated as chance. Replaced the old walk-forward button, which returned random numbers.</p>
      <div style={{display:'flex',gap:10,alignItems:'flex-end',flexWrap:'wrap',marginTop:10}}>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Total bars</span><input className="input" type="number" min={1000} step={500} value={wfoBars} onChange={e=>setWfoBars(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Train window</span><input className="input" type="number" min={200} step={100} value={wfoTrain} onChange={e=>setWfoTrain(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Test window</span><input className="input" type="number" min={100} step={50} value={wfoTest} onChange={e=>setWfoTest(Number(e.target.value))}/></div>
        <button className="outline-button" disabled={wfoJ.running} onClick={runWfo}>{wfoJ.running?'Running…':`Run walk-forward (${wfoBars} bars)`}</button>
      </div>
      <p className="tiny muted" style={{marginTop:6}}>Cycles ≈ (total − train) ÷ test. With {wfoBars}/{wfoTrain}/{wfoTest} → <strong>{Math.max(0,Math.floor((wfoBars-wfoTrain)/Math.max(wfoTest,1)))} cycles</strong> (need ≥5 to escape "treated as chance").</p>
      <JobBar job={wfoJ} onStop={()=>jobStore.stop('walkforward')} label="Walk-forward"/>
      {wfoMsg&&<p className="negative tiny" style={{marginTop:6}}>{wfoMsg}</p>}
      {wfo?.ok&&wfo.summary&&<Checklist items={[
        {label:'Verdict',value:String(wfo.summary.verdict||'').slice(0,70),type:wfo.summary.robust?'success':'danger'},
        {label:'OOS expectancy (R/trade)',value:String(wfo.summary.oosExpectancyR),type:wfo.summary.oosExpectancyR>0?'success':'danger'},
        {label:'Cycles scored / trades',value:`${wfo.summary.cyclesScored} / ${wfo.summary.oosTrades}`},
        {label:'Param stability',value:String(wfo.summary.paramStability)},
      ]}/>}
      {wfo?.ok&&<p className="tiny muted" style={{marginTop:6}}>Data: <strong className={wfo.dataSource==='mt5_history'?'positive':'negative'}>{wfo.dataSource==='mt5_history'?'REAL MT5 history':'SYNTHETIC (connect MT5 for a real verdict)'}</strong>{wfo.timeframe?` · ${wfo.timeframe}`:''}{wfo.span?` · ${wfo.span}`:''}</p>}
      {wfo?.ok&&Array.isArray(wfo.cycles)&&wfo.cycles.length>0&&<div style={{marginTop:10}}>
        <SectionTitle title="Per-cycle out-of-sample results"/>
        <div style={{overflowX:'auto'}}><DataTable columns={['cycle','oosTrades','oosExpectancyR','oosPF','isExpectancyR','drop','params']}
          rows={wfo.cycles.map((c:any,i:number)=>{const oo=c.outOfSample||{},is=c.inSample||{};
            const oe=Number(oo.expectancyR??0),ie=Number(is.expectancyR??0);
            return {cycle:c.cycle??i+1,oosTrades:oo.trades??'—',oosExpectancyR:oo.expectancyR??'—',oosPF:oo.profitFactor??'—',
                    isExpectancyR:is.expectancyR??'—',drop:(is.expectancyR!=null&&oo.expectancyR!=null)?(ie-oe).toFixed(3):'—',
                    params:JSON.stringify(c.chosenParams||{}).slice(0,60)};})}
          renderCell={(r:any,col:string)=>col==='oosExpectancyR'?<span className={Number(r.oosExpectancyR)>=0?'positive':'negative'}>{r.oosExpectancyR}</span>:col==='drop'?<span className={Number(r.drop)>0.15?'negative':'muted'}>{r.drop}</span>:r[col]}/></div>
        <p className="tiny muted" style={{marginTop:6}}><strong>drop</strong> = in-sample minus out-of-sample expectancy. A big positive drop means the optimizer memorised the past (overfit).</p>
        <button className="ghost-button" style={{marginTop:8}} onClick={()=>{
          const rows=wfo.cycles.map((c:any,i:number)=>{const oo=c.outOfSample||{},is=c.inSample||{};
            return [c.cycle??i+1,oo.trades,oo.expectancyR,oo.profitFactor,oo.netR,is.trades,is.expectancyR,is.profitFactor,c.oosOk,JSON.stringify(c.chosenParams||{})];});
          const csv=['cycle,oosTrades,oosExpectancyR,oosProfitFactor,oosNetR,isTrades,isExpectancyR,isProfitFactor,oosOk,chosenParams',...rows.map((r:any[])=>r.map(v=>`"${String(v??'').replace(/"/g,'""')}"`).join(','))].join('\n');
          const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download=`walkforward_${Date.now()}.csv`;a.click();
        }}>Export cycles CSV</button>
      </div>}
      {wfo?.dataSource==='synthetic_demo'&&<p className="tiny muted" style={{marginTop:6}}>MT5 disconnected — synthetic candles, verdict meaningless for live. Connect MT5 and rerun.</p>}
      {wfo&&!wfo.ok&&<p className="tiny" style={{marginTop:6}}>{wfo.message}</p>}
    </Card>
  </div>;
}

function DecisionLogTab(){
  const [items,setItems]=useState<any[]>([]),[counts,setCounts]=useState<any>({}),[cat,setCat]=useState('all'),[loading,setLoading]=useState(false);
  const load=async()=>{setLoading(true);const r:any=await api.journalDecisions(cat,300);setItems(r?.items||[]);setCounts(r?.counts||{});setLoading(false)};
  usePoll(load,5000,[cat]);
  const clear=async()=>{await api.journalDecisionsClear();load()};
  // V13.10: missed_pump rows existed in the API but had no chip, no badge, and were mapped to a
  // phantom "Closed #" with the blocking reason dropped entirely. All three fixed below.
  const cats:[string,string][]=[['all','All'],['entry','Entries'],['management','Management'],['close','Closes'],['missed_pump','Missed pumps']];
  const fmtTime=(e:any)=>String(e.ts||'').replace('T',' ').replace('Z',' UTC');
  const badge=(c:string)=>c==='entry'?<Tag color="blue">entry</Tag>:c==='management'?<Tag color="purple">mgmt</Tag>:c==='missed_pump'?<Tag color="red">missed</Tag>:<Tag color="gold">close</Tag>;
  return <div className="analytics-layout solo"><div className="analytics-grid">
    <Card className="span-2"><SectionTitle title="Decision & Management Journal" right={<Tag color="green">WHY it traded — or didn't</Tag>}/>
      <p className="tiny muted">Every entry decision (taken AND skipped, with the exact confidence + blocking reason), every management action (break-even, trail, recovery-room, fast-fail, partials), and every close outcome — persisted across restarts. Identical "waiting" ticks are collapsed; a new row appears whenever the bot's decision or reason CHANGES.</p>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',alignItems:'center',marginTop:10}}>
        {cats.map(([key,label])=><button key={key} className={cat===key?'gold-button':'ghost-button'} style={{height:32}} onClick={()=>setCat(key)}>{label}{counts[key]!=null&&key!=='all'?` (${counts[key]})`:''}</button>)}
        <span style={{flex:1}}/>
        <button className="ghost-button" style={{height:32}} onClick={load}>{loading?'…':'Refresh'}</button>
        <button className="ghost-button" style={{height:32}} onClick={clear}>Clear</button>
      </div>
    </Card>
    <Card className="span-2"><DataTable columns={['time','type','what','side','conf','quality','detail','outcome']} rows={items.map((e:any)=>({
      _e:e, time:fmtTime(e), type:e.category,
      what:e.category==='entry'?e.decision:e.category==='management'?e.title:e.category==='missed_pump'?`MISSED ${e.side||''} ${Number(e.displacementAtr||0).toFixed(2)} ATR`:`Closed #${e.ticket||''}`,
      side:e.side||'', conf:e.confidence!=null?`${e.confidence}%`:'', quality:e.quality||'',
      detail:e.category==='entry'?((e.blocks&&e.blocks[0])||e.reason||''):e.category==='missed_pump'?String(e.blockedBy||''):e.detail||'',
      outcome:e.category==='close'?`${e.outcome} ${Number(e.pnlUsd)>=0?'+':''}${e.pnlUsd}`:e.category==='missed_pump'?`@ ${Number(e.price||0).toFixed(2)}`:(e.opened?'OPENED':''),
    }))} renderCell={(r:any,c:string)=>c==='type'?badge(r._e.category):c==='outcome'&&r._e.category==='close'?<span className={Number(r._e.pnlUsd)>=0?'positive':'negative'}>{r.outcome}</span>:c==='what'&&r._e.category==='entry'?<span className={r._e.decision==='TAKE_TRADE'?'positive':'muted'}>{r.what}</span>:r[c]}/>
      {!items.length&&<p className="muted" style={{marginTop:10}}>No decisions logged yet. With Auto-Trading ON, the bot records a row each time its decision or reason changes.</p>}
    </Card>
  </div></div>;
}
function AnalyticsOverview({data,k,currency,report,getReport}:{data:any;k:any;currency:string;report:any;getReport:()=>void}){const sample=Number(k.totalTrades||0);const bestStrategy=(data.topStrategies||[])[0];const bestSession=(data.sessions||[])[0];return <div className="analytics-layout"><div className="analytics-grid"><Card className="span-2"><SectionTitle title="Equity Curve" right={<Tag color="purple">Bot only</Tag>}/><EquityCurve data={data.equityCurve||[]} height={270}/><div className="chart-summary"><span>Starting Balance <strong>{money(data.startingBalance,currency)}</strong></span><span>Ending Balance <strong>{money(data.endingBalance,currency)}</strong></span><span>Net PnL <strong className={Number(k.netProfit)>=0?'positive':'negative'}>{money(k.netProfit,currency)}</strong></span><span>Return <strong>{k.returnPct||0}%</strong></span></div></Card><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Net PnL','Win Rate','Trades']} rows={data.topStrategies||[]} /></Card><Card className="span-full"><SectionTitle title="Returns Calendar" right={<Tag color="purple">Click a day for AI insight</Tag>}/><ReturnsCalendar data={data.returnsCalendar||[]} currency={currency}/></Card><Card><SectionTitle title="Win Rate Breakdown"/><Donut value={Number(k.winRate||0)}/><Checklist items={[{label:'Buy Trades',value:`${data.buyWinRate||0}%`},{label:'Sell Trades',value:`${data.sellWinRate||0}%`},{label:'Break-even',value:`${data.breakEvenRate||0}%`},{label:'Loss Trades',value:`${data.lossRate||0}%`}]}/></Card><Card><SectionTitle title="Session Performance"/><DataTable columns={['Session','Net PnL','Win Rate','Trades','Expectancy']} rows={data.sessions||[]} /></Card><Card><SectionTitle title="Market Heatmap PnL"/><BarDistribution data={data.marketHeatmap||[]}/></Card><Card><SectionTitle title="Expectancy vs Win Rate"/><ScatterPerformance data={data.expectancyScatter||[]}/></Card><Card><SectionTitle title="Drawdown Curve"/><DrawdownChart data={data.drawdown||[]}/></Card><Card><SectionTitle title="Execution Quality"/><BarDistribution data={data.executionQuality||[]}/><Checklist items={[{label:'Avg Slippage',value:String(data.avgSlippage??'—')},{label:'Fill Quality',value:data.fillQuality||'Waiting'}]}/></Card><Card><SectionTitle title="Confidence vs Result"/><ScatterPerformance data={data.confidenceResult||[]}/></Card></div><div className="right-stack side-panel-sticky"><Card><SectionTitle title="Analytics Insights"/><Checklist items={[{label:'Evidence maturity',value:sample>=30?`${sample} trades — reviewable`:`${sample} trades — insufficient sample`},{label:'Best Performing Strategy',value:sample&&bestStrategy?.Strategy?bestStrategy.Strategy:'Not established'},{label:'Best Observed Session',value:sample&&bestSession?.Session?bestSession.Session:'Not established'},{label:'Measured Max Drawdown',value:k.maxDrawdown==null?'—':String(k.maxDrawdown)},{label:'Inference status',value:sample>=30?'Derived from bot-only history':'No performance claim'}]}/><div className="report-action"><p className="muted">Generate a complete bot-only report from real MT5 trade history.</p><button className="outline-button full" onClick={getReport}><FileText size={14}/> View Full Report</button></div>{report&&<pre className="code-box">{JSON.stringify(report,null,2)}</pre>}</Card><Card><SectionTitle title="Evidence-Based Takeaways"/><Checklist items={[{label:'Sample size',value:String(sample)},{label:'Observed strategy leader',value:bestStrategy?.Strategy||'Not established'},{label:'Observed session leader',value:bestSession?.Session||'Not established'},{label:'Next action',value:sample>=30?'Review out-of-sample stability':'Collect more bot-only trades'}]}/></Card></div></div>}
