// Module-level background-job store. Jobs keep running and polling here, INDEPENDENT of which page
// or tab is mounted — so a backtest/lab run survives switching tabs, and its progress + result are
// still there when you come back. Each job is keyed (e.g. 'backtest', 'validate', 'lab').
import { useEffect, useState } from 'react';
import { api } from './api';

export type JobState = {
  running: boolean;
  pct: number;
  stage: string;
  eta: number | null;
  result: any | null;
  error?: string;
  jobId: string | null;
  startedAt?: number;
};

const EMPTY: JobState = { running: false, pct: 0, stage: '', eta: null, result: null, jobId: null };
const states: Record<string, JobState> = {};
const listeners: Record<string, Set<() => void>> = {};
const timers: Record<string, any> = {};

function emit(key: string) { (listeners[key] || new Set()).forEach((l) => l()); }
function setState(key: string, patch: Partial<JobState>) {
  states[key] = { ...(states[key] || EMPTY), ...patch };
  emit(key);
}

function poll(key: string) {
  clearTimeout(timers[key]);
  const tick = async () => {
    const st = states[key];
    if (!st || !st.running || !st.jobId) return;
    // api.jobStatus resolves to a fallback rather than rejecting, but a rejection here (an aborted
    // navigation, a serialisation error) used to escape as an unhandled promise rejection and
    // silently end the poll loop, leaving a finished backtest stuck at "running" forever with no
    // way to recover except a page reload.
    let j: any;
    try { j = await api.jobStatus(st.jobId); }
    catch (error) { setState(key, { running: false, error: error instanceof Error ? error.message : 'Job status request failed.' }); return; }
    if (!j?.ok) { setState(key, { running: false, error: j?.message || 'Job was lost.' }); return; }
    if (j.status === 'done') { setState(key, { running: false, pct: 100, stage: 'Done', eta: 0, result: j.result }); return; }
    if (j.status === 'error') { setState(key, { running: false, error: j.message || 'Job failed.' }); return; }
    if (j.status === 'cancelled') { setState(key, { running: false, stage: 'Stopped', eta: 0 }); return; }
    setState(key, { pct: j.progress || 0, stage: j.stage || '', eta: j.etaSeconds ?? null });
    timers[key] = setTimeout(tick, 600);
  };
  tick();
}

export const jobStore = {
  get(key: string): JobState { return states[key] || EMPTY; },
  subscribe(key: string, fn: () => void) {
    (listeners[key] ||= new Set()).add(fn);
    return () => { listeners[key]?.delete(fn); };
  },
  // Start a job; startFn must return {jobId} (the *-async endpoints). Ignores a second start while running.
  async start(key: string, startFn: () => Promise<any>) {
    if (states[key]?.running) return;
    setState(key, { running: true, pct: 0, stage: 'Starting…', eta: null, result: null, error: undefined, jobId: null, startedAt: Date.now() });
    let s: any;
    // Without this, a throwing startFn left the job pinned at running:true with no jobId, so the
    // Run button stayed disabled for the rest of the session.
    try { s = await startFn(); }
    catch (error) { setState(key, { running: false, error: error instanceof Error ? error.message : 'Could not start the job.' }); return; }
    if (s?.ok === false || !s?.jobId) { setState(key, { running: false, error: s?.message || 'Could not start the job.' }); return; }
    setState(key, { jobId: s.jobId });
    poll(key);
  },
  async stop(key: string) {
    const st = states[key];
    if (st?.jobId) { setState(key, { stage: 'Stopping…' }); await api.jobCancel(st.jobId); }
    else setState(key, { running: false, stage: 'Stopped' });
  },
  clear(key: string) { clearTimeout(timers[key]); states[key] = { ...EMPTY }; emit(key); },
};

// React hook: re-renders the component whenever this job's state changes.
export function useJob(key: string): JobState {
  const [, force] = useState(0);
  useEffect(() => jobStore.subscribe(key, () => force((x) => x + 1)), [key]);
  return jobStore.get(key);
}
