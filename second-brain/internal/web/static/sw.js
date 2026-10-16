const CACHE_NAME = 'second-brain-v0.10.0';

const APP_SHELL = [
  '/',
  '/static/index.html',
  '/static/style.css',
  '/static/app.js',
  '/static/review.js',
  '/static/pwa.js',
  '/static/install.js',
  '/static/offline-queue.js',
  '/static/webpush.js',
  '/static/manifest.webmanifest',
  '/static/favicon.svg',
  '/static/icons/icon.svg',
  '/static/icons/icon-maskable.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable-512.png',
  '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return url.pathname === '/api' || url.pathname.startsWith('/api/');
}

function isSwrApiGet(request) {
  if (request.method !== 'GET') return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (!isApiRequest(url)) return false;

  const p = url.pathname;
  if (p === '/api/notes') return true;
  if (p === '/api/tags') return true;
  if (p === '/api/stats') return true;
  if (p === '/api/search') return true;
  if (p === '/api/review/queue') return true;
  if (p === '/api/review/stats') return true;
  if (p === '/api/graph') return true;

  // /api/notes/{id} and /api/notes/{id}/preview, /api/notes/{id}/backlinks
  const noteMatch = p.match(/^\/api\/notes\/[^/]+(?:\/(?:preview|backlinks))?$/);
  if (noteMatch) return true;

  return false;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method === 'GET' && request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/static/index.html'))
    );
    return;
  }

  if (isApiRequest(url)) {
    if (isSwrApiGet(request)) {
      event.respondWith(
        caches.open(CACHE_NAME).then((cache) =>
          fetch(request)
            .then((response) => {
              if (response && response.ok) {
                cache.put(request, response.clone());
              }
              return response;
            })
            .catch(() => cache.match(request))
        )
      );
    }
    return;
  }

  if (request.method === 'GET' && url.origin === self.location.origin) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response && response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
  }
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    // 载荷解析失败时用默认文案兜底
  }
  const title = data.title || '第二大脑 · 复习提醒';
  const options = {
    body: data.body || '有笔记到期了，点开看看',
    tag: data.tag || 'review-digest',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    renotify: false,
    data: { url: data.url || '/#review' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// 点击通知：已有本应用窗口则聚焦并跳到复习页，否则开新窗口。
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/#review';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        try {
          if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
            return client.focus().then(() => {
              if ('navigate' in client) return client.navigate(targetUrl);
            }).catch(() => client.focus());
          }
        } catch (e) {
          // URL 解析失败则继续找下一个窗口
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
