const CACHE_NAME = 'second-brain-v0.7.0';

const APP_SHELL = [
  '/',
  '/static/index.html',
  '/static/style.css',
  '/static/app.js',
  '/static/review.js',
  '/static/pwa.js',
  '/static/install.js',
  '/static/offline-queue.js',
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
