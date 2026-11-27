// Executive brief: findings computed by the backend from warehouse queries (no language model involved).
import { errorBox } from './ui.js';
import { ROOT } from './api.js';
import { el } from './util.js';

const SEV = {
  risk: { kind: 'bad', icon: '▲', label: 'Risk' },
  watch: { kind: 'warn', icon: '!', label: 'Watch' },
  opportunity: { kind: 'ok', icon: '↗', label: 'Opportunity' },
  good: { kind: 'ok', icon: '✓', label: 'Good news' },
  info: { kind: '', icon: '•', label: 'Outlook' },
};

export function briefCard(api, mode) {
  const body = el('div', { class: 'brief-list' }, el('p', { class: 'sub' }, 'Analysing the warehouse…'));
  const card = el('section', { class: 'card brief span-all', 'aria-labelledby': 'brief-title' },
    el('div', { class: 'card-head' },
      el('div', {}, el('h3', { id: 'brief-title' }, 'Executive brief'),
        el('p', { class: 'sub' }, 'Computed from the warehouse on every build. Each finding shows its evidence and a recommended action.'))),
    body);
  api.insights().then((d) => {
    body.replaceChildren(...d.findings.map((f) => {
      const s = SEV[f.severity] || SEV.info;
      const ev = el('details', { class: 'brief-evidence' }, el('summary', {}, 'Evidence'),
        el('dl', {}, Object.entries(f.evidence).flatMap(([k, v]) => [el('dt', {}, k.replace(/_/g, ' ')), el('dd', {}, typeof v === 'number' ? v.toLocaleString('en-IN') : String(v))])));
      const ask = mode === 'live'
        ? el('a', { class: 'btn', href: `${ROOT}ai-assistant/?q=${encodeURIComponent(f.question)}` }, 'Ask the agent')
        : null;
      return el('article', { class: `brief-item sev-${f.severity}` },
        el('div', { class: 'row' }, el('span', { class: `chip ${s.kind}` }, el('span', { 'aria-hidden': 'true' }, `${s.icon} `), s.label), el('h4', {}, f.title)),
        el('p', {}, f.detail),
        el('p', { class: 'brief-action' }, el('b', {}, 'Recommended action: '), f.action),
        el('div', { class: 'row' }, ev, ask));
    }));
    body.after(el('p', { class: 'sub' }, d.method));
  }).catch((e) => body.replaceChildren(errorBox(e, true)));
  return card;
}
