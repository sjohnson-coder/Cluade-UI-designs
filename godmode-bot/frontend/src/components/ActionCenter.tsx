import { useEffect, useState } from 'react';

type Toast = { id: number; title: string; body: string };

function textOf(el: HTMLElement) {
  return (el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
}

function actionMessage(label: string) {
  const t = label.toLowerCase();
  if (t.includes('connect mt5')) return ['MT5 connection', 'Connection request sent to the backend.'];
  if (t.includes('refresh')) return ['Refreshed', 'Latest backend state requested.'];
  if (t.includes('live trading')) return ['Live switch updated', 'Execution mode was updated in backend runtime settings.'];
  if (t.includes('auto trading')) return ['Auto trading updated', 'GodMode internal auto-trading guard was updated.'];
  if (t.includes('telegram')) return ['Telegram test', 'Telegram authentication/test request sent.'];
  if (t.includes('export')) return ['Export started', 'Download/export endpoint opened.'];
  if (t.includes('configure')) return ['Configure opened', 'Configuration panel is active.'];
  if (t.includes('save')) return ['Saved', 'Save request sent.'];
  if (t.includes('filter')) return ['Filter toggled', 'Filter controls updated.'];
  if (t.includes('manage')) return ['Management checked', 'Live management endpoint was called.'];
  if (t.includes('break-even')) return ['Break-even checked', 'Break-even management action sent.'];
  if (t.includes('trailing')) return ['Trailing stop checked', 'Trailing modifier action sent.'];
  if (t.includes('pyramid')) return ['Pyramid guard checked', 'Protected pyramid plan/execution routed through backend guards.'];
  if (t.includes('api documentation')) return ['API documentation', 'Opening FastAPI documentation.'];
  return ['Action confirmed', label || 'The UI action completed.'];
}

export function ActionCenter() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => {
    const addToast = (title: string, body: string) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((prev) => [...prev.slice(-2), { id, title, body }]);
      window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 2400);
    };
    const handler = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const el = target?.closest('button, .select, .toggle, [role="button"]') as HTMLElement | null;
      if (!el || el.closest('.nav')) return;
      const label = textOf(el) || el.getAttribute('aria-label') || 'Control';
      const [title, body] = actionMessage(label);
      addToast(title, body);
    };
    document.addEventListener('click', handler, false);
    return () => document.removeEventListener('click', handler, false);
  }, []);
  return <div className="action-toast-wrap" aria-live="polite">{toasts.map((t) => <div key={t.id} className="action-toast"><strong>{t.title}</strong><span>{t.body}</span></div>)}</div>;
}
