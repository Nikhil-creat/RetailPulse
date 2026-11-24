// Tiny DOM + formatting helpers. All server data is rendered with textContent / text nodes (never innerHTML),
// which removes the XSS class of bugs by construction. Inline styles use the CSSOM (allowed by a strict CSP).
const SVG_NS = 'http://www.w3.org/2000/svg';

export const $ = (sel, root = document) => root.querySelector(sel);

function append(node, kids) {
  for (const k of kids) {
    if (k == null || k === false) continue;
    if (Array.isArray(k)) append(node, k);
    else node.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}

export function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(n.style, v);
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'hidden') n[k] = v;
    else n.setAttribute(k, v === true ? '' : String(v));
  }
  append(n, kids);
  return n;
}

export function svg(tag, attrs = {}, ...kids) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'text') n.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, String(v));
  }
  append(n, kids);
  return n;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// ---- formatting (Indian number system, INR)
export const fmtInt = (x) => (x == null ? '–' : Number(x).toLocaleString('en-IN', { maximumFractionDigits: 0 }));
export function fmtINR(x) {
  if (x == null || Number.isNaN(Number(x))) return '–';
  const v = Number(x), a = Math.abs(v);
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} cr`;
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}
export const fmtPct = (x, d = 1) => (x == null ? '–' : `${Number(x).toFixed(d)}%`);
export const fmtNum = (x, d = 2) => (x == null ? '–' : Number(x).toLocaleString('en-IN', { maximumFractionDigits: d }));
export const titleCase = (s) => String(s).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export function niceTicks(max, count = 4) {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const out = [];
  for (let v = 0; v <= max + step * 0.999; v += step) out.push(+v.toFixed(10));
  return out;
}

export function toCSV(columns, rows) {
  const q = (v) => {
    let s = v == null ? '' : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // neutralise spreadsheet formula injection
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.map(q).join(','), ...rows.map((r) => r.map(q).join(','))].join('\n');
}

export function download(name, text, type = 'text/csv') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el('a', { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function toast(message, kind = 'info') {
  const host = document.getElementById('toasts');
  if (!host) return;
  const t = el('div', { class: `toast ${kind}`, role: kind === 'error' ? 'alert' : 'status' }, message);
  host.appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- dates (ISO strings; no timezone surprises)
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const fmtMonth = (ym) => `${MON[+ym.slice(5, 7) - 1]} ${ym.slice(2, 4)}`;
export const fmtDate = (d) => `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]}`;
export const fmtDateFull = (d) => `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
