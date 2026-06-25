const API_BASE = import.meta.env.VITE_API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');
const GODMODE_API_KEY = import.meta.env.VITE_GODMODE_API_KEY || '';

function headers(extra: Record<string, string> = {}) {
  const h: Record<string, string> = { 'Content-Type': 'application/json', ...extra };
  if (GODMODE_API_KEY) h['X-GodMode-Key'] = GODMODE_API_KEY;
  return h;
}

async function request(path: string, fallback: any, init?: RequestInit) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: headers(), ...init });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  } catch (error) {
    console.warn('[GodMode API]', path, error);
    return fallback;
  }
}

function offline(path: string) {
  return { ok: false, source: 'frontend_offline', detail: `Backend unavailable for ${path}` };
}

const emptyTrades = { active: [], pending: [], history: [], memoryScope: 'bot_only', source: 'frontend_offline', message: 'Backend unavailable.' };
const emptyMarket = { connected: false, source: 'frontend_offline', symbol: 'XAUUSD', price: null, side: 'WAIT', confidence: 0, candles: [], regime: 'Backend offline', session: 'Unknown' };
const emptyAccount = { connected: false, source: 'frontend_offline', balance: 0, equity: 0, dailyPnl: 0, dailyPnlPct: 0, openRisk: 0, openRiskPct: 0, freeMargin: 0, marginHealth: 0, currency: '' };

export function downloadExport(dataset: string, format = 'json') {
  const url = `${API_BASE}/api/export/${encodeURIComponent(dataset)}?format=${encodeURIComponent(format)}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = `godmode_${dataset}.${format}`;
  a.target = '_blank';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export const api = {
  status: () => request('/api/status', offline('/api/status')),
  account: () => request('/api/account', emptyAccount),
  marketSnapshot: () => request('/api/market/snapshot', emptyMarket),
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
  settings: () => request('/api/settings', {}),
  saveSettings: (payload: unknown) => request('/api/settings', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),

  mt5Connect: (payload: unknown) => request('/api/mt5/connect', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  mt5Disconnect: () => request('/api/mt5/disconnect', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  mt5AutoConnect: () => request('/api/mt5/auto-connect', { ok: false }, { method: 'POST', body: JSON.stringify({}) }),
  mt5Refresh: (payload?: unknown) => request('/api/mt5/refresh', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  setLiveMode: (enabled: boolean) => request('/api/mt5/live-mode', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled }) }),
  setAutoTrading: (enabled: boolean) => request('/api/mt5/auto-trading', { ok: false }, { method: 'POST', body: JSON.stringify({ enabled }) }),

  executeTrade: (payload: unknown) => request('/api/trades/execute', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload) }),
  manualTradeTrigger: (payload: unknown) => request('/api/trades/manual-trigger', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload) }),
  autoTradingStatus: () => request('/api/auto-trading/status', { ok: false }),
  autoTradingHeartbeat: () => request('/api/auto-trading/heartbeat', { ok: true, items: [] }),
  autoTradingTick: () => request('/api/auto-trading/tick', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify({ reason: 'ui_manual_tick' }) }),
  executeMultiTarget: (payload: unknown) => request('/api/trades/execute-multi-target', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload) }),
  closeTrade: (payload: unknown) => request('/api/trades/close', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  modifyTrade: (payload: unknown) => request('/api/trades/modify', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  partialClose: (payload: unknown) => request('/api/trades/partial-close', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  modifyTrailingStop: (payload: unknown) => request('/api/trades/modify-trailing-stop', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  manageLiveTrade: (payload: unknown) => request('/api/trades/manage-live', { action: 'HOLD' }, { method: 'POST', body: JSON.stringify(payload) }),

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
  executePyramiding: (payload: unknown) => request('/api/pyramiding/execute', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  tradeManagementStatus: () => request('/api/trade-management/status', {}),
  brokerExecutionQuality: () => request('/api/broker/execution-quality', {}),
  probabilityCalibration: () => request('/api/calibration/probability', []),
  overfittingGuard: () => request('/api/overfitting/guard', {}),
  killSwitchStatus: () => request('/api/emergency/kill-switch', {}),
  uiFeatureMap: () => request('/api/ui/feature-map', {}),
  walkForward: (payload: unknown) => request('/api/backtest/walk-forward', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  monteCarlo: (payload: unknown) => request('/api/backtest/monte-carlo', { ok: false }, { method: 'POST', body: JSON.stringify(payload) }),
  backtestRun: (payload: unknown) => request('/api/backtest/run', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  backtestValidate: (payload: unknown) => request('/api/backtest/validate', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  journalDecisions: (category?: string, limit = 250) => request(`/api/journal/decisions?category=${encodeURIComponent(category || 'all')}&limit=${limit}`, { ok: false, items: [], counts: {} }),
  labRun: (payload?: unknown) => request('/api/lab/run', { ok: false }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  labStatus: () => request('/api/lab/status', { ok: false }),
  labInstall: (id: string) => request('/api/lab/install', { ok: false }, { method: 'POST', body: JSON.stringify({ id }) }),
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
  testTelegram: (payload: unknown) => request('/api/telegram/test', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  telegramRecap: (payload: unknown) => request('/api/telegram/recap', { ok: false, message: 'Backend unavailable.' }, { method: 'POST', body: JSON.stringify(payload || {}) }),
  aiMonitor: () => request('/api/ai/monitor', { ok: false }),
  createBackup: () => request('/api/replay/store', { ok: false }, { method: 'POST', body: JSON.stringify({ event: 'BACKUP_REQUEST', timestamp: new Date().toISOString() }) }),

  notifications: () => request('/api/notifications', { ok: true, unread: 0, items: [] }),
  clearNotifications: () => request('/api/notifications/clear', { ok: true, unread: 0, items: [] }, { method: 'POST', body: JSON.stringify({}) }),
  docsInfo: () => request('/api/docs-info', {}),
};
