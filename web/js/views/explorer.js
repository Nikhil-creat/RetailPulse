import { banner, chip, dataTable, errorBox, pageHead, select } from '../ui.js';
import { clear, download, el, fmtInt, toCSV } from '../util.js';

const STARTER = "SELECT category, ROUND(SUM(revenue), 0) AS net_revenue\nFROM vw_sales\nWHERE is_returned = 0\nGROUP BY category\nORDER BY net_revenue DESC";
const ATTACKS = ['DROP TABLE returns', 'SELECT email, phone FROM dim_customer LIMIT 3', 'SELECT * FROM sqlite_master', 'SELECT 1; SELECT 2'];

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('Data explorer', 'The SQL library behind the dashboards, and a guarded console. Everything runs read-only through the same guard the agent uses.'));
  const demo = mode === 'demo';
  if (demo) root.appendChild(banner('Static demo: the console replays the example queries (including the attacks). Run the backend to execute your own SQL.', 'info', 'Static demo.'));
  const result = el('div', { class: 'stack' });
  const area = el('textarea', { rows: '6', spellcheck: 'false', 'aria-label': 'SQL query', maxlength: '2000', disabled: false }, STARTER);
  area.value = STARTER;
  const run = el('button', { class: 'btn primary', type: 'button' }, 'Run query');
  const names = el('div', { class: 'row' });

  function showResult(res, label) {
    clear(result);
    const cols = res.columns.map((c, i) => ({ label: c, align: typeof (res.rows[0] || [])[i] === 'number' ? 'right' : 'left', fmt: (v) => (typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : v) }));
    const csv = el('button', { class: 'btn', type: 'button' }, 'Download CSV');
    csv.addEventListener('click', () => download(`${label || 'result'}.csv`, toCSV(res.columns, res.rows)));
    result.append(el('div', { class: 'row' }, chip(`${fmtInt(res.row_count)} rows${res.truncated ? ' (truncated at the row cap)' : ''}`, res.truncated ? 'warn' : 'ok'),
      res.elapsed_ms != null ? chip(`${res.elapsed_ms} ms`) : null, csv),
      el('div', { class: 'table-wrap' }, dataTable(cols, res.rows)));
    const nulls = res.columns.filter((c) => /^(email|phone)$/i.test(c));
    if (nulls.length && res.rows.every((r) => res.columns.every((c, i) => !/^(email|phone)$/i.test(c) || r[i] == null))) {
      result.append(banner('The guard returned NULL for the PII columns: customer contact details can never be read through this interface.', 'ok', 'PII protected.'));
    }
  }
  function showError(e) {
    clear(result);
    result.append(e.status === 400 ? banner(e.message, 'warn', '🛡 Blocked by the SQL guard:') : errorBox(e));
  }
  async function runSql(sql) {
    run.disabled = true;
    try { showResult(await api.sql(sql), 'query'); } catch (e) { showError(e); } finally { run.disabled = false; }
  }
  run.addEventListener('click', () => runSql(area.value));
  area.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runSql(area.value); });

  const attackChips = el('div', { class: 'chips' }, ATTACKS.map((q) => {
    const b = el('button', { class: 'chip warn', type: 'button' }, `🛡 ${q}`);
    b.addEventListener('click', () => { area.value = q; runSql(q); });
    return b;
  }));
  const safeChip = el('button', { class: 'chip', type: 'button' }, 'Reset to the starter query');
  safeChip.addEventListener('click', () => { area.value = STARTER; runSql(STARTER); });

  let list = [];
  try { list = (await api.namedList()).queries; } catch (e) { names.appendChild(errorBox(e, true)); }
  if (list.length) {
    const sel = select(list.map((n) => [n, n.replace(/_/g, ' ')]), list[0], () => {}, 'Named query');
    const go = el('button', { class: 'btn', type: 'button' }, 'Run library query');
    go.addEventListener('click', async () => { try { showResult(await api.named(sel.value), sel.value); } catch (e) { showError(e); } });
    names.append(sel, go);
  }

  root.append(el('div', { class: 'stack' },
    el('section', { class: 'card' }, el('h3', {}, 'SQL library'), el('p', { class: 'sub' }, '15 named business questions (CTEs, window functions, LAG, RANK, Pareto…). Read the SQL in sql/analysis_queries.sql.'), names),
    el('section', { class: 'card' }, el('h3', {}, 'Guarded SQL console'),
      el('p', { class: 'sub' }, 'Single read-only SELECT/WITH over the allow-listed tables and views. 200-row cap, 3-second limit. Ctrl+Enter to run.'),
      area, el('div', { class: 'row', style: { marginTop: '10px' } }, run, safeChip),
      el('p', { class: 'sub', style: { marginTop: '12px' } }, 'Try to break it:'), attackChips),
    result));
}
