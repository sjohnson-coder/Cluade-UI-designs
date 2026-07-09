// Shared rendering helpers and small components used across views.

export const el = (html) => {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

export const esc = (s = '') =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const money = (min, max, cur = 'GBP') => {
  const sym = cur === 'GBP' ? '£' : cur === 'USD' ? '$' : '';
  if (!min && !max) return 'Salary not stated';
  const f = (n) => sym + Number(n).toLocaleString();
  return min && max ? `${f(min)} – ${f(max)}` : f(min || max);
};

export const bandClass = (score) => (score >= 70 ? 'high' : score >= 45 ? 'mod' : 'low');
export const ringClass = (score) => (score >= 70 ? 'emerald' : score >= 45 ? 'amber' : 'rose');

export const ring = (score, label = '') => `
  <div class="ring ${ringClass(score)}" style="--p:${score}">
    <b>${score}</b>${label ? `<small>${label}</small>` : ''}
  </div>`;

export const meter = (pct, variant = '') =>
  `<div class="meter ${variant}"><i style="width:${Math.max(3, Math.min(100, pct))}%"></i></div>`;

export const badge = (text, cls = 'ghost') => `<span class="badge ${cls}">${esc(text)}</span>`;

export const confidenceBadge = (score, band) => {
  const cls = bandClass(score);
  const dotc = cls === 'high' ? '#34d399' : cls === 'mod' ? '#fbbf24' : '#fb7185';
  return `<span class="badge ${cls}"><span class="d" style="background:${dotc}"></span>Sponsor ${score} · ${band}</span>`;
};

export function toast(msg, kind = 'info') {
  const t = el(`<div class="notice ${kind === 'error' ? 'warn' : kind === 'success' ? 'safe' : 'info'}"
    style="position:fixed;bottom:24px;right:24px;z-index:200;max-width:340px;box-shadow:var(--shadow)">
    <span>${kind === 'success' ? '✓' : kind === 'error' ? '⚠' : 'ℹ'}</span><span>${esc(msg)}</span></div>`);
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; }, 2600);
  setTimeout(() => t.remove(), 3000);
}

export function openModal(innerHtml, { wide = false } = {}) {
  const root = document.getElementById('modalRoot');
  const bg = el(`<div class="modal-bg"><div class="card modal fade-in" style="${wide ? 'width:min(920px,100%)' : ''}">
    <button class="btn icon close" aria-label="Close">✕</button>${innerHtml}</div></div>`);
  bg.addEventListener('click', (e) => { if (e.target === bg) close(); });
  bg.querySelector('.close').addEventListener('click', close);
  function close() { bg.remove(); }
  root.appendChild(bg);
  return { close, root: bg.querySelector('.modal') };
}

export const loading = (label = 'Working…') =>
  `<div class="center"><div style="text-align:center"><div class="spinner" style="margin:0 auto 12px"></div>
   <div class="muted" style="font-size:13px">${esc(label)}</div></div></div>`;

export const kwList = (words = [], cls = '') =>
  `<div class="tag-list">${words.map((w) => `<span class="kw ${cls}">${esc(w)}</span>`).join('') || '<span class="dim" style="font-size:12px">None</span>'}</div>`;

export const topbar = (title, subtitle = '', actions = '') => {
  const initials = window.__avatar || 'AO';
  return `<div class="topbar fade-in">
    <div style="display:flex;align-items:center;gap:14px">
      <button class="btn icon menu-btn" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
      <div class="title"><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div>
    </div>
    <div class="actions">${actions}<div class="avatar" title="Amara Okafor">${esc(initials)}</div></div>
  </div>`;
};

export const daysLeft = (dateStr) => {
  if (!dateStr) return null;
  const d = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  return d;
};
