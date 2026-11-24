import { chip, pageHead } from '../ui.js';
import { copyText, el, toast } from '../util.js';

const LAYERS = [['Data', 'Seeded synthetic generator with planted structure'], ['Warehouse', 'SQLite star schema, constraints, 5 quality gates'], ['Analytics & ML', 'RFM, cohorts, basket, forecast, churn, vision'],
  ['Knowledge', 'Insights turned into a cited knowledge base'], ['AI layer', 'RAG, tool-using agent, SQL guard'], ['Service + API', 'Roles, rate limits, SSE, OpenAPI, metrics'], ['Web app', 'This progressive web app']];
const STACK = ['Python', 'SQLite', 'pandas', 'scikit-learn', 'NumPy', 'Starlette', 'Uvicorn', 'Vanilla JS (ES modules)', 'SVG charts', 'PWA', 'Docker', 'GitHub Actions', 'pytest'];
const LIMITS = [
  'All data is synthetic: finding planted patterns proves the pipeline works, not that it would on messy real data.',
  'The forecast beats naive baselines but under-forecasts on the holdout; weekly totals are more reliable than single days.',
  'Churn signal is modest (AUC about 0.70) because churn in the generator is partly random.',
  'RAG uses TF-IDF, not embeddings, and its eval set was written by the author, so hit@3 is optimistic.',
  'The image model is trained on synthetic icons and says nothing about real photos.',
  'Injection detection is heuristic; the real protection is that tools are read-only and allow-listed.',
  'The rate limiter is in-memory and per process; the app does not terminate TLS itself.',
];
const RUN = `git clone https://github.com/Nikhil-creat/RetailPulse && cd RetailPulse
pip install -r requirements-dev.txt
python -m pytest -q
python -m retailpulse.cli run-all
python -m retailpulse.cli make-key --role admin   # prints a key once + the hash for .env
python -m retailpulse.cli serve                   # open http://127.0.0.1:8000`;

export async function render(root) {
  root.appendChild(pageHead('About RetailPulse', 'A portfolio-grade analytics platform built to show the whole stack honestly: data, models, AI, security, MLOps and a real web app.'));
  const copy = el('button', { class: 'btn', type: 'button' }, 'Copy');
  copy.addEventListener('click', async () => toast((await copyText(RUN)) ? 'Commands copied' : 'Copy failed'));
  root.append(el('div', { class: 'stack' },
    el('section', { class: 'card' }, el('h3', {}, 'Architecture'), el('ol', { class: 'flow', style: { marginTop: '10px' } }, LAYERS.map(([t, d]) => el('li', {}, el('b', {}, t), d)))),
    el('div', { class: 'grid cols-2' },
      el('section', { class: 'card' }, el('h3', {}, 'Tech stack'), el('div', { class: 'chips', style: { marginTop: '10px' } }, STACK.map((s) => chip(s)))),
      el('section', { class: 'card' }, el('h3', {}, 'Honest limitations'), el('ul', { class: 'list-clean', style: { marginTop: '10px' } }, LIMITS.map((l) => el('li', {}, '• ', l))))),
    el('section', { class: 'card' }, el('h3', {}, 'Run it yourself'), el('div', { class: 'codeblock', style: { marginTop: '10px' } }, el('pre', {}, RUN), copy)),
    el('section', { class: 'card' }, el('h3', {}, 'Author'), el('p', {}, 'Built by Nikhil Chary Sriramoju, final-year B.Tech CSE (Vaagdevi College of Engineering) focused on data analytics and AI.'),
      el('p', {}, el('a', { href: 'https://github.com/Nikhil-creat/RetailPulse', rel: 'noopener noreferrer' }, 'GitHub'), ' · ', el('a', { href: 'https://in.linkedin.com/in/nikhil-chary-sriramoju-95041b38a', rel: 'noopener noreferrer' }, 'LinkedIn')))));
}
