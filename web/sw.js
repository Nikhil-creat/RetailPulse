// Service worker: makes the app shell installable and the static demo work offline.
// It NEVER caches API responses (/v1/*, /health, /metrics): authorised data must not be stored on disk.
const CACHE = 'retailpulse-shell-v2';
const SHELL = ['./', 'index.html', 'css/app.css', 'js/main.js', 'js/api.js', 'js/util.js', 'js/ui.js', 'js/charts.js',
  'icons/icon.svg', 'icons/icon-192.png', 'manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  const p = url.pathname;
  if (/\/(v1\/|health$|metrics$|openapi\.json$)/.test(p) && !p.includes('/demo/')) return; // live API: never cached
  // stale-while-revalidate for the shell and demo data
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(req);
    const net = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => cached);
    return cached || net;
  }));
});
