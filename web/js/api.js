// API adapter. LIVE mode talks to the backend; DEMO mode (e.g. GitHub Pages) reads pre-exported JSON from ./demo/.
// The API key lives in sessionStorage only (cleared when the tab closes) and is sent as a Bearer token.
import { sleep } from './util.js';

const state = { mode: 'live', health: null, me: null, key: readKey() };

function readKey() {
  try { return sessionStorage.getItem('rp_key') || ''; } catch { return ''; }
}
export function setKey(k) {
  state.key = (k || '').trim();
  try { state.key ? sessionStorage.setItem('rp_key', state.key) : sessionStorage.removeItem('rp_key'); } catch { /* storage blocked */ }
}
export const hasKey = () => !!state.key;
export const mode = () => state.mode;
export const health = () => state.health;
export const me = () => state.me;

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function http(path, { method = 'GET', body, headers = {} } = {}) {
  const h = { ...headers };
  if (state.key) h.Authorization = `Bearer ${state.key}`;
  let res;
  try {
    res = await fetch(path, { method, headers: h, body, cache: 'no-store' });
  } catch {
    throw new ApiError(0, 'Cannot reach the server.');
  }
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    const retry = res.headers.get('retry-after');
    throw new ApiError(res.status, (data && data.error) || (res.status === 429 && retry ? `Rate limited. Retry in ${retry}s.` : res.statusText) || 'Request failed');
  }
  return data;
}

async function demo(name) {
  const res = await fetch(`demo/${name}.json`, { cache: 'no-cache' });
  if (!res.ok) throw new ApiError(404, 'This view is not available in the static demo. Run the backend to try it live.');
  return res.json();
}

const get = (livePath, demoName) => (state.mode === 'demo' ? demo(demoName) : http(livePath));
const jsonPost = (path, payload) => http(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });

export async function boot() {
  try {
    const r = await fetch('health', { cache: 'no-store' });
    if (!r.ok || !(r.headers.get('content-type') || '').includes('json')) throw new Error('not live');
    state.health = await r.json();
    state.mode = 'live';
  } catch {
    try {
      state.health = await demo('health');
      state.mode = 'demo';
    } catch {
      state.mode = 'offline';
      return state;
    }
  }
  await refreshMe();
  return state;
}

export async function refreshMe() {
  if (state.mode === 'demo') { state.me = await demo('me').catch(() => null); return state.me; }
  try { state.me = await http('v1/me'); } catch { state.me = null; }
  return state.me;
}

export const api = {
  kpis: () => get('v1/kpis', 'kpis'),
  summary: () => get('v1/summary', 'summary'),
  monthly: () => get('v1/monthly', 'monthly'),
  top: (dim, metric, n = 10) => get(`v1/top?dimension=${encodeURIComponent(dim)}&metric=${encodeURIComponent(metric)}&n=${n}`, `top_${dim}_${metric}`),
  forecast: (h = 30) => get(`v1/forecast?horizon=${h}`, 'forecast'),
  segments: () => get('v1/segments', 'segments'),
  cohort: () => get('v1/cohort', 'cohort'),
  anomalies: () => get('v1/anomalies', 'anomalies'),
  basket: (n = 10) => get(`v1/basket?n=${n}`, 'basket'),
  namedList: () => get('v1/named', 'named'),
  named: (name) => get(`v1/named/${encodeURIComponent(name)}`, `named_${name}`),
  churnTop: (n = 15) => get(`v1/churn/top?n=${n}`, 'churn_top'),
  customer: (key) => get(`v1/customers/${encodeURIComponent(key)}`, `customer_${key}`),
  monitoring: () => get('v1/monitoring', 'monitoring'),
  models: () => get('v1/models', 'models'),
  openapi: () => get('openapi.json', 'openapi'),
  auditTail: (n = 20) => (state.mode === 'demo' ? Promise.reject(new ApiError(404, 'The audit log is not part of the static demo.')) : http(`v1/audit/tail?n=${n}`)),
  auditVerify: () => (state.mode === 'demo' ? Promise.reject(new ApiError(404, 'Not available in the static demo.')) : http('v1/audit/verify')),

  async guardExamples() { return state.mode === 'demo' ? demo('guard_examples') : null; },
  async sql(sql) {
    if (state.mode === 'demo') {
      const ex = (await demo('guard_examples')).find((e) => e.sql === sql);
      if (!ex) throw new ApiError(400, 'The demo only replays the example queries. Run the backend to execute your own.');
      if (ex.error) throw new ApiError(400, ex.error);
      return ex.result;
    }
    return jsonPost('v1/sql', { sql });
  },
  async ask(question) {
    if (state.mode === 'demo') {
      const ex = (await demo('examples')).find((e) => e.mode === 'rag' && e.question === question);
      if (!ex) throw new ApiError(400, 'The demo only replays the example questions.');
      return ex.result;
    }
    return jsonPost('v1/ask', { question });
  },
  async classify(blob, name) {
    if (state.mode === 'demo') {
      const hit = (await demo('samples')).find((s) => s.name === name);
      if (!hit) throw new ApiError(400, 'Uploads need the live backend. Click a sample tile instead.');
      return hit.result;
    }
    return http('v1/classify', { method: 'POST', headers: { 'content-type': blob.type || 'image/png' }, body: blob });
  },
  // Streams plan -> step -> final events. onEvent({type, ...}) is called as each arrives.
  async streamAgent(question, onEvent) {
    if (state.mode === 'demo') {
      const ex = (await demo('examples')).find((e) => e.mode === 'agent' && e.question === question);
      if (!ex) throw new ApiError(400, 'The demo only replays the example questions.');
      for (const ev of ex.events) { await sleep(ev.type === 'step' ? 450 : 200); onEvent(ev); }
      return;
    }
    const headers = { 'content-type': 'application/json' };
    if (state.key) headers.Authorization = `Bearer ${state.key}`;
    const res = await fetch('v1/agent/stream', { method: 'POST', headers, body: JSON.stringify({ question }) });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new ApiError(res.status, (data && data.error) || res.statusText);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const dataLine = block.split('\n').find((l) => l.startsWith('data: '));
        if (dataLine) { try { onEvent(JSON.parse(dataLine.slice(6))); } catch { /* ignore malformed event */ } }
      }
    }
  },
};
