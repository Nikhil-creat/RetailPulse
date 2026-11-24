import { banner, chip, dataTable, errorBox, meter, pageHead, statusChip, withLoading } from '../ui.js';
import { clear, el, fmtNum, titleCase } from '../util.js';

const GUARDS = [
  ['SQL injection / destructive SQL', 'SELECT-only text checks, read-only connection, SQLite authorizer allow-listing tables and functions', 'Attack test-suite (DROP, stacked statements, comments, PRAGMA, CTE shadowing)'],
  ['Runaway queries', '3-second progress-handler timeout, 200-row cap, query length cap', 'Recursive-CTE timeout test'],
  ['Customer PII', 'email/phone read as NULL at the authorizer; output masking; PII dropped from exports', 'PII tests across SQL, RAG, agent and API'],
  ['Prompt injection', 'Heuristic refusal before any tool runs; LLM plans validated against a tool allow-list', 'Agent + eval tests'],
  ['Unauthorised use', 'Hashed API keys, constant-time compare, roles (viewer < analyst < admin), prod refuses to start without keys', 'Role-matrix + live-server tests'],
  ['Abuse', 'Token-bucket rate limits per IP and per key, body-size caps, strict validation', 'Rate-limit, 413/415/422 tests'],
  ['Tampered logs', 'Hash-chained audit log; verification pinpoints the first altered line', 'Tamper test'],
  ['Web attacks', 'Strict CSP (no inline script/style), nosniff, frame deny, no-store on API, safe static serving', 'Traversal + CSP tests'],
];

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('Trust & MLOps', 'Security controls, model registry with promotion gates, drift monitoring and quality checks, with the evidence behind each.'));
  const guardTable = dataTable([{ label: 'Threat' }, { label: 'Control' }, { label: 'Verified by' }], GUARDS);
  guardTable.classList.add('guard');
  const reg = el('div'), drift = el('div', { class: 'card' }), gates = el('div', { class: 'card' }), live = el('div', { class: 'card' });

  root.append(el('section', { class: 'card' }, el('h3', {}, 'Security controls'), el('p', { class: 'sub' }, 'Known gaps are documented in SECURITY.md: heuristic injection detection, in-memory rate limiter, no TLS in the app itself.'),
    el('div', { class: 'table-wrap' }, guardTable)),
    el('h2', { class: 'section-title' }, 'Live security checks'), live,
    el('h2', { class: 'section-title' }, 'Model registry'), reg,
    el('div', { class: 'grid cols-2', style: { marginTop: '16px' } }, drift, gates));

  // live checks
  if (mode === 'demo') live.append(banner('The audit log belongs to a running server, so it is not part of the static demo.', 'info', 'Static demo.'));
  else {
    const out = el('div', { class: 'stack' });
    const v = el('button', { class: 'btn', type: 'button' }, 'Verify audit chain');
    const t = el('button', { class: 'btn', type: 'button' }, 'Show recent entries');
    v.addEventListener('click', async () => {
      clear(out);
      try { const r = await api.auditVerify(); out.append(banner(r.ok ? 'Every audit entry links to the previous one. No tampering detected.' : `Tampering detected at line ${r.first_bad_line}.`, r.ok ? 'ok' : 'error', r.ok ? 'Chain intact.' : 'Chain broken!')); } catch (e) { out.append(errorBox(e)); }
    });
    t.addEventListener('click', async () => {
      clear(out);
      try {
        const r = await api.auditTail(15);
        out.append(el('div', { class: 'table-wrap' }, dataTable([{ label: 'Time' }, { label: 'Actor' }, { label: 'Action' }, { label: 'Detail' }, { label: 'Hash' }],
          r.entries.slice().reverse().map((e) => [e.ts.replace('T', ' ').slice(0, 19), e.actor, e.action, JSON.stringify(e.detail).slice(0, 80), e.hash.slice(0, 10) + '…']))));
      } catch (e) { out.append(errorBox(e)); }
    });
    live.append(el('div', { class: 'row' }, v, t, el('span', { class: 'sub' }, 'Needs the admin role.')), out);
  }

  // registry
  await withLoading(reg, () => api.models(), ({ latest }) => {
    reg.append(el('div', { class: 'grid cols-3' }, Object.values(latest).map((m) => el('section', { class: 'card' },
      el('div', { class: 'row' }, el('h3', {}, titleCase(m.model)), chip(m.promoted ? 'promoted' : 'blocked', m.promoted ? 'ok' : 'bad')),
      el('p', { class: 'sub' }, `${m.version} · data ${m.data_fingerprint}`),
      el('dl', { class: 'kv' }, Object.entries(m.metrics).flatMap(([k, v]) => [el('dt', {}, titleCase(k)), el('dd', {}, fmtNum(v, 3))])),
      el('p', { class: 'sub', style: { marginTop: '10px' } }, 'Promotion gates'),
      el('ul', { class: 'list-clean' }, Object.entries(m.gates).map(([g, ok]) => el('li', {}, chip(ok ? '✓' : '✕', ok ? 'ok' : 'bad'), ' ', titleCase(g))))))));
  });

  // drift
  await withLoading(drift, () => api.monitoring(), (d) => {
    drift.append(el('div', { class: 'row' }, el('h3', {}, 'Data drift (PSI)'), statusChip(d.overall_status)),
      el('p', { class: 'sub' }, `Population Stability Index: below ${d.thresholds.stable_below} stable, ${d.thresholds.stable_below}–${d.thresholds.significant_from} moderate, above ${d.thresholds.significant_from} significant. ${d.note}`),
      el('p', {}, el('b', {}, 'Order value '), `(${d.order_value.reference} vs ${d.order_value.current}): PSI ${fmtNum(d.order_value.psi, 3)} `, statusChip(d.order_value.status)),
      el('div', { class: 'table-wrap' }, dataTable([{ label: 'Churn feature' }, { label: 'PSI', align: 'right', fmt: (v) => fmtNum(v, 3) }, { label: '', fmt: (v) => meter(Math.min(1, v / 0.5), v >= 0.25 ? 'bad' : v >= 0.1 ? 'warn' : 'ok') }, { label: 'Status', fmt: (v) => statusChip(v) }],
        d.churn_features.map((f) => [titleCase(f.feature), f.psi, f.psi, f.status]))));
  });

  // quality gates + evals
  await withLoading(gates, () => api.summary(), (s) => {
    gates.append(el('h3', {}, 'Data-quality gates'), el('p', { class: 'sub' }, 'The pipeline stops if any check is non-zero.'),
      el('ul', { class: 'list-clean' }, Object.entries(s.data_quality.checks).map(([k, v]) => el('li', { class: 'row' }, chip(v === 0 ? '✓ 0' : `✕ ${v}`, v === 0 ? 'ok' : 'bad'), titleCase(k)))),
      el('h3', { style: { marginTop: '16px' } }, 'Evaluations'),
      el('ul', { class: 'list-clean' }, [
        el('li', {}, `RAG retrieval hit@3: ${s.evals.rag.hit_at_3} (MRR ${s.evals.rag.mrr}) on ${s.evals.rag.cases} questions`),
        el('li', {}, `Agent routing + refusals: ${s.evals.agent.passed}/${s.evals.agent.cases}`),
        el('li', { class: 'sub' }, 'Both eval sets were written by the project author, so treat them as regression tests, not independent benchmarks.')]));
  });
}
