import { useEffect, useMemo, useState } from 'react';
import { Download, FileText, RefreshCcw } from 'lucide-react';
import { Card, Checklist, DataTable, MetricCard, PageHeader, SectionTitle, Tag, ToggleSwitch } from '../components/ui';
import { BarDistribution, Donut, DrawdownChart, EquityCurve, ReturnsHeatmap, ScatterPerformance } from '../components/Charts';
import { api, downloadExport } from '../lib/api';
const money=(v:any,c='')=>`${c?c+' ':''}${Number(v||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
export default function Analytics(){
  const [data,setData]=useState<any>({kpis:{},history:[]}),[report,setReport]=useState<any|null>(null),[tab,setTab]=useState('Overview');
  const [dateFrom,setDateFrom]=useState(''),[dateTo,setDateTo]=useState(''),[account,setAccount]=useState('All Accounts');
  const load=async()=>setData(await api.analytics(dateFrom,dateTo));
  useEffect(()=>{load();const id=setInterval(load,10000);return()=>clearInterval(id)},[dateFrom,dateTo]);
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
    {tab==='Trades'&&<Card><SectionTitle title="Bot-only trade sample"/><DataTable columns={['symbol','direction','pnlUsd','closeTime','reason']} rows={history}/></Card>}
    {tab==='Strategies'&&<div className="analytics-layout"><div className="analytics-grid"><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Net PnL','Win Rate','Trades']} rows={topRows}/></Card><Card><SectionTitle title="Expectancy vs Win Rate"/><ScatterPerformance data={data.expectancyScatter||[]}/></Card></div></div>}
    {tab==='Risk'&&<div className="analytics-layout"><div className="analytics-grid"><Card><SectionTitle title="Win Rate Breakdown"/><Donut value={Number(k.winRate||0)}/></Card><Card><SectionTitle title="Drawdown Curve"/><DrawdownChart data={data.drawdown||[]}/></Card><Card><SectionTitle title="Confidence vs Result"/><ScatterPerformance data={data.confidenceResult||[]}/></Card></div></div>}
    {tab==='Reports'&&<Card><SectionTitle title="Full Report" right={<button className="outline-button" onClick={getReport}><FileText size={14}/> View Full Report</button>}/>{report?<pre className="code-box">{JSON.stringify(report,null,2)}</pre>:<p className="muted">Press View Full Report to generate the backend/API report information.</p>}</Card>}
    {tab==='Decisions'&&<DecisionLogTab/>}
    {tab==='Strategy Lab'&&<StrategyLabTab/>}
    {tab==='Backtest'&&<BacktestTab/>}
    {tab==='Custom'&&<Card><SectionTitle title="Custom Analytics Builder"/><p className="muted">Custom filters use the selected date range and bot-only MT5 trade history. More report templates can be added here.</p></Card>}
  </div>
}

function BacktestTab(){
  const [res,setRes]=useState<any>(null),[opt,setOpt]=useState<any>(null),[val,setVal]=useState<any>(null),[loading,setLoading]=useState(''),[msg,setMsg]=useState('');
  const [bars,setBars]=useState(4000),[spread,setSpread]=useState(0.20),[commission,setCommission]=useState(0.05),[apply,setApply]=useState(false);
  const run=async()=>{setLoading('run');setMsg('');const r:any=await api.backtestRun({bars,spread,commission});setRes(r);setLoading('');if(!r?.ok)setMsg(r?.message||'Backtest failed.')};
  const validate=async()=>{setLoading('val');setMsg('');const r:any=await api.backtestValidate({});setVal(r);if(r?.ok)setRes(r);setLoading('');if(!r?.ok)setMsg(r?.message||'Validation failed.')};
  const optimize=async()=>{setLoading('opt');setMsg('');const r:any=await api.backtestOptimizeWeights({bars:Math.max(bars,5000),spread,commission,apply});setOpt(r);setLoading('');setMsg(r?.ok?(r.message||`Optimizer recommendation: ${r.recommendation}`):(r?.message||'Optimize failed'))};
  const applyVerdicts=async()=>{if(!res?.strategies)return;const r:any=await api.backtestApplyVerdicts({strategies:res.strategies});setMsg(r?.message||'Applied.')};
  const resetW=async()=>{const r:any=await api.backtestWeightsReset();setMsg(r?.message||'Reset to defaults.')};
  const k=res?.overall||{};
  return <div className="analytics-layout"><div className="analytics-grid">
    <Card className="span-2"><SectionTitle title="Cost-Aware Backtest & Walk-Forward" right={<Tag color="purple">Replays the real engine</Tag>}/>
      <div style={{display:'flex',gap:14,flexWrap:'wrap',alignItems:'flex-end',marginTop:6}}>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">M15 bars</span><input className="input" type="number" value={bars} onChange={e=>setBars(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:120}}><span className="tiny muted">Spread (USD)</span><input className="input" type="number" step="0.01" value={spread} onChange={e=>setSpread(Number(e.target.value))}/></div>
        <div style={{display:'flex',flexDirection:'column',gap:4,width:130}}><span className="tiny muted">Commission (USD)</span><input className="input" type="number" step="0.01" value={commission} onChange={e=>setCommission(Number(e.target.value))}/></div>
        <button className="gold-button" onClick={run} disabled={loading==='run'} style={{height:38}}>{loading==='run'?'Running…':'Run Backtest'}</button>
        <button className="gold-button" onClick={validate} disabled={loading==='val'} style={{height:38}} title="Replays the real engine over ~2 years of your MT5 history and gives a GO / CAUTION / NO-GO">{loading==='val'?'Validating…':'🎯 Validate My Edge'}</button>
      </div>
      <p className="tiny muted" style={{marginTop:6}}>“Validate My Edge” pulls up to ~2 years of your real MT5 M15 history and returns a plain-English GO / CAUTION / NO-GO. Scroll your MT5 chart far back first so the terminal caches the history. Connect MT5 for a real verdict (otherwise it runs on synthetic data).</p>
      <div style={{display:'flex',gap:14,flexWrap:'wrap',alignItems:'center',marginTop:12}}>
        <div style={{display:'flex',gap:8,alignItems:'center'}}><span className="tiny muted">Apply if improved</span><ToggleSwitch checked={apply} onChange={setApply}/></div>
        <button className="outline-button" onClick={optimize} disabled={loading==='opt'} style={{height:38}}>{loading==='opt'?'Optimizing…':'Optimize Weights'}</button>
        <button className="ghost-button" onClick={resetW} style={{height:38}}>Reset Weights</button>
      </div>
      {msg&&<p className="muted tiny" style={{marginTop:8}}>{msg}</p>}
      {res?.note&&<p className="gold tiny" style={{marginTop:6}}>{res.note}</p>}
      {res?.ok&&<p className="muted tiny" style={{marginTop:6}}>Source: <strong>{res.dataSource}</strong> · {res.span} · {res.candles} candles · costs spread {res.costs?.spreadPrice} + comm {res.costs?.commissionPrice} (set these to your broker's real XAUUSD costs)</p>}
    </Card>
    {val?.ok&&val.validation&&(()=>{const v=val.validation;const go=String(v.decision).startsWith('GO');const cau=v.decision==='CAUTION';const col=go?'green':cau?'gold':'red';return <Card className="span-2"><SectionTitle title="Edge Validation Verdict" right={<Tag color={col as any}>{v.decision}</Tag>}/><p style={{marginTop:6,fontWeight:600}}>{v.headline}</p><div className="top-kpis" style={{marginTop:10}}><MetricCard label="Data" value={v.dataSource==='mt5_history'?'Real MT5':'Synthetic'}/><MetricCard label="Trades" value={v.trades}/><MetricCard label="Expectancy" value={`${v.expectancyR}R`}/><MetricCard label="Profit Factor" value={v.profitFactor}/><MetricCard label="Win Rate" value={`${v.winRatePct}%`}/><MetricCard label="Folds +ve" value={`${v.oosConsistencyPct}%`}/></div><p className="tiny muted" style={{marginTop:8}}>Span: {v.span||'—'} · Max DD: {v.maxDrawdownR}R</p><ul className="tiny muted" style={{marginTop:8,paddingLeft:18}}>{(v.checklist||[]).map((c:string,i:number)=><li key={i} style={{marginBottom:3}}>{c}</li>)}</ul></Card>})()}
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
  useEffect(()=>{(async()=>{const s:any=await api.labStatus();if(s?.result)setRes(s.result);if(s?.installed)setInstalled(s.installed)})()},[]);
  const run=async()=>{setLoading(true);setMsg('');const r:any=await api.labRun({});setRes(r);setLoading(false);if(!r?.ok)setMsg(r?.message||'Lab run failed.')};
  const install=async(id:string,name:string)=>{const r:any=await api.labInstall(id);if(r?.ok){setInstalled(r.installed);const e=r.evidence;setMsg(`✓ Installed ${name}. ${e?`Evidence: ${e.expectancyR}R/trade · PF ${e.profitFactor} · ${e.oosConsistencyPct}% folds positive · ${e.trades} trades.`:''} ${r.thesis||''}`)}else setMsg(r?.message||'Install failed.')};
  const rec=res?.recommendation; const base=res?.baseline||{};
  const rows=[{name:res?.baseline?.name||'Your current config',...base,_base:true},...(res?.candidates||[])];
  return <div className="analytics-layout"><div className="analytics-grid">
    <Card className="span-2"><SectionTitle title="AI Strategy Lab" right={<Tag color="purple">Tests candidate styles on YOUR data</Tag>}/>
      <p className="tiny muted">The agent back- and forward-tests a library of candidate trading STYLES against your own MT5 history and head-to-head with your live config. It only recommends an upgrade that genuinely beats your current setup out-of-sample — and nothing is applied until you click Install. Connect MT5 for a real verdict (otherwise it runs on synthetic data).</p>
      <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap',marginTop:10}}>
        <button className="gold-button" onClick={run} disabled={loading} style={{height:38}}>{loading?'Testing all candidates…':'🧠 Run Strategy Lab'}</button>
        {installed&&<span className="tiny muted">Installed: <strong>{installed.name}</strong></span>}
      </div>
      {res?.span&&<p className="muted tiny" style={{marginTop:6}}>Source: <strong>{res.dataSource}</strong> · {res.span} · {res.candles} candles</p>}
      {msg&&<p className="gold tiny" style={{marginTop:6}}>{msg}</p>}
    </Card>
    {rec&&<Card className="span-2"><SectionTitle title="Recommended upgrade" right={<Tag color="green">Beats your current config</Tag>}/>
      <p style={{fontWeight:600,marginTop:4}}>{rec.name}</p>
      <p className="muted" style={{marginTop:4}}>{rec.why}</p>
      {rec.thesis&&<p className="tiny muted" style={{marginTop:4}}>{rec.thesis}</p>}
      <button className="gold-button" style={{marginTop:8,height:36}} onClick={()=>install(rec.id,rec.name)}>Install {rec.name}</button>
    </Card>}
    {res?.ok&&<Card className="span-2"><SectionTitle title="Candidates vs your current config — net of costs"/>
      <DataTable columns={['name','trades','expectancyR','vsBaseline','profitFactor','winRate','oos','install']} rows={rows.map((r:any)=>({_r:r,name:r.name,trades:r.trades,expectancyR:`${r.expectancyR}R`,vsBaseline:r._base?'—':`${Number(r.expectancyVsBaseline)>=0?'+':''}${r.expectancyVsBaseline}R`,profitFactor:r.profitFactor,winRate:`${r.winRate}%`,oos:`${r.oosConsistencyPct||0}%`,install:''}))}
        renderCell={(row:any,c:string)=>c==='vsBaseline'&&!row._r._base?<span className={Number(row._r.expectancyVsBaseline)>=0?'positive':'negative'}>{row.vsBaseline}</span>:c==='install'?(row._r._base?<Tag color="blue">current</Tag>:<button className="ghost-button" style={{height:28}} onClick={()=>install(row._r.id,row._r.name)}>Install</button>):c==='name'?<span><strong>{row.name}</strong>{row._r.thesis?<><br/><span className="tiny muted">{row._r.thesis}</span></>:null}</span>:row[c]}/>
    </Card>}
    {res&&!res.ok&&<Card className="span-2"><p className="muted">{res.message||'Run the lab to test candidate strategies against your history.'}</p></Card>}
  </div></div>;
}
function DecisionLogTab(){
  const [items,setItems]=useState<any[]>([]),[counts,setCounts]=useState<any>({}),[cat,setCat]=useState('all'),[loading,setLoading]=useState(false);
  const load=async()=>{setLoading(true);const r:any=await api.journalDecisions(cat,300);setItems(r?.items||[]);setCounts(r?.counts||{});setLoading(false)};
  useEffect(()=>{load();const id=setInterval(load,5000);return()=>clearInterval(id)},[cat]);
  const clear=async()=>{await api.journalDecisionsClear();load()};
  const cats:[string,string][]=[['all','All'],['entry','Entries'],['management','Management'],['close','Closes']];
  const fmtTime=(e:any)=>String(e.ts||'').replace('T',' ').replace('Z',' UTC');
  const badge=(c:string)=>c==='entry'?<Tag color="blue">entry</Tag>:c==='management'?<Tag color="purple">mgmt</Tag>:<Tag color="gold">close</Tag>;
  return <div className="analytics-layout"><div className="analytics-grid">
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
      what:e.category==='entry'?e.decision:e.category==='management'?e.title:`Closed #${e.ticket||''}`,
      side:e.side||'', conf:e.confidence!=null?`${e.confidence}%`:'', quality:e.quality||'',
      detail:e.category==='entry'?((e.blocks&&e.blocks[0])||e.reason||''):e.detail||'',
      outcome:e.category==='close'?`${e.outcome} ${Number(e.pnlUsd)>=0?'+':''}${e.pnlUsd}`:(e.opened?'OPENED':''),
    }))} renderCell={(r:any,c:string)=>c==='type'?badge(r._e.category):c==='outcome'&&r._e.category==='close'?<span className={Number(r._e.pnlUsd)>=0?'positive':'negative'}>{r.outcome}</span>:c==='what'&&r._e.category==='entry'?<span className={r._e.decision==='TAKE_TRADE'?'positive':'muted'}>{r.what}</span>:r[c]}/>
      {!items.length&&<p className="muted" style={{marginTop:10}}>No decisions logged yet. With Auto-Trading ON, the bot records a row each time its decision or reason changes.</p>}
    </Card>
  </div></div>;
}
function AnalyticsOverview({data,k,currency,report,getReport}:{data:any;k:any;currency:string;report:any;getReport:()=>void}){return <div className="analytics-layout"><div className="analytics-grid"><Card className="span-2"><SectionTitle title="Equity Curve" right={<Tag color="purple">Bot only</Tag>}/><EquityCurve data={data.equityCurve||[]} height={270}/><div className="chart-summary"><span>Starting Balance <strong>{money(data.startingBalance,currency)}</strong></span><span>Ending Balance <strong>{money(data.endingBalance,currency)}</strong></span><span>Net PnL <strong className="positive">{money(k.netProfit,currency)}</strong></span><span>Return <strong>{k.returnPct||0}%</strong></span></div></Card><Card><SectionTitle title="Returns"/><ReturnsHeatmap data={data.returns||[]}/></Card><Card><SectionTitle title="Top Strategies"/><DataTable columns={['Strategy','Net PnL','Win Rate','Trades']} rows={data.topStrategies||[]} /></Card><Card><SectionTitle title="Win Rate Breakdown"/><Donut value={Number(k.winRate||0)}/><Checklist items={[{label:'Buy Trades',value:`${data.buyWinRate||0}%`},{label:'Sell Trades',value:`${data.sellWinRate||0}%`},{label:'Break-even',value:`${data.breakEvenRate||0}%`},{label:'Loss Trades',value:`${data.lossRate||0}%`}]}/></Card><Card><SectionTitle title="Session Performance"/><DataTable columns={['Session','Net PnL','Win Rate','Trades','Expectancy']} rows={data.sessions||[]} /></Card><Card><SectionTitle title="Market Heatmap PnL"/><BarDistribution data={data.marketHeatmap||[]}/></Card><Card><SectionTitle title="Expectancy vs Win Rate"/><ScatterPerformance data={data.expectancyScatter||[]}/></Card><Card><SectionTitle title="Drawdown Curve"/><DrawdownChart data={data.drawdown||[]}/></Card><Card><SectionTitle title="Execution Quality"/><BarDistribution data={data.executionQuality||[]}/><Checklist items={[{label:'Avg Slippage',value:String(data.avgSlippage??'—')},{label:'Fill Quality',value:data.fillQuality||'Waiting'}]}/></Card><Card><SectionTitle title="Confidence vs Result"/><ScatterPerformance data={data.confidenceResult||[]}/></Card></div><div className="right-stack side-panel-sticky"><Card><SectionTitle title="Analytics Insights"/><Checklist items={[{label:'Strong performance across the board',value:k.totalTrades?'Detected':'Waiting'},{label:'Best Performing Strategy',value:(data.topStrategies||[])[0]?.Strategy||'—'},{label:'Optimal Trading Session',value:(data.sessions||[])[0]?.Session||'—'},{label:'Risk Management',value:'Drawdown monitored',type:'success'},{label:'Opportunities',value:'Needs more bot-only sample'}]}/><div className="report-action"><p className="muted">Generate a complete bot-only report from real MT5 trade history.</p><button className="outline-button full" onClick={getReport}><FileText size={14}/> View Full Report</button></div>{report&&<pre className="code-box">{JSON.stringify(report,null,2)}</pre>}</Card><Card><SectionTitle title="Key Takeaways"/><Checklist items={[{label:'Focus on London session setups',value:'Review'},{label:'Leverage high-confidence signals >70%',value:'Active'},{label:'Maintain risk settings',value:'Current'},{label:'Scale winners only with prove/confirm/press pyramid',value:'Protected'}]}/></Card></div></div>}
