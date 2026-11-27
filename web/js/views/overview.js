import { barChart, chartCard, lineChart } from '../charts.js';
import { banner, dataTable, errorBox, meter, pageHead, select, tile } from '../ui.js';
import { briefCard } from '../brief.js';
import { el, fmtINR, fmtInt, fmtMonth, fmtPct, titleCase } from '../util.js';

const DIMS = [['category', 'Category'], ['city', 'City'], ['channel', 'Channel'], ['payment', 'Payment'], ['age_band', 'Age band'], ['product', 'Product']];
const METRICS = [['revenue', 'Net revenue'], ['profit', 'Profit'], ['orders', 'Orders'], ['units', 'Units'], ['margin', 'Margin %']];
const MONEY = new Set(['revenue', 'profit']);
const fmtFor = (m) => (MONEY.has(m) ? fmtINR : m === 'margin' ? (v) => fmtPct(v) : fmtInt);

function festiveRanges(months) {
  const out = [];
  let start = null;
  months.forEach((m, i) => {
    const f = ['10', '11'].includes(m.slice(5, 7));
    if (f && start == null) start = i;
    if ((!f || i === months.length - 1) && start != null) { out.push([start, f ? i : i - 1]); start = null; }
  });
  return out;
}

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('Business overview', 'Net revenue excludes returned orders. Every figure comes from the SQL star-schema warehouse.'));
  if (mode === 'demo') root.appendChild(banner('Pre-exported results from the same pipeline. Charts and tables are real; free-form queries need the live backend.', 'info', 'Static demo.'));
  const tiles = el('div', { class: 'tiles' });
  const grid = el('div', { class: 'grid cols-2' });
  const hl = el('div', { class: 'card' });
  hl.append(el('h3', { style: { marginBottom: '10px' } }, 'Pipeline health'));
  root.append(tiles, briefCard(api, mode), grid);

  try {
    const [k, monthly] = await Promise.all([api.kpis(), api.monthly()]);
    tiles.append(
      tile('Net revenue', fmtINR(k.net_revenue), `${k.first_date} → ${k.last_date}`),
      tile('Net profit', fmtINR(k.net_profit), `${fmtPct(k.profit_margin_pct)} margin`),
      tile('Orders', fmtInt(k.orders)), tile('Customers', fmtInt(k.customers)),
      tile('Avg order value', fmtINR(k.avg_order_value)), tile('Return rate', fmtPct(k.return_rate_pct)));

    const months = monthly.rows.map((r) => r[0]);
    const rev = monthly.rows.map((r) => r[1]);
    const trend = chartCard({
      title: 'Net revenue per month', subtitle: 'Shaded months are the Oct–Nov festive season',
      draw: (host) => lineChart(host, { labels: months, series: [{ name: 'Net revenue', cls: 's1', values: rev }], shade: festiveRanges(months),
        yFmt: fmtINR, xFmt: fmtMonth, xFmtFull: fmtMonth, ariaLabel: 'Net revenue per month' }),
      table: () => dataTable([{ label: 'Month' }, { label: 'Net revenue', align: 'right', fmt: fmtINR }, { label: 'Profit', align: 'right', fmt: fmtINR }, { label: 'Orders', align: 'right', fmt: fmtInt }],
        monthly.rows.map((r) => [r[0], r[1], r[3], r[2]])),
    });
    trend.el.classList.add('span-all');

    let dim = 'category', metric = 'revenue', rows = [];
    const card = chartCard({
      title: 'Breakdown', subtitle: 'Top 10, returned orders excluded',
      actions: [select(DIMS, dim, async (v) => { dim = v; await load(); }, 'Dimension'), select(METRICS, metric, async (v) => { metric = v; await load(); }, 'Metric')],
      draw: (host) => barChart(host, { items: rows.map((r) => ({ label: String(r[0]), value: r[1] })), valueFmt: fmtFor(metric), valueName: titleCase(metric), ariaLabel: `${dim} by ${metric}` }),
      table: () => dataTable([{ label: titleCase(dim) }, { label: titleCase(metric), align: 'right', fmt: fmtFor(metric) }], rows),
    });
    async function load() {
      try { rows = (await api.top(dim, metric, 10)).rows; card.redraw(); } catch (e) { card.body.replaceChildren(errorBox(e, true)); }
    }
    await load();
    grid.append(trend.el, card.el, hl);
  } catch (e) {
    tiles.replaceWith(errorBox(e));
  }

  try {
    const s = await api.summary();
    const g = s.forecast.models.gradient_boosting, sn = s.forecast.models.seasonal_naive;
    const items = [
      [s.data_quality.ok, `Data-quality gates: ${Object.keys(s.data_quality.checks).length} checks, ${s.data_quality.ok ? 'all passed' : 'FAILED'}`],
      [g.wape_weekly_pct < sn.wape_weekly_pct, `Forecast weekly WAPE ${fmtPct(g.wape_weekly_pct)} vs ${fmtPct(sn.wape_weekly_pct)} for the seasonal-naive baseline (bias ${fmtPct(g.bias_pct)})`],
      [s.churn.roc_auc > s.churn.baseline_recency_auc, `Churn ROC AUC ${s.churn.roc_auc} vs ${s.churn.baseline_recency_auc} for a recency-only baseline (temporal validation)`],
      [s.evals.rag.hit_at_3 >= 0.85, `RAG retrieval hit@3 ${s.evals.rag.hit_at_3} on ${s.evals.rag.cases} questions (small, self-written set)`],
      [s.evals.agent.passed === s.evals.agent.cases, `Agent routing + guardrail cases: ${s.evals.agent.passed}/${s.evals.agent.cases}`],
      [true, `Top 20% of products earn ${fmtPct(s.pareto_top20_share_pct)} of net revenue`],
    ];
    hl.append(el('ul', { class: 'list-clean' }, items.map(([ok, text]) =>
      el('li', { class: 'row' }, el('span', { class: `chip ${ok ? 'ok' : 'warn'}` }, ok ? '✓ pass' : '! check'), el('span', {}, text)))));
  } catch (e) {
    hl.append(errorBox(e, true));
  }
}
