/* 서가록 service worker — 앱 셸 캐시 + API 는 항상 네트워크
 *
 * 주의: HTML/JS/CSS 는 network-first 로 받아야 배포 후 새 기능이 즉시 보인다.
 * (cache-first 로 두면 배포 후에도 옛 app.js 가 계속 서빙됨)
 * 오프라인일 때만 캐시로 폴백한다.
 */
const CACHE = 'seogarok-v3';
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

  const isAppShell = url.pathname === '/' || url.pathname === '/manifest.webmanifest' ||
    /\.(js|css|html)$/.test(url.pathname);

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    if (isAppShell) {
      // network-first: 배포 즉시 반영, 오프라인은 캐시 폴백
      try {
        const res = await fetch(req);
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      } catch (err) {
        const cached = await cache.match(req, { ignoreSearch: true });
        if (cached) return cached;
        const fallback = await cache.match('/');
        if (fallback) return fallback;
        throw err;
      }
    }
    // 이미지 등 정적 자산: cache-first + 백그라운드 갱신
    const hit = await cache.match(req);
    if (hit) {
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

/* ---------------- 웹푸시 종료 알림 ---------------- */
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: '서가록 종료 알림', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || '서가록 알림';
  const body = data.body || '곧 종료되는 책이 있어요';
  const url = data.url || '/';
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      data: { url },
      tag: 'seogarok-ending',
      renotify: false,
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  // 열람 통계 (실패해도 무시)
  try {
    fetch('/api/push/opened', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, book_id: (url.split('#book=')[1] || '') }),
    }).catch(() => {});
  } catch (e) {}
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const c of all) {
        if ('focus' in c) {
          c.navigate(url);
          return c.focus();
        }
      }
      return self.clients.openWindow(url);
    })(),
  );
});
