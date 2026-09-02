import { useCallback, useEffect, useState } from 'react';
import { Activity, AlertTriangle, BellOff, CircleCheck, Gauge, Hand, Ruler, TrendingUp } from 'lucide-react';
import { Card, Checklist, ProgressBar, SectionTitle, Tag } from './ui';
import { api } from '../lib/api';

type SessionForecast = { expectedRange?: number; lower?: number; upper?: number; shareOfDailyAtr?: number };
type Upgrade = {
  volatilityForecast?: { expectedRange?: number; lower?: number; upper?: number; rSquared?: number;
                         observations?: number; method?: string; degraded?: boolean; reason?: string };
  sessionForecast?: Record<string, SessionForecast>;
  calibration?: { method?: string; samples?: number; brierBefore?: number; brierAfter?: number;
                  eceBefore?: number; eceAfter?: number; improved?: boolean; reason?: string };
  calibrationCurve?: Array<{ displayed: number; calibrated: number }>;
  abstention?: { action?: string; noveltyZ?: number; disagreement?: number;
                 sizeMultiplier?: number; reasons?: string[] };
  featureDistribution?: { observations?: number; features?: number };
  executionEconomics?: { enabled?: boolean; minStopCostMultiple?: number; roundTripCost?: number;
                         minimumStop?: number; costFractionAtMinimum?: number };
  notificationThrottle?: { activeBlocks?: string[]; remindAfterSeconds?: number };
};

const money = (v: any) => `$${Number(v || 0).toFixed(2)}`;
const pct = (v: any) => `${(Number(v || 0) * 100).toFixed(1)}%`;

const SESSION_LABELS: Record<string, string> = {
  ASIA: 'Asia 18:05–02:00',
  LONDON: 'London 02:00–08:00',
  NEW_YORK: 'New York 08:00–12:00',
  NEW_YORK_PM: 'New York 12:00–17:00',
};

function actionTag(action?: string) {
  if (action === 'ABSTAIN') return <Tag color="red">Abstain</Tag>;
  if (action === 'REDUCE') return <Tag color="amber">Reduced size</Tag>;
  return <Tag color="green">Trading</Tag>;
}

export default function ForecastIntelligence() {
  const [data, setData] = useState<Upgrade | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.intelligenceUpgrade();
      setData(res || null);
      setError('');
    } catch (e: any) {
      setError(String(e?.message || 'Forecast intelligence unavailable'));
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, 20000);
    return () => window.clearInterval(timer);
  }, [load]);

  const vol = data?.volatilityForecast;
  const cal = data?.calibration;
  const abs = data?.abstention;
  const econ = data?.executionEconomics;
  const throttle = data?.notificationThrottle;
  const sessions = data?.sessionForecast || {};
  const maxRange = Math.max(1e-9, ...Object.values(sessions).map((s) => Number(s?.expectedRange || 0)));

  return (
    <Card>
      <SectionTitle
        title="Forecast Intelligence"
        icon={<TrendingUp size={16} />}
        right={
          <span className="tiny muted">
            Volatility is ~3,160&times; more forecastable than direction on this instrument
          </span>
        }
      />

      {error && <div className="tiny negative" style={{ marginBottom: 10 }}>{error}</div>}

      <div className="grid grid-2" style={{ gap: 14 }}>
        {/* ---- volatility forecast ---- */}
        <Card soft>
          <SectionTitle title="Tomorrow's expected range" icon={<Activity size={15} />} />
          {vol?.degraded ? (
            <div className="tiny muted">
              Warming up — {vol?.reason || 'not enough completed daily bars yet'}.
              Falling back to ATR14.
            </div>
          ) : (
            <>
              <div className="value" style={{ fontSize: 30, lineHeight: 1.1 }}>{money(vol?.expectedRange)}</div>
              <div className="tiny muted" style={{ marginTop: 4 }}>
                80% interval {money(vol?.lower)} – {money(vol?.upper)}
              </div>
              <div className="tiny" style={{ marginTop: 10, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                <span>model <strong>{vol?.method}</strong></span>
                <span>R² <strong>{Number(vol?.rSquared || 0).toFixed(3)}</strong></span>
                <span>fitted on <strong>{vol?.observations}</strong> days</span>
              </div>
            </>
          )}
        </Card>

        {/* ---- abstention ---- */}
        <Card soft>
          <SectionTitle title="Confidence to act" icon={<Hand size={15} />} right={actionTag(abs?.action)} />
          <div className="tiny" style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 8 }}>
            <span>novelty <strong>{Number(abs?.noveltyZ || 0).toFixed(2)}σ</strong></span>
            <span>source disagreement <strong>{Number(abs?.disagreement || 0).toFixed(2)}</strong></span>
            <span>size <strong>{pct(abs?.sizeMultiplier)}</strong></span>
          </div>
          <ProgressBar value={Number(abs?.sizeMultiplier || 0) * 100} />
          <div className="tiny muted" style={{ marginTop: 8 }}>
            {(abs?.reasons || ['No assessment yet.'])[0]}
          </div>
          <div className="tiny muted" style={{ marginTop: 6 }}>
            Learned from {data?.featureDistribution?.observations ?? 0} observations
            across {data?.featureDistribution?.features ?? 0} features.
          </div>
        </Card>

        {/* ---- session split ---- */}
        <Card soft>
          <SectionTitle title="Where that range is expected to land" icon={<Ruler size={15} />} />
          {Object.keys(sessions).length === 0 ? (
            <div className="tiny muted">No session forecast yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
              {Object.entries(sessions).map(([key, s]) => (
                <div key={key}>
                  <div className="tiny" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span>{SESSION_LABELS[key] || key}</span>
                    <strong>{money(s?.expectedRange)}</strong>
                  </div>
                  <ProgressBar value={(Number(s?.expectedRange || 0) / maxRange) * 100} />
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* ---- calibration ---- */}
        <Card soft>
          <SectionTitle
            title="Probability calibration"
            icon={<Gauge size={15} />}
            right={cal?.improved ? <Tag color="green">{cal?.method}</Tag> : <Tag>uncalibrated</Tag>}
          />
          {cal?.improved ? (
            <>
              <Checklist
                items={[
                  { label: 'Brier score', value: `${Number(cal?.brierBefore).toFixed(3)} → ${Number(cal?.brierAfter).toFixed(3)}` },
                  { label: 'Calibration error', value: `${Number(cal?.eceBefore).toFixed(3)} → ${Number(cal?.eceAfter).toFixed(3)}` },
                  { label: 'Closed trades used', value: String(cal?.samples ?? 0) },
                ]}
              />
              {!!data?.calibrationCurve?.length && (
                <div className="tiny muted" style={{ marginTop: 8 }}>
                  {data.calibrationCurve.map((p) => (
                    <span key={p.displayed} style={{ marginRight: 12 }}>
                      {Math.round(p.displayed * 100)}% → <strong>{Math.round(p.calibrated * 100)}%</strong>
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="tiny muted">
              {cal?.reason || `Needs closed bot trades before confidence scores can be checked against outcomes. ${cal?.samples ?? 0} so far.`}
            </div>
          )}
        </Card>

        {/* ---- execution economics ---- */}
        <Card soft>
          <SectionTitle
            title="Execution economics"
            icon={<AlertTriangle size={15} />}
            right={econ?.enabled ? <Tag color="green">Cost gate on</Tag> : <Tag color="red">Cost gate off</Tag>}
          />
          <Checklist
            items={[
              { label: 'Round-trip cost now', value: money(econ?.roundTripCost) },
              { label: 'Minimum allowed stop', value: money(econ?.minimumStop) },
              {
                label: 'Cost ceiling per trade',
                value: pct(econ?.costFractionAtMinimum),
                type: Number(econ?.costFractionAtMinimum || 0) > 0.08 ? 'warning' : 'success',
              },
            ]}
          />
          <div className="tiny muted" style={{ marginTop: 8 }}>
            A stop tighter than {money(econ?.minimumStop)} hands more than
            {' '}{pct(econ?.costFractionAtMinimum)} of every trade's risk to the spread.
          </div>
        </Card>

        {/* ---- notification throttle ---- */}
        <Card soft>
          <SectionTitle
            title="Alert throttle"
            icon={<BellOff size={15} />}
            right={
              (throttle?.activeBlocks?.length || 0) > 0
                ? <Tag color="amber">{throttle?.activeBlocks?.length} active</Tag>
                : <Tag color="green">Clear</Tag>
            }
          />
          {(throttle?.activeBlocks?.length || 0) === 0 ? (
            <div className="tiny muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CircleCheck size={14} color="var(--green)" />
              No policy block active. Entries are not being suppressed.
            </div>
          ) : (
            <Checklist
              items={(throttle?.activeBlocks || []).map((b) => ({ label: b, value: 'suppressing repeats', type: 'warning' as const }))}
            />
          )}
          <div className="tiny muted" style={{ marginTop: 8 }}>
            A repeated block alerts once, then at most every
            {' '}{Math.round(Number(throttle?.remindAfterSeconds || 900) / 60)} min.
            Every attempt is still recorded in the journal.
          </div>
        </Card>
      </div>
    </Card>
  );
}
