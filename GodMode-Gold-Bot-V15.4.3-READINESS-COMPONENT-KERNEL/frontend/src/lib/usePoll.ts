import { useEffect, useRef } from 'react';

/**
 * Interval polling that cannot pile up.
 *
 * Every page in this app used the same raw shape:
 *
 *     useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id) }, []);
 *
 * which has three problems in a trading dashboard that talks to a single-process backend:
 *
 *  1. NO OVERLAP GUARD. setInterval fires on wall-clock time, not on completion. When the backend
 *     is busy — exactly when a position is open and the poll rate is highest — a request that takes
 *     longer than the interval is joined by the next one, then the next. Requests stack, the
 *     backend's thread pool saturates, responses get slower, and more requests stack. The UI reads
 *     as "laggy" precisely when it matters most. Scheduling the next tick only after the current
 *     one settles makes the loop self-limiting under load.
 *
 *  2. NO VISIBILITY GUARD on most callers. Only 5 of 14 polling sites checked document.hidden, so a
 *     backgrounded tab kept hammering the backend and burning laptop battery indefinitely.
 *
 *  3. NO IMMEDIATE CATCH-UP. Returning to a hidden tab left stale data on screen until the next
 *     scheduled tick, which on the slower loops is up to two minutes.
 *
 * The interval is a gap *between* runs, so the effective request rate is
 * `1 / (interval + serviceTime)` — it degrades gracefully instead of collapsing.
 */
export function usePoll(fn: () => void | Promise<any>, intervalMs: number, deps: unknown[] = []) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let running = false;

    const schedule = () => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(tick, intervalMs);
    };

    const tick = async () => {
      if (cancelled) return;
      if (document.hidden || running) { schedule(); return; }
      running = true;
      try { await fnRef.current(); }
      catch (error) { console.warn('[GodMode poll]', error); }
      finally { running = false; schedule(); }
    };

    // Coming back to the tab shows fresh data straight away rather than after a full interval.
    const onVisible = () => { if (!document.hidden) void tick(); };
    document.addEventListener('visibilitychange', onVisible);

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);
}
