import { api, boot, hasKey, health, me, mode, refreshMe, setKey } from './api.js';
import { $, clear, el, toast } from './util.js';
import { banner, errorBox, loading } from './ui.js';

const ROUTES = {
  overview: ['Overview', './views/overview.js'],
  customers: ['Customers', './views/customers.js'],
  forecast: ['Forecast', './views/forecast.js'],
  assistant: ['Assistant', './views/assistant.js'],
  explorer: ['Explorer', './views/explorer.js'],
  vision: ['Vision', './views/vision.js'],
  trust: ['Trust & MLOps', './views/trust.js'],
  api: ['API', './views/api_docs.js'],
  about: ['About', './views/about.js'],
};

// ---------------------------------------------------------------- theme
function systemDark() { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
function effectiveTheme() { return document.documentElement.dataset.theme || (systemDark() ? 'dark' : 'light'); }
function paintThemeButton() {
  const dark = effectiveTheme() === 'dark';
  const b = $('#theme-btn');
  b.textContent = dark ? '☀' : '☾';
  b.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
}
function initTheme() {
  try { const t = localStorage.getItem('rp_theme'); if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; } catch { /* storage blocked */ }
  paintThemeButton();
  $('#theme-btn').addEventListener('click', () => {
    const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('rp_theme', next); } catch { /* ignore */ }
    paintThemeButton();
  });
  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paintThemeButton);
}

// ---------------------------------------------------------------- header / footer state
function paintChrome() {
  const m = mode(), h = health(), who = me();
  const mb = $('#mode-badge');
  mb.textContent = m === 'live' ? 'Live backend' : m === 'demo' ? 'Static demo' : 'Offline';
  mb.className = `badge ${m === 'live' ? 'live' : m === 'demo' ? 'demo' : ''}`;
  mb.title = m === 'demo' ? 'Showing pre-exported results. Run the backend for live queries.' : 'Connected to the RetailPulse API';
  const rb = $('#role-badge');
  rb.hidden = !who;
  if (who) { rb.textContent = m === 'demo' ? 'read-only' : who.role; }
  const kb = $('#key-btn');
  kb.hidden = !(m === 'live' && h && h.auth_required);
  kb.querySelector('span').textContent = hasKey() ? 'Key set' : 'API key';
  if (h && h.version) $('#ver').textContent = `v${h.version}`;
  const dot = $('#st-service'), txt = $('#st-service-text');
  if (m === 'offline') { dot.className = 'dot-status bad'; txt.textContent = 'Service unreachable'; }
  else if (h && h.ready === false) { dot.className = 'dot-status warn'; txt.textContent = 'Service starting (run the pipeline)'; }
  else { dot.className = 'dot-status ok'; txt.textContent = m === 'demo' ? 'Static demo (pre-exported data)' : 'Service healthy'; }
  const ad = $('#st-audit'), at = $('#st-audit-text');
  if (m === 'live' && h && h.audit_chain_ok != null) { ad.className = `dot-status ${h.audit_chain_ok ? 'ok' : 'bad'}`; at.textContent = h.audit_chain_ok ? 'Audit chain verified' : 'AUDIT CHAIN BROKEN'; }
  else { ad.className = 'dot-status'; at.textContent = 'Audit chain: live mode only'; }
}

function initKeyDialog() {
  const dlg = $('#key-dialog'), input = $('#key-input');
  $('#key-btn').addEventListener('click', () => { input.value = ''; dlg.showModal(); input.focus(); });
  $('#key-cancel').addEventListener('click', () => dlg.close());
  $('#key-clear').addEventListener('click', async () => { setKey(''); dlg.close(); await refreshMe(); paintChrome(); toast('Key removed from this tab'); render(); });
  $('#key-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    setKey(input.value);
    dlg.close();
    const who = await refreshMe();
    paintChrome();
    toast(who ? `Signed in as ${who.actor} (${who.role})` : 'That key was not accepted', who ? 'info' : 'error');
    render();
  });
}

// ---------------------------------------------------------------- router
let renderToken = 0;
function currentRoute() {
  const raw = (location.hash || '#/').replace(/^#\/?/, '').split('?')[0];
  return ROUTES[raw || 'overview'] ? raw || 'overview' : null;
}

async function render() {
  const root = $('#main');
  const key = currentRoute();
  const token = ++renderToken;
  document.querySelectorAll('#nav a').forEach((a) => {
    if (a.dataset.route === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  clear(root);
  if (!key) {
    root.appendChild(el('div', { class: 'card' }, el('h1', { id: 'page-title', tabindex: '-1' }, 'Page not found'), el('p', {}, 'That page does not exist. '), el('a', { href: '#/' }, 'Go to the overview')));
    return;
  }
  if (mode() === 'offline') {
    root.appendChild(banner('The backend is not reachable and no static demo data was found. Start it with `python -m retailpulse.cli serve` and reload.', 'error', 'Offline'));
    return;
  }
  const [name, path] = ROUTES[key];
  document.title = `${name} · RetailPulse`;
  root.appendChild(loading('Loading page'));
  try {
    const mod = await import(path);
    if (token !== renderToken) return;
    clear(root);
    await mod.render(root, { api, mode: mode(), me: me(), health: health(), hasKey: hasKey() });
    if (token !== renderToken) return;
    const h1 = $('#page-title');
    if (h1) h1.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } catch (e) {
    if (token !== renderToken) return;
    clear(root);
    root.appendChild(errorBox(e));
  }
}

async function main() {
  initTheme();
  initKeyDialog();
  await boot();
  paintChrome();
  window.addEventListener('hashchange', render);
  await render();
  if (mode() === 'live' && health() && health().auth_required && !me()) {
    toast('This server needs an API key. Use the key button in the header.', 'info');
  }
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* optional enhancement */ });
  }
}

main();
