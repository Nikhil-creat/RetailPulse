// Reusable UI pieces (all text via text nodes).
import { clear, el } from './util.js';

export function dataTable(columns, rows, opts = {}) {
  // columns: [{label, align?, fmt?(value,row)}] ; rows: array of arrays or objects (use opts.get)
  const head = el('tr', {}, columns.map((c) => el('th', { scope: 'col', class: c.align === 'right' ? 'num' : '' }, c.label)));
  const body = rows.map((r) => el('tr', {}, columns.map((c, i) => {
    const raw = Array.isArray(r) ? r[i] : r[c.key];
    const v = c.fmt ? c.fmt(raw, r) : raw;
    return el('td', { class: c.align === 'right' ? 'num' : '' }, v == null ? '–' : v);
  })));
  const t = el('table', { class: 'data' }, opts.caption ? el('caption', { class: 'sr-only' }, opts.caption) : null,
    el('thead', {}, head), el('tbody', {}, body));
  return t;
}

export function tile(label, value, sub) {
  return el('div', { class: 'tile' }, el('span', { class: 'tile-label' }, label), el('b', { class: 'tile-value' }, value),
    sub ? el('span', { class: 'tile-sub' }, sub) : null);
}

export function chip(text, kind = '') {
  return el('span', { class: `chip ${kind}` }, text);
}

export const STATUS = {
  stable: { kind: 'ok', icon: '✓', label: 'Stable' },
  moderate: { kind: 'warn', icon: '!', label: 'Moderate' },
  significant: { kind: 'bad', icon: '▲', label: 'Significant' },
};
export function statusChip(status) {
  const s = STATUS[status] || { kind: '', icon: '•', label: status };
  return el('span', { class: `chip ${s.kind}` }, el('span', { 'aria-hidden': 'true' }, `${s.icon} `), s.label);
}

export function meter(fraction, kind = '') {
  const fill = el('span', { class: `meter-fill ${kind}` });
  fill.style.width = `${Math.max(0, Math.min(1, fraction)) * 100}%`;
  return el('span', { class: 'meter', role: 'presentation' }, fill);
}

export function banner(text, kind = 'info', title) {
  return el('div', { class: `banner ${kind}`, role: kind === 'error' ? 'alert' : 'note' },
    title ? el('b', {}, title) : null, title ? ' ' : null, text);
}

export function pageHead(title, sub) {
  return el('header', { class: 'page-head' }, el('h1', { id: 'page-title', tabindex: '-1' }, title), sub ? el('p', { class: 'lede' }, sub) : null);
}

export function loading(label = 'Loading') {
  return el('div', { class: 'loading', role: 'status' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), label);
}

export function segmented(options, value, onChange, label) {
  const wrap = el('div', { class: 'segmented', role: 'group', 'aria-label': label });
  const btns = options.map(([val, text]) => {
    const b = el('button', { type: 'button', class: 'seg-btn', 'aria-pressed': String(val === value) }, text);
    b.addEventListener('click', () => {
      btns.forEach((x) => x.setAttribute('aria-pressed', 'false'));
      b.setAttribute('aria-pressed', 'true');
      onChange(val);
    });
    return b;
  });
  btns.forEach((b) => wrap.appendChild(b));
  return wrap;
}

export function select(options, value, onChange, label) {
  const s = el('select', { class: 'select', 'aria-label': label },
    options.map(([v, t]) => el('option', { value: v, ...(v === value ? { selected: true } : {}) }, t)));
  s.value = value;
  s.addEventListener('change', () => onChange(s.value));
  return s;
}

// Friendly, role-aware error display for failed API calls.
export function errorBox(err, hint) {
  const status = err && err.status;
  let title = 'Something went wrong';
  let text = (err && err.message) || 'Unknown error';
  if (status === 401) { title = 'API key needed'; text = 'This server requires an API key. Use the key button in the header.'; }
  if (status === 403) { title = 'Not allowed for your role'; }
  if (status === 429) { title = 'Slow down'; }
  if (status === 404 && hint) { title = 'Not available here'; }
  return banner(text, status === 403 || status === 404 ? 'warn' : 'error', title);
}

export function mount(root, ...nodes) {
  clear(root);
  nodes.forEach((n) => n && root.appendChild(n));
}

export async function withLoading(host, promiseFactory, render) {
  clear(host);
  host.appendChild(loading());
  try {
    const data = await promiseFactory();
    clear(host);
    render(data);
  } catch (e) {
    clear(host);
    host.appendChild(errorBox(e, true));
  }
}
