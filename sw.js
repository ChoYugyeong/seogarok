/* 서가록 service worker — 앱 셸 캐시 + API 는 항상 네트워크 */
const CACHE = 'seogarok-v1';
const SHELL = [
  '/', '/styles.css', '/app.js', '/data.js', '/legal.html',
  '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // API/헬스/메트릭은 캐시하지 않는다 (항상 최신)
  if (url.pathname.startsWith('/api/') || url.pathname === '/metrics' ||
      url.pathname === '/livez' || url.pathname === '/readyz') return;

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(req, { ignoreSearch: url.pathname === '/' });
    if (hit) {
      // 백그라운드 갱신
      fetch(req).then((res) => { if (res.ok) cache.put(req, res.clone()); }).catch(() => {});
      return hit;
    }
    try {
      const res = await fetch(req);
      if (res.ok && res.type === 'basic') cache.put(req, res.clone());
      return res;
    } catch (err) {
      const fallback = await cache.match('/');
      if (fallback) return fallback;
      throw err;
    }
  })());
});
