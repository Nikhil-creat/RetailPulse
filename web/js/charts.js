// Dependency-free SVG/HTML charts. Design rules: thin marks, rounded data-ends anchored to the baseline,
// recessive grid, legend for >=2 series (+ direct end labels), crosshair + tooltip on hover/touch,
// keyboard support, a table view for every chart, text in ink tokens (never series colour).
import { clear, el, niceTicks, svg } from './util.js';
import { dataTable } from './ui.js';

function makeTooltip(host) {
  const tip = el('div', { class: 'tooltip', 'aria-hidden': 'true', hidden: true });
  host.appendChild(tip);
  return {
    show(x, y, title, rows) {
      clear(tip);
      tip.appendChild(el('div', { class: 'tt-title' }, title));
      for (const r of rows) {
        tip.appendChild(el('div', { class: 'tt-row' }, r.cls ? el('span', { class: `swatch ${r.cls}` }) : null,
          el('span', { class: 'tt-name' }, r.name), el('b', {}, r.value)));
      }
      tip.hidden = false;
      const w = tip.offsetWidth, h = tip.offsetHeight, hw = host.clientWidth;
      let left = x + 14;
      if (left + w > hw - 4) left = Math.max(4, x - w - 14);
      tip.style.left = `${left}px`;
      tip.style.top = `${Math.max(4, Math.min(y - h / 2, host.clientHeight - h - 4))}px`;
    },
    hide() { tip.hidden = true; },
  };
}

function observe(host, draw) {
  let raf = 0, lastW = 0;
  const ro = new ResizeObserver(() => {
    if (Math.abs(host.clientWidth - lastW) < 2) return;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => { lastW = host.clientWidth; draw(); });
  });
  ro.observe(host);
  lastW = host.clientWidth;
  draw();
  return ro;
}

// ------------------------------------------------------------------ line chart (+ band, shading)
export function lineChart(host, o) {
  const H = o.height || 260;
  const labels = o.labels, n = labels.length;
  let idx = null;

  function draw() {
    clear(host);
    const W = Math.max(280, host.clientWidth);
    const multi = o.series.length > 1;
    const m = { l: 58, r: multi ? 72 : 16, t: 12, b: 30 };
    const w = W - m.l - m.r, h = H - m.t - m.b;
    const all = o.series.flatMap((s) => s.values).concat(o.band ? o.band.upper : []).filter((v) => v != null);
    const ticks = niceTicks(Math.max(...all, 1) * 1.04, 4);
    const top = ticks[ticks.length - 1];
    const x = (i) => m.l + (n === 1 ? 0 : (i * w) / (n - 1));
    const y = (v) => m.t + h - (v / top) * h;
    const step = n > 1 ? w / (n - 1) : w;

    if (multi) {
      host.appendChild(el('div', { class: 'legend' }, o.series.map((s) =>
        el('span', { class: 'legend-item' }, el('span', { class: `swatch ${s.cls}${s.dashed ? ' dashed' : ''}` }), s.name))));
    }
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: H, role: 'img', 'aria-label': o.ariaLabel || o.title || 'Line chart' });
    ticks.forEach((t) => {
      root.appendChild(svg('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: 'grid' }));
      root.appendChild(svg('text', { x: m.l - 8, y: y(t) + 4, class: 'axis-text', 'text-anchor': 'end', text: o.yFmt(t) }));
    });
    (o.shade || []).forEach(([a, b]) => {
      const x0 = Math.max(m.l, x(a) - step / 2), x1 = Math.min(W - m.r, x(b) + step / 2);
      root.appendChild(svg('rect', { x: x0, y: m.t, width: Math.max(0, x1 - x0), height: h, class: 'shade' }));
    });
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 78))));
    let lastLabelX = -1e9;
    labels.forEach((lb, i) => {
      const regular = i % every === 0;
      if (!regular && i !== n - 1) return;
      if (i === n - 1 && !regular && x(i) - lastLabelX < 64) return; // avoid colliding with the previous label
      lastLabelX = x(i);
      root.appendChild(svg('text', { x: x(i), y: H - 8, class: 'axis-text', 'text-anchor': i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle', text: o.xFmt ? o.xFmt(lb) : lb }));
    });
    if (o.band) {
      const pts = [];
      for (let i = 0; i < n; i++) if (o.band.upper[i] != null) pts.push([i, o.band.upper[i], o.band.lower[i]]);
      if (pts.length > 1) {
        const d = pts.map((p, k) => `${k ? 'L' : 'M'}${x(p[0])},${y(p[1])}`).join(' ')
          + pts.slice().reverse().map((p) => ` L${x(p[0])},${y(p[2])}`).join('') + ' Z';
        root.appendChild(svg('path', { d, class: `band ${o.band.cls}` }));
      }
    }
    const lastY = [];
    o.series.forEach((s) => {
      let d = '', pen = false;
      s.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
        pen = true;
      });
      root.appendChild(svg('path', { d, class: `line ${s.cls}${s.dashed ? ' dashed' : ''}` }));
      if (multi) {
        let li = s.values.length - 1;
        while (li > 0 && s.values[li] == null) li--;
        let ly = y(s.values[li]) + 4;
        while (lastY.some((p) => Math.abs(p - ly) < 13)) ly += 13;
        lastY.push(ly);
        root.appendChild(svg('text', { x: x(li) + 8, y: ly, class: 'axis-text strong', text: s.name }));
      }
    });
    const cross = svg('line', { y1: m.t, y2: m.t + h, class: 'crosshair', visibility: 'hidden' });
    const dots = o.series.map((s) => svg('circle', { r: 5, class: `dot f-${s.cls}`, visibility: 'hidden' }));
    root.append(cross, ...dots);
    host.appendChild(root);
    const tip = makeTooltip(host);

    function update(i, cx) {
      idx = i;
      if (i == null) { cross.setAttribute('visibility', 'hidden'); dots.forEach((d) => d.setAttribute('visibility', 'hidden')); tip.hide(); return; }
      const px = x(i);
      cross.setAttribute('x1', px); cross.setAttribute('x2', px); cross.setAttribute('visibility', 'visible');
      const rows = [];
      o.series.forEach((s, k) => {
        const v = s.values[i];
        if (v == null) { dots[k].setAttribute('visibility', 'hidden'); return; }
        dots[k].setAttribute('cx', px); dots[k].setAttribute('cy', y(v)); dots[k].setAttribute('visibility', 'visible');
        rows.push({ cls: s.cls, name: s.name, value: o.yFmtFull ? o.yFmtFull(v) : o.yFmt(v) });
      });
      if (o.band && o.band.upper[i] != null) rows.push({ name: 'Range', value: `${o.yFmt(o.band.lower[i])} – ${o.yFmt(o.band.upper[i])}` });
      tip.show(cx ?? px, m.t + h / 3, o.xFmtFull ? o.xFmtFull(labels[i]) : labels[i], rows);
    }
    const hit = svg('rect', { x: m.l, y: m.t, width: w, height: h, class: 'hit' });
    const pick = (e) => {
      const r = root.getBoundingClientRect();
      const px = ((e.clientX - r.left) / r.width) * W;
      return [Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (step || 1)))), px];
    };
    hit.addEventListener('pointermove', (e) => { const [i] = pick(e); update(i, x(i)); });
    hit.addEventListener('pointerdown', (e) => { const [i] = pick(e); update(i, x(i)); });
    hit.addEventListener('pointerleave', () => update(null));
    root.appendChild(hit);
    if (idx != null) update(Math.min(idx, n - 1));
  }

  host.setAttribute('tabindex', '0');
  host.setAttribute('role', 'group');
  host.setAttribute('aria-label', `${o.ariaLabel || o.title || 'Chart'}. Use left and right arrow keys to inspect values.`);
  host.addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Escape'].includes(e.key)) return;
    e.preventDefault();
    const cur = idx == null ? (e.key === 'ArrowLeft' ? n : -1) : idx;
    if (e.key === 'Escape') idx = null;
    else idx = Math.max(0, Math.min(n - 1, cur + (e.key === 'ArrowRight' ? 1 : -1)));
    draw();
  });
  return observe(host, draw);
}

// ------------------------------------------------------------------ horizontal bar chart
export function barChart(host, o) {
  const rowH = 34, barH = 14;
  function draw() {
    clear(host);
    const W = Math.max(280, host.clientWidth);
    const narrow = W < 460;
    const maxLabel = Math.max(...o.items.map((it) => it.label.length));
    const labelW = narrow ? 92 : Math.min(170, Math.max(80, maxLabel * 6.8 + 8));
    const valueW = 78;
    const maxChars = Math.floor((labelW - 8) / 6.4);
    const bw = Math.max(40, W - labelW - valueW - 8);
    const max = Math.max(...o.items.map((it) => it.value), 1e-9);
    const H = o.items.length * rowH + 6;
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: H, role: 'img', 'aria-label': o.ariaLabel || o.title || 'Bar chart' });
    const tip = makeTooltip(host);
    o.items.forEach((it, i) => {
      const cy = i * rowH + rowH / 2 + 3;
      const wv = Math.max(0, (it.value / max) * bw);
      const g = svg('g', { class: 'bar-row' });
      g.appendChild(svg('rect', { x: 0, y: cy - rowH / 2, width: W, height: rowH, class: 'row-hl' }));
      const lab = it.label.length > maxChars ? `${it.label.slice(0, maxChars - 1)}…` : it.label;
      g.appendChild(svg('text', { x: 4, y: cy + 4, class: 'axis-text strong', text: lab }));
      const x0 = labelW, y0 = cy - barH / 2;
      const r = Math.min(4, wv / 2);
      const d = wv < 2 ? '' : `M${x0},${y0} h${wv - r} a${r},${r} 0 0 1 ${r},${r} v${barH - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(wv - r)} z`;
      if (d) g.appendChild(svg('path', { d, class: `bar f-${o.cls || 's1'}` }));
      g.appendChild(svg('text', { x: x0 + wv + 8, y: cy + 4, class: 'value-text', text: o.valueFmt(it.value) }));
      const move = (e) => {
        const rect = host.getBoundingClientRect();
        tip.show(e.clientX - rect.left, cy, it.label, [{ name: o.valueName || 'Value', value: o.valueFmt(it.value) }, ...(it.tip || [])]);
      };
      g.addEventListener('pointermove', move);
      g.addEventListener('pointerdown', move);
      g.addEventListener('pointerleave', () => tip.hide());
      root.appendChild(g);
    });
    host.appendChild(root);
  }
  return observe(host, draw);
}

// ------------------------------------------------------------------ small column chart
export function columnChart(host, o) {
  const H = o.height || 130;
  function draw() {
    clear(host);
    const W = Math.max(240, host.clientWidth);
    const m = { l: 6, r: 6, t: 8, b: 22 };
    const n = o.items.length, w = W - m.l - m.r, h = H - m.t - m.b;
    const slot = w / n, bw = Math.max(3, Math.min(26, slot - 4));
    const max = Math.max(...o.items.map((it) => it.value), 1);
    const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', height: H, role: 'img', 'aria-label': o.ariaLabel || 'Column chart' });
    const tip = makeTooltip(host);
    root.appendChild(svg('line', { x1: m.l, x2: W - m.r, y1: m.t + h, y2: m.t + h, class: 'grid base' }));
    const every = Math.max(1, Math.ceil(n / Math.floor(w / 46)));
    o.items.forEach((it, i) => {
      const bh = Math.max(it.value > 0 ? 2 : 0, (it.value / max) * h);
      const x0 = m.l + slot * i + (slot - bw) / 2, y0 = m.t + h - bh, r = Math.min(3, bw / 2, bh);
      if (bh > 0) {
        root.appendChild(svg('path', { d: `M${x0},${m.t + h} v${-(bh - r)} a${r},${r} 0 0 1 ${r},${-r} h${bw - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${bh - r} z`, class: `bar f-${o.cls || 's1'}` }));
      }
      if (i % every === 0) root.appendChild(svg('text', { x: x0 + bw / 2, y: H - 6, class: 'axis-text', 'text-anchor': 'middle', text: it.label.slice(2) }));
      const hit = svg('rect', { x: m.l + slot * i, y: m.t, width: slot, height: h, class: 'hit' });
      const show = () => tip.show(x0 + bw / 2, m.t + 10, it.label, [{ name: o.valueName || 'Value', value: o.valueFmt(it.value) }]);
      hit.addEventListener('pointermove', show);
      hit.addEventListener('pointerdown', show);
      hit.addEventListener('pointerleave', () => tip.hide());
      root.appendChild(hit);
    });
    host.appendChild(root);
  }
  return observe(host, draw);
}

// ------------------------------------------------------------------ heatmap (CSS-grid; colours via .h0-.h6 classes)
export function heatmap(host, o) {
  clear(host);
  const tip = makeTooltip(host);
  const cols = o.cols.length;
  const grid = el('div', { class: 'heat', role: 'img', 'aria-label': o.ariaLabel || 'Heatmap' });
  grid.style.gridTemplateColumns = `76px repeat(${cols}, minmax(22px, 1fr))`;
  grid.appendChild(el('div', { class: 'heat-corner' }));
  o.cols.forEach((c) => grid.appendChild(el('div', { class: 'heat-col' }, String(c))));
  o.rows.forEach((r, i) => {
    grid.appendChild(el('div', { class: 'heat-row' }, r));
    o.cols.forEach((c, j) => {
      const v = o.values[i][j];
      const cell = el('div', { class: v == null ? 'cell na' : `cell h${Math.min(6, Math.floor((v / o.max) * 7))}` }, v == null ? '' : o.cellText(v));
      if (v != null) {
        const show = (e) => {
          const hr = host.getBoundingClientRect();
          tip.show(e.clientX - hr.left, e.clientY - hr.top, r, [{ name: o.colName(c), value: o.fmt(v) }]);
        };
        cell.addEventListener('pointermove', show);
        cell.addEventListener('pointerdown', show);
        cell.addEventListener('pointerleave', () => tip.hide());
      }
      grid.appendChild(cell);
    });
  });
  host.appendChild(grid);
  host.appendChild(el('div', { class: 'heat-legend' }, el('span', {}, o.fmt(0)),
    [0, 1, 2, 3, 4, 5, 6].map((k) => el('span', { class: `cell h${k} key` })), el('span', {}, o.fmt(o.max))));
}

// ------------------------------------------------------------------ card with chart/table toggle
export function chartCard(o) {
  const body = el('div', { class: 'chart-body' });
  let current = 'chart';
  const bChart = el('button', { type: 'button', class: 'seg-btn', 'aria-pressed': 'true' }, 'Chart');
  const bTable = el('button', { type: 'button', class: 'seg-btn', 'aria-pressed': 'false' }, 'Table');
  const toggle = el('div', { class: 'segmented', role: 'group', 'aria-label': 'View' }, bChart, bTable);
  const card = el('section', { class: `card chart-card ${o.class || ''}` },
    el('div', { class: 'card-head' },
      el('div', {}, el('h3', {}, o.title), o.subtitle ? el('p', { class: 'sub' }, o.subtitle) : null),
      el('div', { class: 'card-actions' }, o.actions || null, toggle)),
    body);
  let ro = null;
  function show(mode) {
    current = mode;
    bChart.setAttribute('aria-pressed', String(mode === 'chart'));
    bTable.setAttribute('aria-pressed', String(mode === 'table'));
    if (ro) { ro.disconnect(); ro = null; }
    clear(body);
    if (mode === 'chart') {
      const host = el('div', { class: 'chart-host' });
      body.appendChild(host);
      ro = o.draw(host);
    } else {
      body.appendChild(el('div', { class: 'table-wrap' }, o.table()));
    }
  }
  bChart.addEventListener('click', () => show('chart'));
  bTable.addEventListener('click', () => show('table'));
  show('chart');
  return { el: card, redraw: () => show(current), body };
}

export { dataTable };
