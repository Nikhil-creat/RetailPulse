import { chartCard, lineChart } from '../charts.js';
import { banner, chip, dataTable, errorBox, pageHead, segmented, tile, withLoading } from '../ui.js';
import { el, fmtDate, fmtDateFull, fmtINR, fmtInt, fmtNum, fmtPct } from '../util.js';

const NAMES = { gradient_boosting: 'Gradient boosting (this model)', seasonal_naive: 'Seasonal naive (baseline)', moving_average_28d: '28-day moving average (baseline)' };

export async function render(root, { api }) {
  root.appendChild(pageHead('Demand forecast', 'Daily net revenue forecast with an empirical range, a backtest against simple baselines, and anomaly detection.'));
  const tiles = el('div', { class: 'tiles' }), chartHost = el('div'), models = el('div', { class: 'card' }), anom = el('div', { class: 'card' });
  root.append(el('div', { class: 'row' }, segmented([[14, '14 days'], [30, '30 days'], [60, '60 days']], 30, (v) => { horizon = v; draw(); }, 'Forecast horizon')), el('div', { class: 'stack' }, tiles, chartHost, models, anom));
  let horizon = 30, data = null, card = null;

  function draw() {
    if (!data) return;
    const rows = data.rows.slice(0, horizon);
    const total = rows.reduce((a, r) => a + r.forecast, 0);
    const lo = rows.reduce((a, r) => a + r.lower, 0), hi = rows.reduce((a, r) => a + r.upper, 0);
    tiles.replaceChildren(tile(`Next ${horizon} days`, fmtINR(total), 'expected net revenue'), tile('Daily average', fmtINR(total / rows.length)),
      tile('Plausible range', `${fmtINR(lo)} – ${fmtINR(hi)}`, 'empirical, not guaranteed'), tile('Backtest weekly WAPE', fmtPct(data.backtest_wape_weekly_pct)));
    const hist = data.history;
    const labels = hist.map((h) => h.date).concat(rows.map((r) => r.date));
    const nh = hist.length, pad = (arr, left) => (left ? Array(nh).fill(null).concat(arr) : arr.concat(Array(rows.length).fill(null)));
    const upper = pad(rows.map((r) => r.upper), true), lower = pad(rows.map((r) => r.lower), true);
    card = chartCard({
      title: 'Actual vs forecast', subtitle: 'Last 45 days of actuals, then the forecast with its range',
      draw: (host) => lineChart(host, { labels, series: [{ name: 'Actual', cls: 's1', values: pad(hist.map((h) => h.revenue), false) }, { name: 'Forecast', cls: 's2', dashed: true, values: pad(rows.map((r) => r.forecast), true) }],
        band: { upper, lower, cls: 's2' }, yFmt: fmtINR, xFmt: fmtDate, xFmtFull: fmtDateFull, ariaLabel: 'Actual and forecast daily net revenue' }),
      table: () => dataTable([{ label: 'Date' }, { label: 'Forecast', align: 'right', fmt: fmtINR }, { label: 'Low', align: 'right', fmt: fmtINR }, { label: 'High', align: 'right', fmt: fmtINR }], rows.map((r) => [r.date, r.forecast, r.lower, r.upper])),
    });
    chartHost.replaceChildren(card.el);
  }

  try { data = await api.forecast(60); draw(); } catch (e) { chartHost.replaceChildren(errorBox(e)); }

  await withLoading(models, () => api.summary(), (s) => {
    const m = s.forecast.models, best = s.forecast.best_model, g = m.gradient_boosting;
    models.append(el('h3', {}, `Backtest on the last ${s.forecast.holdout_days} days`), el('p', { class: 'sub' }, 'Recursive multi-step forecast: predictions feed later lag features, so errors can accumulate. Lower WAPE is better.'),
      el('div', { class: 'table-wrap' }, dataTable([{ label: 'Model' }, { label: 'Weekly WAPE', align: 'right', fmt: (v) => fmtPct(v) }, { label: 'Daily WAPE', align: 'right', fmt: (v) => fmtPct(v) }, { label: 'MAE', align: 'right', fmt: fmtINR }, { label: 'Bias', align: 'right', fmt: (v) => fmtPct(v) }, { label: '' }],
        Object.entries(m).map(([k, v]) => [NAMES[k] || k, v.wape_weekly_pct, v.wape_daily_pct, v.mae, v.bias_pct, k === best ? chip('best', 'ok') : '']))),
      el('div', { style: { marginTop: '12px' } }, banner(`The model under-forecasts by ${fmtNum(Math.abs(g.bias_pct), 1)}% on this window: flash-sale spikes and growth are hard for lag features to anticipate. A promo calendar feature is the first fix. Weekly totals are more reliable than single days.`, 'warn', 'Known limitation.')));
  });

  await withLoading(anom, () => api.anomalies(), ({ rows, unit }) => {
    const top = rows.slice().sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, 12);
    anom.append(el('h3', {}, 'Flagged anomalous days'), el('p', { class: 'sub' }, `Robust z-score of each day's ${unit} vs the same weekday over the prior 8 weeks (|z| > 3.5). ${rows.length} days flagged; strongest ${top.length} shown. Flash sales and promotions legitimately appear as spikes.`),
      el('div', { class: 'table-wrap' }, dataTable([{ label: 'Date', fmt: fmtDateFull }, { label: 'Orders', align: 'right', fmt: fmtInt }, { label: 'Expected', align: 'right', fmt: (v) => fmtNum(v, 0) }, { label: 'z', align: 'right', fmt: (v) => fmtNum(v, 1) }, { label: 'Kind', fmt: (v) => chip(v, v === 'spike' ? 'warn' : 'bad') }],
        top.map((r) => [r.date, r.revenue, r.expected, r.z, r.kind]))));
  });
}
