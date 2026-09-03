/* Grader PWA service worker (rendered by Flask so asset versions match the layout).
 * Caches the app shell only. Every /api/ call, every image, and every authenticated
 * page goes to the network - no PHI ever enters CacheStorage. */
const VERSION = {{ pwa_version|tojson }};
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

/* ---- Bearer tokens: the page hands them over; the worker attaches them to
 * every same-origin page, API and media request so navigations and <img>
 * loads authenticate without cookies. Kept in IndexedDB so a fresh worker
 * instance still has them. ---- */
const AUTH_DB = 'grader-auth';
let tokens = null;
let refreshing = null;

function openAuthDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(AUTH_DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore('kv');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function persistTokens(value) {
  tokens = value;
  try {
    const db = await openAuthDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction('kv', 'readwrite');
      if (value) tx.objectStore('kv').put(value, 'tokens'); else tx.objectStore('kv').delete('tokens');
      tx.oncomplete = resolve; tx.onerror = () => reject(tx.error);
    });
  } catch (_) {}
}
async function loadTokens() {
  if (tokens) return tokens;
  try {
    const db = await openAuthDb();
    tokens = await new Promise((resolve, reject) => {
      const req = db.transaction('kv').objectStore('kv').get('tokens');
      req.onsuccess = () => resolve(req.result || null); req.onerror = () => reject(req.error);
    });
  } catch (_) { tokens = null; }
  return tokens;
}
async function refreshTokens() {
  if (refreshing) return refreshing;
  const current = await loadTokens();
  if (!current || !current.refresh_token) return null;
  refreshing = fetch({{ mobile_refresh_url|tojson }}, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
    body: JSON.stringify({refresh_token: current.refresh_token, device_id: current.device_id || ''}),
  }).then(async response => {
    if (!response.ok) { if (response.status === 401) await persistTokens(null); return null; }
    const payload = await response.json();
    const next = {...current, access_token: payload.access_token, refresh_token: payload.refresh_token || current.refresh_token,
                  expires_at: Date.now() + (Number(payload.expires_in) || 900) * 1000};
    await persistTokens(next);
    const clients = await self.clients.matchAll({type: 'window'});
    clients.forEach(client => client.postMessage({type: 'AUTH_TOKENS_UPDATED', tokens: next}));
    return next;
  }).catch(() => null).finally(() => { refreshing = null; });
  return refreshing;
}
function needsAuth(url, request) {
  if (url.origin !== self.location.origin) return false;
  if (request.headers.has('Authorization')) return false;
  const path = url.pathname;
  if (path.startsWith('/api/mobile/v1/auth/')) return false;
  if (path === {{ login_url|tojson }} || path === OFFLINE_URL || path.startsWith('/static/')) return false;
  return path.startsWith('/grader/') || path.startsWith('/api/') || path.startsWith('/media/');
}
async function withAuth(request, current) {
  const headers = new Headers(request.headers);
  headers.set('Authorization', 'Bearer ' + current.access_token);
  // Navigation requests use browser-managed redirects (``manual`` in Edge and
  // other Chromium browsers).  Preserve that mode: following the redirect
  // inside the worker produces a redirected Response that respondWith() is
  // forbidden to use for the original navigation request.
  const init = {method: request.method, headers, credentials: 'same-origin', redirect: request.redirect, cache: request.cache};
  if (request.method !== 'GET' && request.method !== 'HEAD') init.body = await request.clone().arrayBuffer();
  return new Request(request.url, init);
}
async function authenticatedFetch(request) {
  let current = await loadTokens();
  if (!current || !current.access_token) return fetch(request);
  if (current.expires_at && Date.now() > current.expires_at - 5000) current = (await refreshTokens()) || current;
  let response = await fetch(await withAuth(request, current));
  if (response.status === 401) {
    let payload = null;
    try { payload = await response.clone().json(); } catch (_) {}
    const code = String(payload && (payload.error && payload.error.code || payload.error || payload.message) || '');
    if (!/reauth_required/.test(code)) {
      const refreshed = await refreshTokens();
      if (refreshed) response = await fetch(await withAuth(request, refreshed));
    }
  }
  return response;
}

self.addEventListener('message', event => {
  const data = event.data || {};
  if (data.type === 'SKIP_WAITING') self.skipWaiting();
  if (data.type === 'AUTH_TOKENS') { const t = {...data.tokens}; t.device_id = t.device_id || data.device_id; event.waitUntil(persistTokens(t)); }
  if (data.type === 'AUTH_CLEAR') event.waitUntil(persistTokens(null));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    // Mutations get the bearer token too, but are never cached.
    if (needsAuth(url, request)) event.respondWith(authenticatedFetch(request));
    return;
  }

  // Pages: always live (with the bearer token attached); the offline screen
  // is the only fallback.
  if (request.mode === 'navigate') {
    event.respondWith(authenticatedFetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  // API and media: never cached; authenticated when a token is held.
  if (needsAuth(url, request)) {
    event.respondWith(authenticatedFetch(request));
    return;
  }

  // Only versioned static files are cacheable; anything else falls through.
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
