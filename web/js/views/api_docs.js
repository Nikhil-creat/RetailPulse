import { chip, errorBox, pageHead, withLoading } from '../ui.js';
import { copyText, el, toast } from '../util.js';

const BODY = {
  '/v1/sql': `-H "content-type: application/json" -d '{"sql":"SELECT category, COUNT(*) FROM dim_product GROUP BY category"}'`,
  '/v1/ask': `-H "content-type: application/json" -d '{"question":"How is churn defined?"}'`,
  '/v1/agent': `-H "content-type: application/json" -d '{"question":"top 5 categories by profit"}'`,
  '/v1/agent/stream': `-N -H "content-type: application/json" -d '{"question":"forecast the next 14 days"}'`,
  '/v1/classify': `-H "content-type: image/png" --data-binary @tile.png`,
};
const ROLE_KIND = { public: '', viewer: 'ok', analyst: 'warn', admin: 'bad' };

export async function render(root, { api, mode }) {
  root.appendChild(pageHead('API reference', 'Generated from the live OpenAPI 3.1 document. Roles are cumulative: viewer < analyst < admin.'));
  const host = el('div', { class: 'stack' });
  root.appendChild(host);
  const base = `${location.origin}${location.pathname.replace(/[^/]*$/, '')}`.replace(/\/$/, '');
  await withLoading(host, () => api.openapi(), (spec) => {
    const byTag = {};
    for (const [path, ops] of Object.entries(spec.paths)) {
      for (const [method, op] of Object.entries(ops)) (byTag[op.tags[0]] ||= []).push({ path, method: method.toUpperCase(), op });
    }
    host.append(el('div', { class: 'card' }, el('p', {}, `${spec.info.title} v${spec.info.version}. `, spec.info.description), mode === 'demo' ? el('p', { class: 'sub' }, 'You are viewing the static demo; the examples below target a running backend.') : null,
      el('p', { class: 'sub' }, 'Authenticate with ', el('code', {}, 'Authorization: Bearer $KEY'), ' (or ', el('code', {}, 'X-API-Key'), '). Responses carry ', el('code', {}, 'X-Request-ID'), '.')));
    for (const [tag, list] of Object.entries(byTag)) {
      host.append(el('section', { class: 'card' }, el('h3', { style: { textTransform: 'capitalize', marginBottom: '8px' } }, tag), list.map(({ path, method, op }) => {
        const role = op['x-required-role'];
        const curl = `curl ${method === 'POST' ? '-X POST ' : ''}${role === 'public' ? '' : '-H "Authorization: Bearer $KEY" '}${BODY[path] ? BODY[path] + ' ' : ''}"${base}${path.replace('{key}', '1042').replace('{name}', 'monthly_revenue')}"`;
        const btn = el('button', { class: 'btn', type: 'button' }, 'Copy');
        btn.addEventListener('click', async () => toast((await copyText(curl)) ? 'curl copied' : 'Copy failed', 'info'));
        return el('details', {}, el('summary', { class: 'endpoint' }, el('span', { class: `method ${method}` }, method), el('span', {}, el('code', {}, path), ' ', el('span', { class: 'sub' }, op.summary)), chip(role, ROLE_KIND[role])),
          el('div', { class: 'codeblock', style: { margin: '6px 0 12px' } }, el('pre', {}, curl), btn));
      })));
    }
  });
}
