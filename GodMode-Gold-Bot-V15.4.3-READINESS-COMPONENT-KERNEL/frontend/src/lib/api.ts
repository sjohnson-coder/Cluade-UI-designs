const API_BASE = import.meta.env.VITE_API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');
const GODMODE_API_KEY = import.meta.env.VITE_GODMODE_API_KEY || '';
export const FRONTEND_BUILD_ID='V15.4.3-READINESS-COMPONENT-KERNEL';
export type SafetyState='LIVE'|'STALE'|'OFFLINE'|'AUTH_REQUIRED'|'DEGRADED';
let safetyState: SafetyState = 'OFFLINE';

// Last-good response per GET path, used to keep the UI populated when the backend blips.
// This is a bounded LRU: previously an unbounded Map, and because job polling keys on
// `/api/jobs/<uuid>` a long session accumulated one permanently-retained entry per job.
const RESPONSE_CACHE_LIMIT = 96;
const responseCache = new Map<string, {at:number; json:any}>();
function cacheGet(key: string) {
  const hit = responseCache.get(key);
  if (hit) { responseCache.delete(key); responseCache.set(key, hit); }   // refresh LRU recency
  return hit;
}
function cacheSet(key: string, json: any) {
  responseCache.delete(key);
  responseCache.set(key, { at: Date.now(), json });
  while (responseCache.size > RESPONSE_CACHE_LIMIT) {
    const oldest = responseCache.keys().next();
    if (oldest.done) break;
    responseCache.delete(oldest.value);
  }
}

// Concurrent GETs of the same path share one network round-trip.
//
// Five independent consumers poll this backend: the React shell, the Dashboard page, and three
// vanilla runtime scripts loaded from index.html. Measured steady state was ~6.5 requests/second
// with /api/fast-sniper/status and /api/trading-modes/protected-burst/status each fetched twice
// per second by two different code paths that had no idea about each other. Coalescing collapses
// duplicate in-flight reads without changing any caller.
//
// The map is also published on window so the non-module runtime scripts can join the same pool
// (see public/godmode-runtime-bus.js).
const inflight = new Map<string, Promise<any>>();


// Runtime API key (set in Settings → Security, retained for this browser tab/session only). Used to authenticate the UI
// when the server is exposed for mobile/remote access (server: set GODMODE_API_KEY to the same value).
export const apiKey = {
  get(): string {
    try { return (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('godmode_api_key')) || GODMODE_API_KEY; }
    catch { return GODMODE_API_KEY; }
  },
  set(k: string) {
    try {
      if (k) sessionStorage.setItem('godmode_api_key', k);
      else sessionStorage.removeItem('godmode_api_key');
    } catch { /* ignore */ }
  },
};

// Hosts the operator reaches over a link they physically control: loopback, RFC1918 LAN, link-local,
// CGNAT (which is the Tailscale 100.64.0.0/10 range), and mDNS names. MOBILE_REMOTE_ACCESS.md
// documents exactly these two topologies — "http://192.168.1.20:8000" on home Wi-Fi and
// "http://100.101.102.103:8000" over Tailscale — and the previous check treated both as insecure
// public transport. Because the guard sits at the top of request() ahead of the method test, it
// short-circuited *every* call including GETs, so the documented phone dashboard loaded its shell
// and then showed nothing but offline fallbacks. Genuinely public plaintext hosts are still blocked.
function isPrivateHost(host: string): boolean {
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]') return true;
  if (host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) return true;
  if (host.startsWith('[fe80:') || host.startsWith('[fc') || host.startsWith('[fd')) return true;  // IPv6 link-local / ULA
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!v4) return false;
  const [a, b] = [Number(v4[1]), Number(v4[2])];
  if ([a, b, Number(v4[3]), Number(v4[4])].some((n) => n > 255)) return false;
  if (a === 127 || a === 10) return true;                 // loopback, 10.0.0.0/8
  if (a === 192 && b === 168) return true;                // 192.168.0.0/16
  if (a === 172 && b >= 16 && b <= 31) return true;       // 172.16.0.0/12
  if (a === 169 && b === 254) return true;                // 169.254.0.0/16 link-local
  if (a === 100 && b >= 64 && b <= 127) return true;      // 100.64.0.0/10 CGNAT — Tailscale
  return false;
}

function insecureRemoteTransport(): boolean {
  try {
    const url = new URL(API_BASE);
    if (url.protocol === 'https:') return false;
    return !isPrivateHost(url.hostname.toLowerCase());
  } catch {
    return true;
  }
}

function headers(extra: Record<string, string> = {}) {
  const h: Record<string, string> = { 'Content-Type': 'application/json', ...extra };
  const k = apiKey.get();
  if (k) h['X-GodMode-Key'] = k;
  return h;
}

function withExecutionId(payload: unknown, prefix: string) {
  const row = (payload && typeof payload === 'object') ? { ...(payload as Record<string, unknown>) } : {};
  if (row.executionId || row.idempotencyKey || row.signalId || row.tradeId) return row;
  const randomId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return { ...row, executionId: `${prefix}-${randomId}` };
}

export async function refreshExecutionReadiness(): Promise<{reachable:boolean; buildMatch:boolean; authRequired?:boolean; state:SafetyState; payload?:any; message?:string}> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(`${API_BASE}/api/readiness`, { headers: headers(), cache:'no-store', credentials:'omit', signal:controller.signal });
    if (res.status === 401) {
      safetyState='AUTH_REQUIRED';
      try { window.dispatchEvent(new CustomEvent('godmode:auth-required')); } catch {}
      return { reachable:true, buildMatch:false, authRequired:true, state:safetyState, message:'API key required.' };
    }
    const payload = await res.json().catch(() => ({}));
    const buildMatch = payload?.buildId === FRONTEND_BUILD_ID;
    safetyState = payload?.appReady === true && buildMatch ? 'LIVE' : 'DEGRADED';
    try {
      window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:safetyState,path:'/api/readiness',reasons:payload?.reasons||[],executionAuthority:payload?.executionAuthority||null}}));
      window.dispatchEvent(new CustomEvent('godmode:trading-readiness',{detail:{tradingReady:payload?.tradingReady===true,warnings:payload?.warnings||[],reasons:payload?.reasons||[],executionAuthority:payload?.executionAuthority||null}}));
    } catch {}
    return { reachable:true, buildMatch, state:safetyState, payload, message:buildMatch?'':'Frontend/backend build mismatch.' };
  } catch (error) {
    safetyState='OFFLINE';
    return { reachable:false, buildMatch:false, state:safetyState, message:error instanceof Error ? error.message : 'Backend unavailable.' };
  } finally {
    window.clearTimeout(timer);
  }
}

function request(path: string, fallback: any, init?: RequestInit) {
  const method = (init?.method || 'GET').toUpperCase();
  // Mutations are never shared — each one must reach the broker on its own.
  if (method !== 'GET') return requestOnce(path, fallback, init);
  const pending = inflight.get(path);
  if (pending) return pending;
  const run = requestOnce(path, fallback, init).finally(() => { inflight.delete(path); });
  inflight.set(path, run);
  return run;
}

async function requestOnce(path: string, fallback: any, init?: RequestInit) {
  const method = (init?.method || 'GET').toUpperCase();
  if (insecureRemoteTransport()) {
    safetyState='DEGRADED';
    const detail = 'Remote dashboard access over the public internet requires HTTPS. Plaintext HTTP is only permitted to loopback, your LAN, or a Tailscale address.';
    try { window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:safetyState,path}})); } catch {}
    return { ...fallback, ok:false, blocked:true, message:detail, safetyState };
  }
  // Only broker/order mutations are globally safety-gated. Configuration, MT5 connect,
  // validation and maintenance endpoints must remain usable so an operator can recover
  // from DEGRADED/OFFLINE states instead of being locked out of the controls needed to fix them.
  // V14.1.10 — every prefix below uses the real backend paths (plural
  // (/api/trades/..., not /api/trade/), nested (/api/trading-modes/protected-burst,
  // /api/pyramiding/execute), and none of the five original prefixes matched a single
  // real endpoint. The DEGRADED-state guard this release claims to add was silently
  // not covering ANY genuine order-mutating call. Enumerated from every @app.post/put/
  // delete route in app.py that actually sends an order to the broker.
  const EXECUTION_MUTATION_PATHS = [
    '/api/trades/execute', '/api/trades/execute-multi-target', '/api/trades/manage-live',
    '/api/trades/manual-trigger', '/api/trades/modify', '/api/trades/modify-trailing-stop',
    '/api/trades/partial-close', '/api/trades/close', '/api/trades/break-even',
    '/api/trades/pyramid-execute-real', '/api/pyramiding/execute',
    '/api/trading-modes/protected-burst',
  ];
  const configurationOnlyMutation = path === '/api/trading-modes/protected-burst';
  const executionMutation = method !== 'GET' && !configurationOnlyMutation && EXECUTION_MUTATION_PATHS.some(p => path.startsWith(p));
  const needsReadinessRefresh = executionMutation && safetyState !== 'LIVE';
  if (needsReadinessRefresh) {
    // Refresh transport/build truth, but do not duplicate the backend's safety policy.
    // A reachable matching backend must return the authoritative MT5, validation,
    // Tick Guard, reconciliation and pre-live blocker so the operator sees the real cause.
    const readiness = await refreshExecutionReadiness();
    if (!readiness.reachable || readiness.authRequired || !readiness.buildMatch) {
      const detail = readiness.message || `Trading execution unavailable while frontend safety state is ${readiness.state}.`;
      try { window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:readiness.state,path}})); } catch {}
      return { ok:false, blocked:true, message:detail, safetyState:readiness.state };
    }
  }
  const cacheKey = `godmode.apiCache:${path}`;
  const controller = new AbortController();
  // V13.7: /api/feeds/status can hit live upstream feeds (calendar + news). At a flat 2800ms
  // a slow-but-working feed timed out, the News card fell back to its 'not_configured'
  // default, and showed OFF even though the feeds were configured and fine. Give the feed
  // endpoints real headroom; everything else keeps the snappy 2.8s budget.
  const slowPath = path.startsWith('/api/feeds') || path.startsWith('/api/news');
  const criticalLivePath = path==='/api/readiness' || path==='/api/status' || path==='/api/dashboard' || path.startsWith('/api/fast-sniper/status') || path.startsWith('/api/trading-modes/protected-burst/status');
  const timeoutMs = method === 'GET' ? (slowPath ? 15000 : criticalLivePath ? 10000 : 6000) : 20000;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: headers(), cache: method === 'GET' ? 'no-store' : 'default', credentials:'omit', ...init, signal: controller.signal });
    if (res.status === 401) {
      // Server requires an API key (remote/LAN mode). Tell the UI so it can prompt for the key.
      safetyState='AUTH_REQUIRED'; try { window.dispatchEvent(new CustomEvent('godmode:auth-required')); window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:safetyState,path}})); } catch { /* ignore */ }
      throw new Error('401 API key required');
    }
    let json = await res.json().catch(() => ({}));
    if(path==='/api/readiness'){
      const buildMatch=json?.buildId===FRONTEND_BUILD_ID;
      safetyState=(json?.appReady===true&&buildMatch)?'LIVE':'DEGRADED';
      if(!buildMatch){json={...json,ready:false,reasons:[...(json?.reasons||[]),'Frontend/backend build mismatch']};}
      // V14.1.10 — surface tradingReady and warnings separately from app readiness.
      // read here: the app-level safety state ignored both, so "trading is armed" and
      // "why isn't it armed" were invisible even though the backend already knew.
      try {
        window.dispatchEvent(new CustomEvent('godmode:live-data',{detail:{path}}));
        window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:safetyState,path,reasons:json?.reasons||[]}}));
        window.dispatchEvent(new CustomEvent('godmode:trading-readiness',{detail:{
          tradingReady: json?.tradingReady === true,
          warnings: json?.warnings || [],
          reasons: json?.reasons || [],
          executionAuthority: json?.executionAuthority || null,
        }}));
      } catch {}
    }
    if (!res.ok && path !== '/api/readiness') return { ...fallback, ...json, ok:false, httpStatus:res.status };
    if (method === 'GET' && path !== '/api/settings') cacheSet(cacheKey, json);
    return json;
  } catch (error) {
    console.warn('[GodMode API]', path, error);
    if (method === 'GET' && path !== '/api/settings') {
      try {
        const cached = cacheGet(cacheKey);
        if (cached?.json) { const staleAgeMs = Math.max(0, Date.now()-Number(cached.at||0)); if(criticalLivePath){ safetyState='STALE'; window.dispatchEvent(new CustomEvent('godmode:stale-data',{detail:{path,staleAgeMs}})); } return { ...cached.json, stale: true, staleReason: 'frontend_memory_cache', staleAgeMs }; }
      } catch {}
    }
    if(criticalLivePath && safetyState !== 'AUTH_REQUIRED') {
      safetyState='OFFLINE';
      try { window.dispatchEvent(new CustomEvent('godmode:safety-state',{detail:{state:safetyState,path}})); } catch {}
    } else {
      try { window.dispatchEvent(new CustomEvent('godmode:ui-error',{detail:{path,message:error instanceof Error?error.message:'Request failed'}})); } catch {}
    }
    return fallback;
  } finally {
    window.clearTimeout(timer);
  }
}

// Shared read bus for the non-module runtime scripts loaded from index.html
// (predictor-live, burst-live, early-impulse-settings, runtime-recovery). They poll the same
// status endpoints this module already polls, so routing them through the same coalescer means
// each endpoint is fetched once per tick instead of once per consumer. A short TTL absorbs the
// case where two consumers tick a few milliseconds apart rather than simultaneously.
const busCache = new Map<string, {at:number; json:any}>();

// Accept either "/api/x" or a fully-qualified same-origin URL. The runtime scripts build their
// requests as `API + path` where API is window.location.origin, and request() prefixes API_BASE
// itself — so passing the absolute form straight through produced
// "http://host:8000http://host:8000/api/settings" and every call from those scripts threw
// "Failed to parse URL". Normalising here means a caller does not have to know whether it reached
// the api.ts implementation or the standalone one in godmode-runtime-bus.js, which uses raw fetch
// and tolerates both.
function toApiPath(target: string): string {
  if (target.startsWith('/')) return target;
  try {
    const url = new URL(target, window.location.origin);
    return url.pathname + url.search;
  } catch {
    return target;
  }
}

async function busFetch(target: string, ttlMs = 700, fallback: any = null): Promise<any> {
  const path = toApiPath(target);
  const hit = busCache.get(path);
  if (hit && Date.now() - hit.at < ttlMs) return hit.json;
  const json = await request(path, fallback);
  if (json != null) busCache.set(path, { at: Date.now(), json });
  return json;
}
try {
  (window as any).__godmodeFetchJSON = busFetch;
  (window as any).__godmodeApiKey = () => apiKey.get();
} catch { /* a sandboxed window must never break the dashboard */ }

function offline(path: string) {
  return { ok: false, source: 'frontend_offline', detail: `Backend unavailable for ${path}` };
}

const emptyTrades = { active: [], pending: [], history: [], memoryScope: 'bot_only', source: 'frontend_offline', message: 'Backend unavailable.' };
const emptyMarket = { connected: false, source: 'frontend_offline', symbol: 'XAUUSD', price: null, side: 'WAIT', confidence: 0, candles: [], regime: 'Backend offline', session: 'Unknown' };
const emptyAccount = { connected: false, source: 'frontend_offline', balance: 0, equity: 0, dailyPnl: 0, dailyPnlPct: 0, openRisk: 0, openRiskPct: 0, freeMargin: 0, marginHealth: 0, currency: '' };

export async function downloadExport(dataset: string, format = 'json') {
  const url = `${API_BASE}/api/export/${encodeURIComponent(dataset)}?format=${encodeURIComponent(format)}`;
  const res = await fetch(url, { headers: headers({ Accept: 'application/octet-stream' }), cache: 'no-store' });
  if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href; a.download = `godmode_${dataset}.${format}`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(href);
}


export const api = {
  readinessRefresh: () => request('/api/readiness/refresh', {ok:false,message:'Refresh unavailable'}, {method:'POST',body:'{}'}),
  readiness: () => request('/api/readiness', {ok:false,ready:false,reasons:['Backend unavailable']}),
  status: () => request('/api/status', offline('/api/status')),
  account: () => request('/api/account', emptyAccount),
  marketSnapshot: () => request('/api/market/snapshot', emptyMarket),
  candles: (tf: string, count = 500) => request(`/api/market/candles?tf=${encodeURIComponent(tf)}&count=${count}`, { ok: false, candles: [] }),
  dashboard: () => request('/api/dashboard', { status: offline('/api/dashboard'), account: emptyAccount, market: emptyMarket, trades: emptyTrades, why: ['Backend offline.'], source: 'frontend_offline' }),
  signals: () => request('/api/signals', []),
  strategies: () => request('/api/strategies', []),
  trades: () => request('/api/trades', emptyTrades),
  risk: () => request('/api/risk', { account: emptyAccount, trades: emptyTrades, warnings: [], source: 'frontend_offline' }),
  riskUpdate: (payload: unknown) => request('/api/risk/update', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  analytics: (dateFrom?: string, dateTo?: string) => {
    const qs = new URLSearchParams();
    if (dateFrom) qs.set('date_from', dateFrom);
    if (dateTo) qs.set('date_to', dateTo);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return request(`/api/analytics${suffix}`, { source: 'frontend_offline', kpis: { netProfit: 0, totalTrades: 0, winRate: 0, profitFactor: 0, expectancy: 0, maxDrawdown: 0 }, history: [] });
  },
  journal: (dateFrom?: string, dateTo?: string) => {
    const qs = new URLSearchParams();
    if (dateFrom) qs.set('date_from', dateFrom);
    if (dateTo) qs.set('date_to', dateTo);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return request(`/api/journal${suffix}`, []);
  },
  settings: () => request('/api/settings', offline('/api/settings')),
  saveSettings: (payload: unknown, expectedRevision?: number) => request('/api/settings', { ok: false }, { method: 'POST', body: JSON.stringify({ settings: payload, expectedRevision }) }),
  setValidationLock: (enabled: boolean, expectedRevision?: number) => request('/api/settings/validation-lock', { ok:false }, { method:'POST', body:JSON.stringify({enabled, expectedRevision}) }),

  mt5Connect: (payload: unknown, expectedRevision?: number) => request('/api/mt5/connect', { ok: false }, { method: 'POST', body: JSON.stringify({ ...((payload || {}) as Record<string, unknown>), expectedRevision }) }),
  mt5Disconnect: () => request('/api/mt5/disconnect', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  mt5AutoConnect: () => request('/api/mt5/auto-connect', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  mt5Refresh: (payload?: unknown) => request('/api/mt5/refresh', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  setLiveMode: (enabled: boolean, expectedRevision?: number) => request('/api/mt5/live-mode', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled, expectedRevision }) }),
  setAutoTrading: (enabled: boolean, expectedRevision?: number) => request('/api/mt5/auto-trading', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled, expectedRevision }) }),

  executeTrade: (payload: unknown) => request('/api/trades/execute', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(withExecutionId(payload,'ui-signal')) }),
  manualTradeTrigger: (payload: unknown) => request('/api/trades/manual-trigger', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(withExecutionId(payload,'ui-manual')) }),
  autoTradingStatus: () => request('/api/auto-trading/status', { ok: false }),
  preLiveStatus: () => request('/api/prelive/status', { ok:false, mode:'UNKNOWN', unresolvedCommands:0 }),
  autoTradingHeartbeat: () => request('/api/auto-trading/heartbeat', { ok: true, items: [] }),
  autoTradingTick: () => request('/api/auto-trading/tick', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify({ reason: 'ui_manual_tick' }) }),
  executeMultiTarget: (payload: unknown) => request('/api/trades/execute-multi-target', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(withExecutionId(payload,'ui-multi')) }),
  closeTrade: (payload: unknown) => request('/api/trades/close', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  modifyTrade: (payload: unknown) => request('/api/trades/modify', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  partialClose: (payload: unknown) => request('/api/trades/partial-close', { ok: false }, { method: 'POST', body: JSON.stringify(withExecutionId(payload,'ui-partial-close')) }),
  modifyTrailingStop: (payload: unknown) => request('/api/trades/modify-trailing-stop', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  breakEvenTrade: (payload: unknown) => request('/api/trades/break-even', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  manageLiveTrade: (payload: unknown) => request('/api/trades/manage-live', { action: 'HOLD' }, { method: 'POST', body: JSON.stringify(payload) }),

  // These two are the only 1 Hz reads in the product, and each has a second consumer outside React
  // (predictor-live.js and burst-live.js). Their timers are independent, so they land a few hundred
  // milliseconds apart rather than simultaneously and the in-flight coalescer alone cannot merge
  // them — measured in the browser, protected-burst/status was still being fetched twice a second.
  // Routing both consumers through the same short-TTL entry makes 1 Hz mean 1 request per second.
  fastSniperStatus: () => busFetch('/api/fast-sniper/status', 700, { ok:false, enabled:false, last:{}, endpointStatus:'UNREACHABLE', message:'Predictor status endpoint unavailable. General backend health may still be live.' }),
  protectedBurstStatus: () => busFetch('/api/trading-modes/protected-burst/status', 700, { ok:false, enabled:false, status:'UNREACHABLE', canFire:false, blocker:'Protected Burst status endpoint unavailable.', gates:[], sustained:{}, beProgress:{}, risk:{} }),

  aiDecision: () => request('/api/ai/decision', {}),
  aiActionMatrix: () => request('/api/ai/action-matrix', {}),
  aiStrictness: () => request('/api/ai/strictness', {}),
  saveAiStrictness: (payload: unknown) => request('/api/ai/strictness', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  aiEvaluate: (payload: unknown) => request('/api/ai/evaluate', {}, { method: 'POST', body: JSON.stringify(payload) }),
  aiSuperIntelligence: () => request('/api/ai/super-intelligence', {}),
  strategyArsenal: () => request('/api/strategy/arsenal', {}),
  enableStrategy: (id: string) => request('/api/strategy/enable', { ok: false }, { method: 'POST', body: JSON.stringify({ id }) }),
  disableStrategy: (id: string) => request('/api/strategy/disable', { ok: false }, { method: 'POST', body: JSON.stringify({ id }) }),
  configureStrategy: (payload: unknown) => request('/api/strategy/configure', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),

  marketIntelligence: () => request('/api/market/intelligence', {}),
  performanceMemory: () => request('/api/memory/performance', {}),
  pyramidingSettings: () => request('/api/pyramiding/settings', {}),
  savePyramidingSettings: (payload: unknown) => request('/api/pyramiding/settings', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  pyramidingPlan: () => request('/api/pyramiding/plan', {}),
  executePyramiding: (payload: unknown) => request('/api/pyramiding/execute', { ok: false }, { method: 'POST', body: JSON.stringify(withExecutionId(payload,'ui-pyramid')) }),
  tradeManagementStatus: () => request('/api/trade-management/status', {}),
  brokerExecutionQuality: () => request('/api/broker/execution-quality', {}),
  probabilityCalibration: () => request('/api/calibration/probability', []),
  overfittingGuard: () => request('/api/overfitting/guard', {}),
  killSwitchStatus: () => request('/api/emergency/kill-switch', {}),
  uiFeatureMap: () => request('/api/ui/feature-map', {}),
  walkForwardAsync: (payload?: unknown) => request('/api/backtest/walk-forward-async', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  monteCarlo: (payload: unknown) => request('/api/backtest/monte-carlo', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  backtestRun: (payload: unknown) => request('/api/backtest/run', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestValidate: (payload: unknown) => request('/api/backtest/validate', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestValidateAsync: (payload?: unknown) => request('/api/backtest/validate-async', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestRunAsync: (payload?: unknown) => request('/api/backtest/run-async', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  efficiencySweepAsync: (payload?: unknown) => request('/api/backtest/efficiency-sweep-async', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  labRunAsync: (payload?: unknown) => request('/api/lab/run-async', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestLast: () => request('/api/backtest/last', { ok: false }),
  jobStatus: (jid: string) => request(`/api/jobs/${jid}`, { ok: false }),
  jobCancel: (jid: string) => request(`/api/jobs/${jid}/cancel`, { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  journalAddEntry: (entry: unknown) => request('/api/journal/entry', { ok: false }, { method: 'POST', body: JSON.stringify(entry) }),
  // V13.10 — missed-move autopsy + what-could-have-been (scored from real candles server-side)
  exitLab: () => request('/api/analysis/exit-lab', { ok: false, status: 'unreachable' }),
  decisions: () => request('/api/journal/decisions', { ok:false, items:[], counts:{}, total:0 }),
  health: () => request('/api/health/full', { ok: false, overall: 'critical', dataSource: 'offline', isRealData: false, components: [], summary: { up:0, warn:0, down:0, criticalDown:[] } }),
  mt5Reconnect: () => request('/api/mt5/connect', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  journalMissedPumps: (limit = 40) => request(`/api/journal/missed-pumps?limit=${limit}`, { ok: false, items: [], totals: {} }),
  journalDecisions: (category?: string, limit = 250) => request(`/api/journal/decisions?category=${encodeURIComponent(category || 'all')}&limit=${limit}`, { ok: false, items: [], counts: {} }),
  labRun: (payload?: unknown) => request('/api/lab/run', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  labStatus: () => request('/api/lab/status', { ok: false }),
  labInstall: (id: string) => request('/api/lab/install', { ok: false }, { method: 'POST', body: JSON.stringify({ id }) }),
  labUninstall: () => request('/api/lab/uninstall', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  labGenerate: (payload?: unknown) => request('/api/lab/generate', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  labFetchFeed: () => request('/api/lab/fetch-feed', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  journalDecisionsClear: () => request('/api/journal/decisions/clear', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  backtestOptimizeWeights: (payload: unknown) => request('/api/backtest/optimize-weights', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestWeights: () => request('/api/backtest/weights', { ok: false }),
  backtestWeightsReset: () => request('/api/backtest/weights/reset', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  backtestApplyVerdicts: (payload: unknown) => request('/api/backtest/apply-verdicts', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  replayTrade: (id: string) => request(`/api/replay/trade/${id}`, {}),
  killSwitch: (reason: string) => request('/api/emergency/kill-switch', { ok: false }, { method: 'POST', body: JSON.stringify({ reason }) }),
  resetKillSwitch: () => request('/api/emergency/reset', { ok: false }, { method: 'POST' }),
  telegramStatus: () => request('/api/telegram/status', { ok:false, configured:false }),
  saveTelegram: (payload: unknown) => request('/api/telegram/save', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  testTelegram: (payload: unknown) => request('/api/telegram/test', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  telegramRecap: (payload: unknown) => request('/api/telegram/recap', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  v15Overview: () => request('/api/v15/overview', { version: '15.0.5', status: 'offline', health: { score: 0, ok: false, errors: ['Backend unavailable'] } }),
  v15Evaluate: (payload: unknown) => request('/api/v15/evaluate', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  v15ExternalRefresh: () => request('/api/v15/external-context/refresh', { available: false, errors: ['Backend unavailable'] }, { method: 'POST', body: JSON.stringify({}) }),
  v15Governance: () => request('/api/v15/governance', { active: null, pending: [], history: [] }),
  aiMonitor: () => request('/api/ai/monitor', { ok: false }),
  createBackup: () => request('/api/replay/store', { ok: false }, { method: 'POST', body: JSON.stringify({ event: 'BACKUP_REQUEST', timestamp: new Date().toISOString() }) }),

  notifications: () => request('/api/notifications', { ok: true, unread: 0, items: [] }),
  clearNotifications: () => request('/api/notifications/clear', { ok: true, unread: 0, items: [] }, { method: 'POST', body: JSON.stringify({}) }),
  // V13.7: fallback no longer claims 'not_configured'. A failed/timed-out request tells us
  // NOTHING about configuration — reporting it as not_configured is the UI stating a fact
  // it cannot know, and is exactly why a working, configured news feed showed OFF.
  feedsStatus: () => request('/api/feeds/status', { ok: false, unreachable: true, economicCalendar: { status: 'unknown' }, marketNews: { status: 'unknown' }, macro: { status: 'unknown' } }),
  liveCalendar: () => request('/api/feeds/economic-calendar/live', { events: [], blackout: {}, configured: false }),
  liveNews: () => request('/api/feeds/news/live', { items: [], status: { status: 'not_configured' }, configured: false }),
  docsInfo: () => request('/api/docs-info', {}),
  aiProviderTest: () => request('/api/ai/provider/test', { ok: false }),
  aiAuditPreview: () => request('/api/ai/audit/preview', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify({}) }),
  aiAuditLog: (limit = 30) => request(`/api/ai/audit/log?limit=${limit}`, { ok: false, items: [], verdictCounts: {} }),
  dataEpoch: () => request('/api/data/epoch', { ok: false, active: false }),
  dataPurge: (scope: string) => request('/api/data/purge', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify({ scope, confirm: true }) }),
  aiPerformanceReview: (period = 'daily', useAi = true) => request(`/api/ai/performance-review?period=${encodeURIComponent(period)}&use_ai=${useAi ? 'true' : 'false'}`, { ok: false, recommendedFixes: [], diagnosis: [] }),
  aiUnifiedRecommendations: () => request('/api/ai/unified-recommendations', { ok: false, items: [], review: {} }),
  aiApplyProposal: (p: unknown) => request('/api/ai/apply-proposal', { ok: false }, { method: 'POST', body: JSON.stringify(p) }),
  aiTradeReviewEngine: () => request('/api/ai/trade-review-engine', { ok: false, stats: {}, findings: [], proposals: [] }),
  aiOptimisationApply: (review: unknown) => request('/api/ai/optimisation/apply', { ok: false }, { method: 'POST', body: JSON.stringify({ review }) }),
  aiOptimisationRollback: (snapshotId?: string, expectedRevision?: number) => request('/api/ai/optimisation/rollback', { ok: false }, { method: 'POST', body: JSON.stringify({ snapshotId, expectedRevision }) }),
  configExport: (includeSecrets = false) => request(`/api/config/export?include_secrets=${includeSecrets ? 'true' : 'false'}`, { ok: false }),
  configImport: (payload: unknown, expectedRevision?: number) => request('/api/config/import', { ok: false }, { method: 'POST', body: JSON.stringify({ settings: (payload as any)?.settings || payload, expectedRevision }) }),
  configLibrary: () => request('/api/config/library', { ok: false, items: [] }),
  configLibraryApply: (id: string) => request('/api/config/library/apply', { ok: false }, { method: 'POST', body: JSON.stringify({ id }) }),
  configLibrarySaveCurrent: (payload: unknown) => request('/api/config/library/save-current', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  tradingModesStatus: () => request('/api/trading-modes/status', { ok: false }),
  setProtectedBurst: (enabled: boolean, settings?: unknown, expectedRevision?: number) => request('/api/trading-modes/protected-burst', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled, settings, expectedRevision }) }),
  setPyramidingMode: (enabled: boolean, expectedRevision?: number) => request('/api/trading-modes/pyramiding', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled, expectedRevision }) }),
};
