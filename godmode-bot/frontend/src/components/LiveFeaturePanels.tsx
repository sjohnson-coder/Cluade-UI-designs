
import type { ReactNode } from 'react';
import { Activity, BarChart3, CalendarClock, DatabaseZap, FileChartColumn, LineChart, Network, Pyramid, Radar, ShieldCheck, SlidersHorizontal, Target, Wifi } from 'lucide-react';
import { Card, Checklist, DataTable, ProgressBar, SectionTitle, Tag } from './ui';

type Tone = 'green' | 'gold' | 'blue' | 'purple' | 'red';

function toneClass(tone: Tone) { return tone === 'red' ? 'negative' : tone === 'gold' ? 'gold' : 'positive'; }

function RefMiniCard({ icon, title, value, subtitle, color='green' }: { icon: ReactNode; title:string; value:string; subtitle:string; color?: Tone }) {
  return <Card soft>
    <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
      <span className={`tag ${color}`} style={{ width: 30, height: 30, display:'grid', placeItems:'center', padding:0 }}>{icon}</span>
      <div style={{ minWidth: 0 }}>
        <strong style={{ fontSize: 12 }}>{title}</strong>
        <div style={{ fontSize: 17, fontWeight: 900, marginTop: 4 }} className={toneClass(color)}>{value}</div>
        <p className="tiny muted" style={{ margin: '3px 0 0' }}>{subtitle}</p>
      </div>
    </div>
  </Card>
}

function RefGrid({ children, cols = 3 }: { children: ReactNode; cols?: 3 | 4 }) {
  return <div className={cols === 4 ? 'reference-kpi-strip' : 'reference-card-strip'}>{children}</div>
}

function RefSection({ icon, title, right, children }: { icon: ReactNode; title: string; right?: ReactNode; children: ReactNode }) {
  return <Card>
    <SectionTitle icon={icon} title={title} right={right} />
    {children}
  </Card>
}

export function LiveFeedsPanel() {
  return <RefSection icon={<Network size={16}/>} title="Real Market Feeds" right={<Tag color="green">Provider-ready</Tag>}>
    <RefGrid>
      <RefMiniCard icon={<CalendarClock size={15}/>} title="Economic Calendar API" value="Connected" subtitle="USD events, blackout windows, forecast, actual and previous." color="gold" />
      <RefMiniCard icon={<LineChart size={15}/>} title="DXY Feed" value="104.21 ▼" subtitle="Dollar pressure layer for gold bias." color="blue" />
      <RefMiniCard icon={<Activity size={15}/>} title="US10Y Yield Feed" value="4.28% ▼" subtitle="Yield pressure/relief layer for XAUUSD." color="purple" />
    </RefGrid>
    <Checklist items={[{label:'News blackout gate connected to calendar layer', value:'ON'},{label:'DXY + US10Y influence AI decision score', value:'ON'},{label:'Safe fallback prevents UI/backend crash if keys missing', value:'ON'}]}/>
  </RefSection>
}

export function RealBacktesterPanel() {
  return <RefSection icon={<BarChart3 size={16}/>} title="Real Tick-Data Backtester + Forward Reports" right={<Tag color="blue">Proof Engine</Tag>}>
    <RefGrid cols={4}>
      {[['MT5 Tick Import','copy_ticks_from when terminal is connected',86],['CSV Tick Replay','Broker tick data for research and replay',82],['Forward Test Generator','Daily/weekly demo-forward report output',88],['Daily AI Review','What worked, failed and what to improve',90]].map(([title,sub,val]) => <Card key={String(title)} soft><strong style={{ fontSize: 12 }}>{title}</strong><p className="tiny muted" style={{ margin:'4px 0 8px' }}>{sub}</p><ProgressBar value={Number(val)} /></Card>)}
    </RefGrid>
  </RefSection>
}

export function ExecutionUpgradePanel() {
  return <RefSection icon={<Target size={16}/>} title="Real Execution Engine" right={<Tag color="green">Safety gated</Tag>}>
    <DataTable columns={['Module','Purpose','Live Endpoint','Status']} rows={[
      {Module:'Broker-specific lot sizing',Purpose:'Tick value, tick size, volume min/step/max',Endpoint:'/api/execution/lot-size',Status:'READY'},
      {Module:'TP1–TP4 partial close',Purpose:'Close child legs or partial volumes at each target',Endpoint:'/api/trades/partial-close',Status:'DRY-RUN SAFE'},
      {Module:'MT5 trailing stop modifier',Purpose:'Moves SL via TRADE_ACTION_SLTP',Endpoint:'/api/trades/modify-trailing-stop',Status:'DRY-RUN SAFE'},
      {Module:'Pyramid execution validation',Purpose:'Exposure cap + BE + floating R validation before add',Endpoint:'/api/trades/pyramid-execute-real',Status:'AI CONTROLLED'},
    ]} renderCell={(r,c)=> c==='Status' ? <Tag color={String(r[c]).includes('AI')?'purple':String(r[c]).includes('READY')?'green':'gold'}>{r[c]}</Tag> : r[c==='Live Endpoint'?'Endpoint':c]} />
    <div style={{ marginTop: 12 }}><Checklist items={[{label:'Never pyramid into losing/unprotected position', value:'ON'},{label:'Exposure cap validation before order', value:'ON'},{label:'Live trading disabled unless GODMODE_ENABLE_LIVE_TRADING=true', value:'ON'}]}/></div>
  </RefSection>
}

export function ReplayVersioningPanel() {
  return <RefSection icon={<DatabaseZap size={16}/>} title="Replay Storage + Version Tracking" right={<Tag color="purple">Audit trail</Tag>}>
    <RefGrid>
      <RefMiniCard icon={<FileChartColumn size={15}/>} title="Trade Screenshot Replay" value="Stored" subtitle="Decision snapshot, chart image, events and notes." color="purple" />
      <RefMiniCard icon={<SlidersHorizontal size={15}/>} title="Strategy Versioning" value="Hash tracked" subtitle="Every configuration can be versioned and compared." color="blue" />
      <RefMiniCard icon={<Activity size={15}/>} title="Parameter Tracking" value="Versioned" subtitle="Risk/profile changes recorded with config hash." color="green" />
    </RefGrid>
  </RefSection>
}

export function DailyAIReviewPanel() {
  return <RefSection icon={<Radar size={16}/>} title="Daily AI Performance Review" right={<Tag color="green">Auto generated</Tag>}>
    <Checklist items={[{label:'Overall Grade', value:'A-'},{label:'Best behaviour', value:'Skipped dirty conditions'},{label:'Best strategy', value:'Liquidity Sweep + OB Retest'},{label:'Main improvement', value:'Wait for cleaner Add 2 retest'},{label:'Tomorrow plan', value:'Sniper-only London open'}]}/>
  </RefSection>
}

export function MacroDecisionPanel() {
  return <RefSection icon={<LineChart size={16}/>} title="Macro Decision Intelligence" right={<Tag color="gold">Gold-aware</Tag>}>
    <RefGrid>
      <RefMiniCard icon={<LineChart size={15}/>} title="DXY" value="104.21 ▼" subtitle="Soft DXY supports gold upside." color="red" />
      <RefMiniCard icon={<Activity size={15}/>} title="US10Y" value="4.28% ▼" subtitle="Yield softening supports gold." color="purple" />
      <RefMiniCard icon={<ShieldCheck size={15}/>} title="Gold Bias" value="BULLISH" subtitle="Macro score 84 / 100." color="green" />
    </RefGrid>
  </RefSection>
}

export function FullFeatureMapPanel() {
  const features = ['Real Calendar API','DXY Feed','US10Y Feed','Tick Backtester','Lot Sizing','TP1–TP4 Partial Close','MT5 Trailing Stop','Pyramid Execution','Replay Storage','Strategy Versioning','Parameter Tracking','Forward Reports','Daily AI Review','Emergency Kill Switch','News Blackout','Macro Context'];
  return <RefSection icon={<ShieldCheck size={16}/>} title="Full Backend ↔ UI Feature Map" right={<Tag color="green">All modules visible</Tag>}>
    <div className="grid grid-4">{features.map((x,i) => <Card key={x} soft>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:8 }}><strong style={{ fontSize: 12 }}>{x}</strong><Tag color="green">Connected</Tag></div>
      <div style={{ marginTop: 10 }}><ProgressBar value={i%3===0?88:i%3===1?92:96} /></div>
    </Card>)}</div>
  </RefSection>
}

export function PyramidExecutionPanel() {
  return <RefSection icon={<Pyramid size={16}/>} title="Prove / Confirm / Press Pyramid Execution" right={<Tag color="purple">Exceptional final add</Tag>}>
    <RefGrid cols={4}>
      <RefMiniCard icon={<Pyramid size={15}/>} title="Current Exposure" value="1.20%" subtitle="Before add" color="purple" />
      <RefMiniCard icon={<Target size={15}/>} title="Next Add Role" value="Confirm" subtitle="Reward proof" color="gold" />
      <RefMiniCard icon={<ShieldCheck size={15}/>} title="Final Add" value="Rare" subtitle="SNIPER only" color="green" />
      <RefMiniCard icon={<Wifi size={15}/>} title="AI Decision" value="WAIT" subtitle="Until retest proves" color="blue" />
    </RefGrid>
    <Checklist items={[{label:'Break-even protected', value:'YES'},{label:'Trade 2 confirms only after', value:'≥ 0.85R'},{label:'Trade 3 presses only if trend stays clean', value:'ON'},{label:'Final add requires exceptional conditions', value:'RARE'}]}/>
  </RefSection>
}
