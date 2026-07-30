import { useEffect, useState } from 'react';
import { CalendarDays, ShieldCheck } from 'lucide-react';
import { Card, SectionTitle, Tag } from '../components/ui';
import { usePoll } from '../lib/usePoll';

/**
 * EconomicCalendar — V13.0 (restored)
 *
 * The calendar data was live at /api/feeds/economic-calendar/live the whole time; there was simply
 * no UI mounted for it, so the only calendar signal you got was a one-line "next high-impact USD"
 * on the dashboard. This is the real panel.
 *
 * Design: the calendar's job is answering ONE question — "am I about to get run over?" So the
 * blackout state is the loudest thing here, the countdown to the next high-impact USD print is
 * second, and the event list is quiet reference below it. Impact is encoded as a bronze weight
 * ramp rather than a traffic-light row, so a screen full of events still scans in one pass.
 * No fabricated rows: an empty/unconfigured feed says so plainly.
 */

type Ev = {
  id: string; title: string; currency: string;
  impact: 'high' | 'medium' | 'low' | string;
  timeUtc: string;
  actual?: string | null; forecast?: string | null; previous?: string | null;
};

export default function EconomicCalendar() {
  const [events, setEvents] = useState<Ev[]>([]);
  const [blackout, setBlackout] = useState<any>({});
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [err, setErr] = useState('');

  const load = async () => {
    try {
      const r = await fetch('/api/feeds/economic-calendar/live');
      const j = await r.json();
      setEvents(Array.isArray(j.events) ? j.events : []);
      setBlackout(j.blackout || {});
      setConfigured(!!j.configured);
      setErr('');
    } catch (e: any) { setErr(String(e?.message || e)); }
  };

  usePoll(load, 60000); // calendar moves in minutes, not ms — 60s is honest

  const now = Date.now();
  const upcoming = events
    .map(e => ({ ...e, ms: new Date(e.timeUtc).getTime() - now }))
    .filter(e => !isNaN(e.ms) && e.ms > -60 * 60 * 1000)
    .sort((a, b) => a.ms - b.ms);

  const nextHigh = upcoming.find(e => e.impact === 'high' && /USD/i.test(e.currency));
  const active = !!blackout?.blackoutActive;

  const mins = (ms: number) => {
    const m = Math.round(ms / 60000);
    if (m < 0) return `${Math.abs(m)}m ago`;
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    return h < 24 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}d ${h % 24}h`;
  };

  const weight = (i: string) => i === 'high' ? 1 : i === 'medium' ? 0.62 : 0.34;

  return (
    <Card className="calendar-card">
      <SectionTitle
        icon={<CalendarDays size={16} />}
        title="Economic Calendar"
        right={<Tag color={active ? 'red' : configured ? 'green' : 'amber'}>
          {active ? 'BLACKOUT' : configured ? 'LIVE' : 'NOT CONFIGURED'}
        </Tag>}
      />

      {/* The one question this panel exists to answer, answered first. */}
      <div className="cal-verdict" style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 8,
        border: `1px solid ${active ? 'rgba(220,80,80,.45)' : 'rgba(201,169,97,.28)'}`,
        background: active ? 'rgba(220,80,80,.08)' : 'rgba(201,169,97,.05)', marginBottom: 10,
      }}>
        <ShieldCheck size={18} style={{ color: active ? '#e05555' : 'rgba(201,169,97,.9)', flexShrink: 0 }} />
        <div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>
            {active ? 'News blackout active — new entries blocked'
              : nextHigh ? `Clear for ${mins(nextHigh.ms)}`
              : configured ? 'Clear — no high-impact USD event ahead' : 'Calendar feed not configured'}
          </div>
          <div className="tiny muted" style={{ marginTop: 2 }}>
            {nextHigh ? `Next: ${nextHigh.title} (${nextHigh.currency})`
              : configured ? 'The blackout gate only reacts to high-impact USD prints.'
              : 'Settings → Data Feeds → Economic calendar URL.'}
          </div>
        </div>
      </div>

      {err && <p className="tiny" style={{ color: '#e05555' }}>Calendar fetch failed: {err}</p>}
      {configured === false && !err && (
        <p className="tiny muted">No calendar URL set, so no events are shown. Nothing is fabricated here.</p>
      )}
      {configured && upcoming.length === 0 && !err && (
        <p className="tiny muted">Feed is live but returned no upcoming events (normal at weekends).</p>
      )}

      {upcoming.length > 0 && (
        <div className="cal-list" style={{ maxHeight: 260, overflowY: 'auto' }}>
          {upcoming.slice(0, 24).map(e => (
            <div key={e.id} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '7px 2px',
              borderBottom: '1px solid rgba(255,255,255,.05)',
              opacity: e.ms < 0 ? 0.45 : 1,
            }}>
              {/* impact as a bronze weight bar — scans faster than three coloured dots */}
              <span style={{
                width: 3, height: 22, borderRadius: 2, flexShrink: 0,
                background: `rgba(201,169,97,${weight(e.impact)})`,
              }} />
              <span style={{ width: 62, flexShrink: 0, fontVariantNumeric: 'tabular-nums', fontSize: 12, opacity: .75 }}>
                {mins(e.ms)}
              </span>
              <span style={{ width: 42, flexShrink: 0, fontSize: 11, opacity: .6 }}>{e.currency}</span>
              <span style={{ flex: 1, fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {e.title}
              </span>
              {(e.forecast || e.previous) && (
                <span className="tiny muted" style={{ flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                  {e.forecast ? `f/c ${e.forecast}` : ''}{e.forecast && e.previous ? ' · ' : ''}{e.previous ? `prev ${e.previous}` : ''}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
