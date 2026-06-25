
import type { ReactNode } from 'react';
import { Activity, BrainCircuit, Gauge, Layers3, LockKeyhole, ShieldCheck, Target } from 'lucide-react';
import { Card, Checklist, ConfidenceRing, DataTable, ProgressBar, SectionTitle, Tag } from './ui';

type Tone = 'green' | 'gold' | 'purple' | 'red' | 'blue';
const statusColor = (status: string) => status.includes('KILL') || status.includes('BLOCK') ? 'red' : status.includes('WAIT') || status.includes('FALLBACK') || status.includes('READY') ? 'gold' : status.includes('PYRAMID') ? 'purple' : 'green';
function toneClass(tone: Tone) { return tone === 'red' ? 'negative' : tone === 'gold' ? 'gold' : 'positive'; }

function DashboardMiniCard({ label, value, tone = 'green' }: { label: string; value: string; tone?: Tone }) {
  return <Card soft>
    <div className="tiny muted">{label}</div>
    <div style={{ fontSize: 17, fontWeight: 900, marginTop: 4 }} className={toneClass(tone)}>{value}</div>
  </Card>
}
function DashboardKpiGrid({ children }: { children: ReactNode }) { return <div className="reference-kpi-strip">{children}</div> }

export function SuperIntelligencePanel() {
  const modules = [
    ['Deterministic Decision Engine','ACTIVE','92%'],['11-Strategy Arsenal Router','ACTIVE','91%'],['Trader Question Gate','ACTIVE','94%'],['Economic Calendar + News Blackout','ACTIVE','100%'],['DXY / US10Y Macro Context','LIVE / FALLBACK','86%'],['Gold Volatility Regime','ACTIVE','88%'],['Performance Memory','ACTIVE','83%'],['Probability Calibration','ACTIVE','78%'],['Broker Execution Scoring','EXCELLENT','96%'],['Overfitting Guard','PASS','92%'],['Emergency Kill Switch','READY','100%'],['Protected Lot-Scaling Pyramid','ARMED','94%'],
  ];
  return <Card>
    <SectionTitle icon={<BrainCircuit size={16}/>} title="GodMode Super Intelligence Core" right={<Tag color="purple">Deterministic + Auditable</Tag>} />
    <div className="grid" style={{ gridTemplateColumns:'112px 1fr', gap:12, alignItems:'center', marginBottom: 12 }}>
      <ConfidenceRing value={91} label="GodMode IQ" size={94} />
      <div>
        <div className="tiny gold" style={{ fontWeight: 900, letterSpacing: '.1em', textTransform: 'uppercase' }}>AI Command Layer</div>
        <h3 style={{ margin: '4px 0 5px', fontSize: 17, letterSpacing:'-.02em' }}>25-year gold-trader logic with deterministic decision control</h3>
        <p className="card-sub">Routes strategies, blocks weak conditions, reads macro/news pressure, manages TP1–TP4, trails, pushes targets, controls pyramiding, and protects capital.</p>
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>{['TAKE/SKIP','SNIPER MODE','NO-TRADE','TP PUSH','BE','TRAILING','PYRAMIDING','KILL SWITCH'].map(x => <Tag key={x} color={x==='PYRAMIDING'?'purple':x==='KILL SWITCH'?'red':'green'}>{x}</Tag>)}</div>
      </div>
    </div>
    <DataTable columns={['Module','Status','Score']} rows={modules.map(m => ({ Module:m[0], Status:m[1], Score:m[2] }))} renderCell={(r,c)=> c==='Status' ? <Tag color={statusColor(String(r[c])) as any}>{r[c]}</Tag> : c==='Score' ? <span className="positive">{r[c]}</span> : r[c]} />
  </Card>
}

export function TraderQuestionGate() {
  return <Card>
    <SectionTitle icon={<ShieldCheck size={16}/>} title="25-Year Gold Trader Question Gate" right={<Tag color="green">Mandatory Before Entry</Tag>} />
    <DashboardKpiGrid><DashboardMiniCard label="Market clean" value="YES"/><DashboardMiniCard label="Liquidity swept" value="YES"/><DashboardMiniCard label="Move timing" value="EARLY" tone="blue"/><DashboardMiniCard label="News danger" value="NO"/></DashboardKpiGrid>
    <Checklist items={[{label:'Is the session supportive?', value:'YES'},{label:'Is spread acceptable?', value:'YES'},{label:'Is there enough room to target?', value:'YES'},{label:'Is the SL structurally protected?', value:'YES'},{label:'Is the entry worth taking or should we skip?', value:'TAKE'}]}/>
  </Card>
}

export function PyramidingAutopilotPanel() {
  const rows = [
    {Stage:'Trade 1', Role:'Prove direction', Trigger:'Initial sniper entry only', Lot:'0.01', Protection:'Normal SL + TP1 plan', Status:'BASE'},
    {Stage:'Trade 2', Role:'Reward confirmation', Trigger:'+0.85R + BE+costs + clean retest', Lot:'0.02', Protection:'Cut newest add at -0.22R / 3 candles no progress', Status:'ARMED'},
    {Stage:'Trade 3', Role:'Press clean trend', Trigger:'+1.60R + Add 1 protected + trend still clean', Lot:'0.03', Protection:'Move add to BE at +0.35R; trail structure', Status:'WAITING'},
    {Stage:'Final add', Role:'Rare exceptional only', Trigger:'+2.80R + SNIPER + HTF liquidity open + low extension', Lot:'Max lot cap', Protection:'Newest/largest add exits first; strict final spread gate', Status:'RARE'}
  ];
  return <Card>
    <SectionTitle icon={<Layers3 size={16}/>} title="Prove → Confirm → Press → Exceptional Pyramid" right={<Tag color="purple">Protected Anti-Martingale</Tag>} />
    <p className="card-sub">First trade proves direction. The second trade rewards confirmation. The third trade presses only if trend remains clean. The final max-lot add is rare and only unlocks on exceptional sniper-grade conditions.</p>
    <DashboardKpiGrid><DashboardMiniCard label="Stage Model" value="4-Step" tone="purple"/><DashboardMiniCard label="Win Streak Gate" value="2+ Wins" tone="blue"/><DashboardMiniCard label="Final Add" value="Rare Only" tone="gold"/><DashboardMiniCard label="Fast Cut" value="-0.22R" tone="red"/></DashboardKpiGrid>
    <DataTable columns={['Stage','Role','Trigger','Lot','Protection','Status']} rows={rows} renderCell={(r,c)=> c==='Status' ? <Tag color={r[c]==='ARMED'?'green':r[c]==='BASE'?'blue':r[c]==='RARE'?'purple':'gold'}>{r[c]}</Tag> : c==='Lot' ? <strong>{r[c]}</strong> : r[c]} />
    <Checklist items={[{label:'Never add to a losing or unprotected trade',value:'ON'},{label:'All earlier legs must be protected before another add',value:'ON'},{label:'No chasing: pullback/retest and low extension required',value:'ON'},{label:'Final max-lot add requires SNIPER quality and exceptional HTF alignment',value:'ON'},{label:'Close newest/largest add first on any invalidation',value:'ON'}]}/>
  </Card>
}

export function TradeManagementIntelligencePanel() {
  return <Card>
    <SectionTitle icon={<Target size={16}/>} title="AI Trade Management Intelligence" right={<Tag color="green">Runner Optimiser</Tag>} />
    <DashboardKpiGrid><DashboardMiniCard label="Hold" value="YES"/><DashboardMiniCard label="Break-even" value="ARMED" tone="blue"/><DashboardMiniCard label="Trailing" value="ACTIVE" tone="purple"/><DashboardMiniCard label="TP Push" value="ON" tone="gold"/></DashboardKpiGrid>
    <Checklist items={[{label:'TP1 partial close', value:'25%'},{label:'TP2 partial close', value:'25%'},{label:'TP3 partial close', value:'25%'},{label:'TP4 runner close / manual AI extension', value:'25%'},{label:'Hold winners while HTF momentum remains clean', value:'ON'},{label:'Exit runner on structure failure', value:'ON'}]}/>
  </Card>
}

export function InstitutionalGuardrailsPanel() {
  return <Card>
    <SectionTitle icon={<LockKeyhole size={16}/>} title="Institutional Guardrails" right={<Tag color="red">Capital Protection</Tag>} />
    <DashboardKpiGrid><DashboardMiniCard label="Kill Switch" value="READY" tone="red"/><DashboardMiniCard label="Blackout" value="OFF"/><DashboardMiniCard label="Overfit Guard" value="PASS" tone="blue"/><DashboardMiniCard label="Broker Score" value="96" tone="purple"/></DashboardKpiGrid>
    <Checklist items={[{label:'Emergency kill switch blocks all execution instantly', value:'ON'},{label:'News blackout blocks high-impact danger windows', value:'ON'},{label:'Overfitting guard requires out-of-sample proof', value:'ON'},{label:'Spread/slippage memory controls trade permission', value:'ON'},{label:'Exposure cap controls pyramid and correlated trades', value:'ON'}]}/>
  </Card>
}

export function VolatilityRegimePanel() { return <Card><SectionTitle icon={<Gauge size={16}/>} title="Gold Volatility Regime" right={<Tag color="blue">ATR + Tick Flow</Tag>} /><DashboardKpiGrid><DashboardMiniCard label="Regime" value="NORMAL"/><DashboardMiniCard label="ATR Rank" value="68%" tone="blue"/><DashboardMiniCard label="Spread" value="LOW"/><DashboardMiniCard label="Impulse" value="CLEAN" tone="purple"/></DashboardKpiGrid><ProgressBar value={68}/></Card> }
export function DailySuperReviewPanel() { return <Card><SectionTitle icon={<Activity size={16}/>} title="Daily AI Performance Review" right={<Tag color="green">Auto generated</Tag>} /><Checklist items={[{label:'Overall Grade', value:'A-'},{label:'Best behaviour', value:'Skipped dirty conditions'},{label:'Best strategy', value:'Liquidity Sweep + OB Retest'},{label:'Main improvement', value:'Wait for cleaner Add 2 retest'},{label:'Tomorrow plan', value:'Sniper-only London open'}]}/></Card> }
export function TestingMemoryPanel() { return <Card><SectionTitle icon={<Gauge size={16}/>} title="Testing, Memory & Calibration" right={<Tag color="blue">Proof Layer</Tag>} /><DashboardKpiGrid><DashboardMiniCard label="Walk-forward" value="ON" tone="blue"/><DashboardMiniCard label="Monte Carlo" value="ON" tone="purple"/><DashboardMiniCard label="Calibration" value="78%" tone="gold"/><DashboardMiniCard label="Memory" value="ACTIVE"/></DashboardKpiGrid><Checklist items={[{label:'Strategy-by-strategy performance memory', value:'ON'},{label:'Session-specific win-rate memory', value:'ON'},{label:'Spread/slippage execution memory', value:'ON'},{label:'Forward-test report generator', value:'ON'},{label:'Daily AI performance review', value:'ON'}]}/></Card> }
export function ExecutionReadinessStrip() { return <Card><div className="reference-kpi-strip"><DashboardMiniCard label="Execution Quality" value="Excellent"/><DashboardMiniCard label="News Blackout" value="Clear"/><DashboardMiniCard label="TP1–TP4" value="Armed"/><DashboardMiniCard label="Pyramiding" value="Waiting Retest" tone="gold"/></div></Card> }
