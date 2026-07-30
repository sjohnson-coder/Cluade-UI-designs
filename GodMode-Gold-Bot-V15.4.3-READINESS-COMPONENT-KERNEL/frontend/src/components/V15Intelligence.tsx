import { useEffect, useState } from 'react';
import { BrainCircuit, RefreshCcw, ShieldCheck, Zap } from 'lucide-react';
import { Card, Checklist, MetricCard, ProgressBar, SectionTitle, Tag } from './ui';
import { api } from '../lib/api';
import { usePoll } from '../lib/usePoll';

const pct=(value:any)=>`${Math.round(Number(value||0)*100)}%`;

export function V15Intelligence(){
  const [data,setData]=useState<any>({version:'15.0.5',health:{score:0,ok:false,errors:[]}});
  const [busy,setBusy]=useState(false);
  const load=async()=>{setBusy(true); try{setData(await api.v15Overview())}finally{setBusy(false)}};
  usePoll(load,10000);
  const forecast=data.forecast||{}; const probabilities=forecast.probabilities||{}; const regime=data.regime||{}; const exit=data.exit||{}; const burst=data.burst||{};
  const gateItems=(burst.gates||[]).map((g:any)=>({label:g.name,value:g.passed?'PASS':'BLOCK',type:g.passed?'success':'danger'}));
  return <Card style={{marginTop:16}}>
    <SectionTitle icon={<BrainCircuit size={17}/>} title="V15 Enterprise Intelligence" right={<span className="button-wrap"><Tag color={data.health?.ok?'green':'gold'}>{Math.round(Number(data.health?.score||0))}% health</Tag><button className="ghost-button" onClick={load} disabled={busy}><RefreshCcw size={13}/>{busy?' Loading':' Refresh'}</button></span>}/>
    <p className="muted compact">Regime-aware calibrated forecasting, broker intelligence, deterministic exits, Burst gate tracing, missed-opportunity learning, free macro/news context and governed model promotion.</p>
    <div className="grid grid-4" style={{marginTop:12}}>
      <MetricCard label="Regime" value={regime.primary||'Ready'}/>
      <MetricCard label="Continuation" value={probabilities.continuation!=null?pct(probabilities.continuation):'—'}/>
      <MetricCard label="Recovery" value={probabilities.recovery!=null?pct(probabilities.recovery):'—'}/>
      <MetricCard label="TP before SL" value={probabilities.tp_before_sl!=null?pct(probabilities.tp_before_sl):'—'}/>
      <MetricCard label="Fast-fail risk" value={probabilities.fast_fail!=null?pct(probabilities.fast_fail):'—'}/>
      <MetricCard label="Expected MFE" value={forecast.expected_mfe_r!=null?`${Number(forecast.expected_mfe_r).toFixed(2)}R`:'—'}/>
      <MetricCard label="Expected MAE" value={forecast.expected_mae_r!=null?`${Number(forecast.expected_mae_r).toFixed(2)}R`:'—'}/>
      <MetricCard label="Uncertainty" value={forecast.uncertainty!=null?pct(forecast.uncertainty):'—'}/>
    </div>
    {/* V15.0.8 — this row previously read "Calibrated confidence" unconditionally, while
        forecast.is_calibrated was false. It presented a hand-tuned heuristic score to the
        operator as a measured win rate, which is exactly how a "92% confidence" setup could
        lose without the display ever appearing wrong. The label now states which quantity is
        being shown and whether it is actually calibrated. */}
    {forecast.win_probability!=null||forecast.confidence!=null?<div className="factor-row" style={{marginTop:12}}>
      <span>{forecast.is_calibrated?'Win probability (calibrated)':'Win probability (uncalibrated estimate)'}</span>
      <ProgressBar value={Number(forecast.win_probability ?? forecast.confidence)*100}/>
      <strong>{pct(forecast.win_probability ?? forecast.confidence)}</strong>
    </div>:null}
    {forecast.data_confidence!=null?<div className="factor-row">
      <span>Input-data confidence <em className="tiny muted">(feed quality, not a win rate)</em></span>
      <ProgressBar value={Number(forecast.data_confidence)*100}/>
      <strong>{pct(forecast.data_confidence)}</strong>
    </div>:null}
    {forecast.is_calibrated===false?<p className="tiny muted" style={{marginTop:6}}>
      <strong>Uncalibrated.</strong> These probabilities come from hand-tuned coefficients, not
      from measured outcomes. {forecast.calibration_samples!=null?`${forecast.calibration_samples}/200`:'Fewer than 200'} labelled
      outcomes recorded. Until that threshold is reached the model is wired veto-only — it can
      block a setup, never authorise one — and these numbers should be read as a sanity filter
      rather than a measured edge.
    </p>:null}
    <div className="grid grid-2" style={{marginTop:12}}>
      <Card soft><SectionTitle icon={<ShieldCheck size={15}/>} title="Deterministic Exit" right={<Tag color={exit.action==='close'||exit.action==='fast_fail'?'red':exit.action==='hold'?'gold':'green'}>{exit.action||'Ready'}</Tag>}/><p className="tiny muted">{exit.reason||'Waiting for a live position snapshot.'}</p>{exit.recommended_stop_r!=null?<p className="tiny">Recommended floor: <strong>{Number(exit.recommended_stop_r).toFixed(2)}R</strong></p>:null}</Card>
      <Card soft><SectionTitle icon={<Zap size={15}/>} title="Burst Intelligence" right={<Tag color={burst.allowed?'green':'gold'}>{burst.allowed?'ALLOWED':'BLOCKED'}</Tag>}/>{gateItems.length?<Checklist items={gateItems}/>:<p className="tiny muted">Burst gate trace appears after the first V15 evaluation.</p>}</Card>
    </div>
    {data.explanation?.summary?<div className="ai-insight" style={{marginTop:12}}><BrainCircuit size={14}/><span>{data.explanation.summary}</span></div>:null}
  </Card>
}
