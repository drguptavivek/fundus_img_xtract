/* Grader PWA service worker (rendered by Flask so asset versions match the layout).
 * Caches the app shell only. Every /api/ call, every image, and every authenticated
 * page goes to the network - no PHI ever enters CacheStorage. */
const VERSION = {{ (config.get('ASSETS_VERSION', '') ~ '-grader-pwa-v1')|tojson }};
const SHELL_CACHE = `grader-shell-${VERSION}`;
const OFFLINE_URL = {{ offline_url|tojson }};
const SHELL_ASSETS = {{ shell_assets|tojson }};

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key.startsWith('grader-shell-') && key !== SHELL_CACHE)
            .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Pages: always live; the offline screen is the only fallback.
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // Only versioned static files are cacheable. /api/, /media/ and everything
  // else fall through to the network untouched.
  if (!url.pathname.startsWith('/static/')) return;

  event.respondWith(
    caches.match(request).then(hit => hit || fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(SHELL_CACHE).then(cache => cache.put(request, copy));
      }
      return response;
    }))
  );
});
