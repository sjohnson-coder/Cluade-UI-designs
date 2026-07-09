// App shell: navigation, hash routing, shared state.
import { api } from './api.js';
import { el } from './ui.js';
import { renderDashboard } from './views/dashboard.js';
import { renderScout } from './views/scout.js';
import { renderCVStudio } from './views/cvstudio.js';
import { renderNHS } from './views/nhs.js';
import { renderCockpit } from './views/cockpit.js';
import { renderTracker } from './views/tracker.js';
import { renderInterview } from './views/interview.js';
import { renderVault } from './views/vault.js';
import { renderSettings } from './views/settings.js';

export const state = { me: null, status: null, selectedJob: null };

const NAV = [
  { group: 'Workspace' },
  { id: 'dashboard', label: 'Dashboard', ic: '◈', render: renderDashboard },
  { id: 'scout', label: 'Job Scout', ic: '🔍', render: renderScout },
  { id: 'tracker', label: 'Tracker', ic: '▦', render: renderTracker },
  { group: 'Studios' },
  { id: 'cv', label: 'CV Studio', ic: '✎', render: renderCVStudio },
  { id: 'nhs', label: 'NHS Studio', ic: '✚', render: renderNHS },
  { id: 'interview', label: 'Interview Coach', ic: '◍', render: renderInterview },
  { group: 'Apply' },
  { id: 'cockpit', label: 'Application Cockpit', ic: '⛶', render: renderCockpit },
  { group: 'Account' },
  { id: 'vault', label: 'Career Vault', ic: '🔐', render: renderVault },
  { id: 'settings', label: 'Settings', ic: '⚙', render: renderSettings },
];

function buildNav() {
  const nav = document.getElementById('nav');
  nav.innerHTML = '';
  NAV.forEach((item) => {
    if (item.group) { nav.appendChild(el(`<div class="nav-group">${item.group}</div>`)); return; }
    const a = el(`<a class="nav-item" href="#${item.id}" data-id="${item.id}">
      <span class="ic">${item.ic}</span><span>${item.label}</span></a>`);
    nav.appendChild(a);
  });
}

function setActive(id) {
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.id === id));
}

async function route() {
  const id = (location.hash.replace('#', '') || 'dashboard').split('/')[0];
  const item = NAV.find((n) => n.id === id) || NAV.find((n) => n.id === 'dashboard');
  setActive(item.id);
  const main = document.getElementById('main');
  document.getElementById('modalRoot').innerHTML = ''; // close any open modal on navigation
  document.getElementById('sidebar')?.classList.remove('open');
  main.scrollTop = 0;
  window.scrollTo(0, 0);
  try {
    await item.render(main, { param: location.hash.split('/')[1] });
  } catch (err) {
    main.innerHTML = `<div class="card pad"><h2>Something went wrong</h2><p class="muted">${err.message}</p></div>`;
    console.error(err);
  }
}

async function boot() {
  buildNav();
  window.addEventListener('hashchange', route);
  try {
    const [me, status] = await Promise.all([api.me(), api.status()]);
    state.me = me; state.status = status;
    renderProviderPill(status);
    renderAvatar(me);
  } catch (e) {
    console.error('Boot error', e);
  }
  route();
}

function renderProviderPill(status) {
  const pill = document.getElementById('providerPill');
  const ai = status?.ai || {};
  const on = ai.llm_enabled;
  pill.innerHTML = `<span class="dot" style="background:${on ? '#34d399' : '#22d3ee'};box-shadow:0 0 10px ${on ? '#34d399' : '#22d3ee'}"></span>
    <span>${on ? `LLM: ${ai.provider}` : 'Rule engine'} · live</span>`;
  pill.title = ai.note || '';
}

function renderAvatar(me) {
  const name = me?.user?.name || 'User';
  const initials = name.split(' ').map((w) => w[0]).slice(0, 2).join('');
  window.__avatar = initials;
}

boot();
