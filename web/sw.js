// Service worker: makes the app shell installable and the static demo work offline.
// It NEVER caches API responses (/v1/*, /health, /metrics): authorised data must not be stored on disk.
const CACHE = 'retailpulse-shell-v4';
const SHELL = ['css/app.css', 'js/main.js', 'js/api.js', 'js/util.js', 'js/ui.js', 'js/charts.js', 'js/brief.js', 'js/palette.js', 'pages.json',
  'icons/icon.svg', 'icons/icon-192.png', 'favicon.ico', 'manifest.webmanifest'];

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
  // HTML pages: network first (so a new deploy shows up at once), cached copy only when offline
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then((res) => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return res; })
      .catch(() => caches.match(req).then((hit) => hit || caches.match(location.origin + new URL('./', self.location).pathname))));
    return;
  }
  // stale-while-revalidate for the shell and demo data
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(req);
    const net = fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); return res; }).catch(() => cached);
    return cached || net;
  }));
});
