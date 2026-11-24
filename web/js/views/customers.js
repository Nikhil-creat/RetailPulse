import { barChart, chartCard, columnChart, heatmap } from '../charts.js';
import { banner, chip, dataTable, errorBox, meter, pageHead, withLoading } from '../ui.js';
import { clear, el, fmtINR, fmtInt, fmtNum, fmtPct } from '../util.js';

const SEG_HELP = {
  Champions: 'Recent, frequent buyers', Loyal: 'Frequent buyers', 'Potential Loyalist': 'Recent with some repeat purchases',
  'New / Promising': 'Recent, few orders', 'At Risk': 'Used to buy often, gone quiet', Hibernating: 'Long inactive, low frequency', 'Needs Attention': 'Middling recency and frequency',
};

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('Customers', 'RFM segments, churn risk, a no-PII customer 360 and cohort retention.'));
  const segHost = el('div'), lookup = el('div', { class: 'card' }), churnHost = el('div', { class: 'card' });
  const cohortHost = el('div', { class: 'card' }), basketHost = el('div', { class: 'card' });
  root.append(segHost, el('h2', { class: 'section-title' }, 'Customer 360 and churn risk'),
    el('div', { class: 'grid cols-2' }, lookup, churnHost),
    el('h2', { class: 'section-title' }, 'Retention and baskets'), el('div', { class: 'stack' }, cohortHost, basketHost));

  // ---- segments
  await withLoading(segHost, () => api.segments(), ({ rows }) => {
    const card = chartCard({
      title: 'Customers by RFM segment', subtitle: 'R = recency, F = frequency, M = monetary (1–5 scores)',
      draw: (host) => barChart(host, { items: rows.map((r) => ({ label: r.segment, value: r.customers,
        tip: [{ name: 'Share', value: fmtPct(r.customer_share_pct) }, { name: 'Avg net revenue', value: fmtINR(r.avg_monetary) }, { name: 'Avg orders', value: fmtNum(r.avg_frequency, 1) }, { name: 'Avg days since last order', value: fmtNum(r.avg_recency_days, 0) }] })),
        valueFmt: fmtInt, valueName: 'Customers', ariaLabel: 'Customers by RFM segment' }),
      table: () => dataTable([{ label: 'Segment' }, { label: 'Meaning' }, { label: 'Customers', align: 'right', fmt: fmtInt },
        { label: 'Share', align: 'right', fmt: (v) => fmtPct(v) }, { label: 'Avg net revenue', align: 'right', fmt: fmtINR }, { label: 'Avg orders', align: 'right', fmt: (v) => fmtNum(v, 1) }, { label: 'Avg recency (d)', align: 'right', fmt: (v) => fmtNum(v, 0) }],
        rows.map((r) => [r.segment, SEG_HELP[r.segment] || '', r.customers, r.customer_share_pct, r.avg_monetary, r.avg_frequency, r.avg_recency_days])),
    });
    segHost.appendChild(card.el);
  });

  // ---- customer 360
  const out = el('div', { class: 'stack' });
  const input = el('input', { class: 'input', type: 'number', min: '1', inputmode: 'numeric', placeholder: 'Customer key, e.g. 1042', 'aria-label': 'Customer key' });
  const go = el('button', { class: 'btn primary', type: 'button' }, 'Look up');
  async function show(key) {
    input.value = key;
    clear(out);
    await withLoading(out, () => api.customer(key), (c) => {
      out.append(el('div', { class: 'row' }, el('h3', {}, `Customer #${c.customer_key}`), c.segment ? chip(c.segment, 'ok') : null, chip(c.city), chip(`Age ${c.age_band}`)),
        el('dl', { class: 'kv' },
          el('dt', {}, 'Net revenue'), el('dd', {}, fmtINR(c.net_revenue)), el('dt', {}, 'Orders'), el('dd', {}, fmtInt(c.orders)),
          el('dt', {}, 'First → last order'), el('dd', {}, `${c.first_order} → ${c.last_order}`),
          el('dt', {}, 'RFM'), el('dd', {}, c.rfm ? `R${c.rfm.R} F${c.rfm.F} M${c.rfm.M} (${c.rfm.recency_days} days since last order)` : 'Not scored'),
          el('dt', {}, 'Churn risk'), el('dd', {}, c.churn ? el('span', { class: 'row' }, meter(c.churn.risk, c.churn.risk > 0.6 ? 'bad' : c.churn.risk > 0.35 ? 'warn' : 'ok'), `${Math.round(c.churn.risk * 100)}% · value at risk ${fmtINR(c.churn.value_at_risk)}`) : 'Not in the scored (recently active) population')));
      const cat = el('div', { class: 'chart-host' }), hist = el('div', { class: 'chart-host' });
      out.append(el('h3', {}, 'Top categories'), cat, el('h3', {}, 'Orders per month (last 12 active)'), hist);
      barChart(cat, { items: c.top_categories.map((t) => ({ label: t.category, value: t.net_revenue })), valueFmt: fmtINR, valueName: 'Net revenue', ariaLabel: 'Top categories for this customer' });
      columnChart(hist, { items: c.orders_by_month.map((m) => ({ label: m.month, value: m.orders })), valueFmt: fmtInt, valueName: 'Orders', ariaLabel: 'Orders per month' });
    });
  }
  go.addEventListener('click', () => { if (input.value) show(input.value); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && input.value) show(input.value); });
  lookup.append(el('h3', {}, 'Customer 360'), el('p', { class: 'sub' }, 'Aggregates only: email and phone are never exposed.'), el('div', { class: 'row' }, input, go), out);

  // ---- churn table (also feeds quick picks)
  await withLoading(churnHost, () => api.churnTop(12), ({ rows }) => {
    churnHost.append(el('h3', {}, 'Highest value at risk'), el('p', { class: 'sub' }, 'Risk of no order in the next 90 days × estimated annual value. Click a key to open the 360 view.'));
    const table = dataTable([{ label: 'Customer', fmt: (v) => { const b = el('button', { class: 'chip', type: 'button' }, `#${v}`); b.addEventListener('click', () => show(v)); return b; } },
      { label: 'Risk', fmt: (v) => el('span', { class: 'row' }, meter(v, v > 0.6 ? 'bad' : v > 0.35 ? 'warn' : 'ok'), `${Math.round(v * 100)}%`) },
      { label: 'Value at risk', align: 'right', fmt: fmtINR }, { label: 'Days idle', align: 'right', fmt: fmtInt }, { label: 'Orders', align: 'right', fmt: fmtInt }],
      rows.map((r) => [r.customer_key, r.churn_risk, r.value_at_risk, r.recency_days, r.frequency]));
    churnHost.appendChild(el('div', { class: 'table-wrap' }, table));
    if (rows.length) show(rows[0].customer_key); // open the highest value-at-risk customer so the panel is never empty
  });

  // ---- cohort heatmap
  await withLoading(cohortHost, () => api.cohort(), (c) => {
    const keep = c.months.filter((m) => m <= 12);
    const values = c.values.map((r) => r.slice(0, keep.length));
    const host = el('div', { class: 'chart-host heat-wrap' });
    cohortHost.append(el('div', { class: 'card-head' }, el('div', {}, el('h3', {}, 'Cohort retention'), el('p', { class: 'sub' }, 'Share of each first-order-month cohort that orders again N months later. Blank = not yet observable.'))), host);
    heatmap(host, { rows: c.cohorts, cols: keep, values, max: 1, fmt: (v) => `${Math.round(v * 100)}%`, cellText: (v) => Math.round(v * 100), colName: (m) => `Month ${m}`, ariaLabel: 'Cohort retention heatmap' });
  });

  // ---- basket
  await withLoading(basketHost, () => api.basket(8), ({ rows }) => {
    basketHost.append(el('h3', {}, 'Categories bought together'), el('p', { class: 'sub' }, 'Lift above 1 means the pair appears together more often than chance.'));
    basketHost.appendChild(el('div', { class: 'table-wrap' }, dataTable([{ label: 'If a basket has' }, { label: 'it also has' }, { label: 'Support', align: 'right', fmt: (v) => fmtPct(v * 100) },
      { label: 'Confidence', align: 'right', fmt: (v) => fmtPct(v * 100, 0) }, { label: 'Lift', align: 'right', fmt: (v) => el('b', {}, fmtNum(v, 2)) }],
      rows.map((r) => [r.antecedent, r.consequent, r.support, r.confidence, r.lift]))));
  });
}
