import { barChart, chartCard } from '../charts.js';
import { banner, dataTable, errorBox, pageHead, tile } from '../ui.js';
import { el, fmtINR, fmtNum, fmtPct } from '../util.js';

// What-if model on the last 12 months of the warehouse. It is deliberately simple and every assumption is a slider:
//   volume   = (1 + price change) ^ elasticity  x  (1 + discount lift per point x discount points)
//   revenue  = baseline revenue x price x (1 - extra discount) x volume x net-of-returns factor
//   cost     = baseline cost x volume x (1 + cost inflation)
export function scenario(base, a) {
  const p = 1 + a.price / 100, d = 1 - a.discount / 100;
  const volume = Math.pow(p, a.elasticity) * (1 + (a.liftPerPoint / 100) * a.discount);
  const net = (1 - (base.returnRate + a.returnDelta) / 100) / (1 - base.returnRate / 100);
  const revenue = base.revenue * p * d * volume * net;
  const cost = base.cost * volume * (1 + a.inflation / 100);
  const profit = revenue - cost;
  return { revenue, cost, profit, margin: revenue ? (profit / revenue) * 100 : 0, volume };
}

const delta = (now, was) => (was ? ((now / was - 1) * 100) : 0);
const sign = (x, d = 1) => (Math.abs(x) < 0.05 ? `${(0).toFixed(d)}%` : `${x > 0 ? '+' : ''}${x.toFixed(d)}%`);

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('Scenario planner', 'Change price, discount, returns and costs and see the effect on profit. The baseline is the last 12 months of the warehouse; the behavioural assumptions are yours.'));
  if (mode === 'demo') root.appendChild(banner('The baseline numbers are real pipeline outputs. The model itself runs in your browser.', 'info', 'Static demo.'));
  let base, observedLift = 0;
  try {
    const [m, k, de] = await Promise.all([api.monthly(), api.kpis(), api.named('discount_effectiveness')]);
    const last12 = m.rows.slice(-12);
    const revenue = last12.reduce((s, r) => s + r[1], 0), profit = last12.reduce((s, r) => s + r[3], 0);
    base = { revenue, profit, cost: revenue - profit, returnRate: k.return_rate_pct, from: last12[0][0], to: last12[last12.length - 1][0] };
    const zero = de.rows.find((r) => r[0] === 0), deep = de.rows.reduce((a, r) => (r[0] > a[0] ? r : a), de.rows[0]);
    if (zero && deep && deep[0] > 0) observedLift = (deep[2] / zero[2] - 1) * 100 / deep[0]; // % units per discount point
  } catch (e) { root.appendChild(errorBox(e)); return; }

  const A = { price: 0, discount: 0, returnDelta: 0, inflation: 0, elasticity: -1.2, liftPerPoint: +observedLift.toFixed(2) };
  const SL = [
    ['price', 'Price change', -20, 20, 1, '%', 'Change in list price'],
    ['discount', 'Extra discount', 0, 20, 1, '%', 'Additional discount on every sale'],
    ['returnDelta', 'Return rate change', -3, 5, 0.5, ' pp', `Baseline return rate is ${fmtPct(base.returnRate)}`],
    ['inflation', 'Cost inflation', 0, 15, 0.5, '%', 'Increase in cost per unit'],
    ['elasticity', 'Price elasticity of demand', -3, -0.3, 0.1, '', 'Assumption: -1.2 means +10% price loses about 11% of volume'],
    ['liftPerPoint', 'Volume lift per discount point', -1, 4, 0.1, '%', `Observed in this data: ${fmtNum(observedLift, 2)}% per point (discounts barely lift units here)`],
  ];
  const out = {};
  const controls = el('div', { class: 'card scenario-controls' }, el('h3', {}, 'Assumptions'));
  SL.forEach(([key, label, min, max, step, unit, hint]) => {
    const val = el('output', { for: `sc-${key}` }, '');
    const inp = el('input', { type: 'range', id: `sc-${key}`, min, max, step, value: A[key], 'aria-describedby': `sc-${key}-h` });
    const paint = () => { const n = +(+A[key]).toFixed(step < 1 ? 1 : 0); val.textContent = `${n > 0 && key !== 'elasticity' ? '+' : ''}${(Math.abs(n) < 0.05 ? 0 : n).toFixed(step < 1 ? 1 : 0)}${unit}`; };
    inp.addEventListener('input', () => { A[key] = +inp.value; paint(); draw(); });
    paint();
    controls.appendChild(el('div', { class: 'sc-row' }, el('label', { for: `sc-${key}` }, label), val, inp, el('p', { class: 'sub', id: `sc-${key}-h` }, hint)));
  });
  const reset = el('button', { class: 'btn', type: 'button' }, 'Reset');
  reset.addEventListener('click', () => { Object.assign(A, { price: 0, discount: 0, returnDelta: 0, inflation: 0, elasticity: -1.2, liftPerPoint: +observedLift.toFixed(2) }); controls.querySelectorAll('input').forEach((i) => { i.value = A[i.id.slice(3)]; i.dispatchEvent(new Event('input')); }); });
  controls.appendChild(reset);

  const tiles = el('div', { class: 'tiles' });
  const sens = el('div', { class: 'table-wrap' });
  const chart = chartCard({
    title: 'Profit: baseline vs scenario', subtitle: `Last 12 months (${base.from} to ${base.to})`,
    draw: (host) => { const s = scenario(base, A); return barChart(host, { items: [{ label: 'Baseline', value: Math.max(0, base.profit) }, { label: 'Scenario', value: Math.max(0, s.profit) }], valueFmt: fmtINR, valueName: 'Profit', ariaLabel: 'Baseline versus scenario profit' }); },
    table: () => { const s = scenario(base, A); return dataTable([{ label: 'Measure' }, { label: 'Baseline', align: 'right' }, { label: 'Scenario', align: 'right' }, { label: 'Change', align: 'right' }],
      [['Net revenue', fmtINR(base.revenue), fmtINR(s.revenue), sign(delta(s.revenue, base.revenue))], ['Cost', fmtINR(base.cost), fmtINR(s.cost), sign(delta(s.cost, base.cost))], ['Profit', fmtINR(base.profit), fmtINR(s.profit), sign(delta(s.profit, base.profit))]]); },
  });

  function draw() {
    const s = scenario(base, A);
    tiles.replaceChildren(
      tile('Net revenue', fmtINR(s.revenue), `${sign(delta(s.revenue, base.revenue))} vs baseline`),
      tile('Profit', fmtINR(s.profit), `${sign(delta(s.profit, base.profit))} vs baseline`),
      tile('Margin', fmtPct(s.margin), `baseline ${fmtPct((base.profit / base.revenue) * 100)}`),
      tile('Volume index', fmtNum(s.volume * 100, 0), '100 = baseline units'));
    chart.redraw();
    const prices = [-10, -5, 0, 5, 10], els = [-0.8, -1.2, -1.6, -2.0];
    sens.replaceChildren(dataTable([{ label: 'Price change' }, ...els.map((e) => ({ label: `e = ${e}`, align: 'right' }))],
      prices.map((pr) => [`${pr > 0 ? '+' : ''}${pr}%`, ...els.map((e) => sign(delta(scenario(base, { ...A, price: pr, elasticity: e }).profit, base.profit)))]),
      { caption: 'Profit change by price change and elasticity, other assumptions as set' }));
  }
  draw();
  root.append(tiles, el('div', { class: 'grid cols-2' }, controls, el('div', { class: 'stack' }, chart.el,
    el('section', { class: 'card' }, el('h3', {}, 'Sensitivity: profit change'), el('p', { class: 'sub' }, 'How much the answer depends on the elasticity you assume.'), sens))),
    banner('This is an assumption-driven what-if model, not a forecast. It ignores competitor reactions, mix shifts between categories and stock effects. Use it to compare options, then test the winner with a controlled experiment.', 'warn', 'Read before using.'));
}
