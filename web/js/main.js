import { ROOT, api, backend, boot, hasKey, health, me, mode, refreshMe, setKey } from './api.js';
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
  mb.textContent = m === 'live' ? 'Live backend' : m === 'demo' ? (backend() ? 'Demo data · sign in for live' : 'Static demo') : 'Offline';
  mb.className = `badge ${m === 'live' ? 'live' : m === 'demo' ? 'demo' : ''}`;
  mb.title = m === 'demo' ? 'Showing pre-exported results. Run the backend for live queries.' : 'Connected to the RetailPulse API';
  const rb = $('#role-badge');
  rb.hidden = !who;
  if (who) { rb.textContent = m === 'demo' ? 'read-only' : who.role; }
  const kb = $('#key-btn');
  kb.hidden = !(backend() && h && h.auth_required);
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
// Real URLs (/demand-forecast/), not hashes. The server (or the static export) returns a full HTML document for
// every page, so this code only takes over navigation after load. Page metadata lives in pages.json.
const BASE = ROOT.replace(/\/$/, '');
let META = null; // pages.json, or null if unavailable
const trimBase = (p) => (BASE && p.startsWith(BASE) ? p.slice(BASE.length) : p) || '/';
const normPath = (p) => {
  let x = trimBase(p).replace(/index\.html$/, '');
  if (!x.endsWith('/')) x += '/';
  return x;
};
// route key -> path, read from the server-rendered navigation so there is one list of URLs, not two.
function routePaths() {
  const map = {};
  document.querySelectorAll('#nav a[data-route]').forEach((a) => { map[a.dataset.route] = normPath(new URL(a.href, location.href).pathname); });
  return map;
}
function keyForPath(pathname) {
  const p = normPath(pathname);
  const hit = Object.entries(routePaths()).find(([, path]) => path === p);
  return hit ? hit[0] : null;
}
const currentKey = () => keyForPath(location.pathname);

async function loadMeta() {
  try {
    const r = await fetch(`${ROOT}pages.json`);
    if (!r.ok) return;
    const d = await r.json();
    META = { site: d.site, pages: Object.fromEntries(d.pages.map((p) => [p.key, p])), notFound: d.not_found };
  } catch { /* optional: navigation still works from the nav links */ }
}

function setMeta(selector, attr, value) {
  const n = document.querySelector(selector);
  if (n && value != null) n.setAttribute(attr, value);
}
function updateHead(key, page, fallbackTitle) {
  document.title = page ? page.title : fallbackTitle;
  if (!page) return;
  setMeta('meta[name="description"]', 'content', page.description);
  const siteRoot = (document.querySelector('meta[name="rp-site"]') || {}).content;
  if (siteRoot) {
    const url = siteRoot + page.path;
    setMeta('link[rel="canonical"]', 'href', url);
    setMeta('meta[property="og:url"]', 'content', url);
    setMeta('meta[property="og:image"]', 'content', `${siteRoot}/${page.social}`);
    setMeta('meta[name="twitter:image"]', 'content', `${siteRoot}/${page.social}`);
  }
  setMeta('meta[property="og:title"]', 'content', page.title);
  setMeta('meta[name="twitter:title"]', 'content', page.title);
  setMeta('meta[property="og:description"]', 'content', page.description);
  setMeta('meta[name="twitter:description"]', 'content', page.description);
  // Structured data was written for the page that was loaded; drop it rather than leave it describing another page.
  document.querySelectorAll('script[type="application/ld+json"]').forEach((n) => n.remove());
}
function updateCrumbs(key, page) {
  const nav = $('#crumbs');
  if (!nav) return;
  clear(nav);
  nav.hidden = key === 'overview';
  if (key === 'overview') return;
  nav.appendChild(el('ol', {}, el('li', {}, el('a', { href: `${BASE}/` }, 'Home')),
    el('li', { 'aria-current': 'page' }, page ? page.crumb : 'Page not found')));
}

let renderToken = 0;
async function render() {
  const root = $('#main');
  const key = currentKey();
  const token = ++renderToken;
  document.querySelectorAll('#nav a').forEach((a) => {
    if (a.dataset.route === key) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  const page = META ? (key ? META.pages[key] : META.notFound) : null;
  updateHead(key, page, key ? `${ROUTES[key][0]} | RetailPulse` : 'Page not found | RetailPulse');
  updateCrumbs(key || 'not_found', page);
  clear(root);
  if (!key) {
    root.appendChild(el('div', { class: 'card' }, el('h1', { id: 'page-title', tabindex: '-1' }, 'Page not found'),
      el('p', {}, 'That page does not exist or has moved. '), el('a', { href: `${BASE}/` }, 'Go to the overview')));
    return;
  }
  if (mode() === 'offline') {
    root.appendChild(banner('The backend is not reachable and no static demo data was found. Start it with `python -m retailpulse.cli serve` and reload.', 'error', 'Offline'));
    return;
  }
  const [, path] = ROUTES[key];
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

// Same-origin links to known pages navigate without a reload; everything else behaves normally.
function initLinks() {
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || a.target || a.hasAttribute('download')) return;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin) return;
    if (u.hash && u.pathname === location.pathname) return; // in-page anchor such as the skip link
    if (!keyForPath(u.pathname)) return;
    e.preventDefault();
    if (normPath(u.pathname) !== normPath(location.pathname)) history.pushState({}, '', u.pathname);
    render();
  });
  window.addEventListener('popstate', render);
}

// Old bookmarks like /#/forecast keep working.
function upgradeLegacyHash() {
  const m = /^#\/([a-z]*)/.exec(location.hash || '');
  if (!m) return;
  const target = routePaths()[m[1] || 'overview'];
  if (target) history.replaceState({}, '', `${BASE}${target}`);
}

async function main() {
  initTheme();
  initKeyDialog();
  await Promise.all([boot(), loadMeta()]);
  paintChrome();
  upgradeLegacyHash();
  window.addEventListener('hashchange', () => { upgradeLegacyHash(); render(); });
  initLinks();
  await render();
  if (backend() && health() && health().auth_required && !me()) {
    toast('Live backend found. Showing demo data: add your API key (key button) to switch to live.', 'info');
  }
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) {
    navigator.serviceWorker.register(`${ROOT}sw.js`).catch(() => { /* optional enhancement */ });
  }
}

main();
