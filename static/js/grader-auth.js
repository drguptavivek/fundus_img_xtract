/* Grader PWA authentication on mobile bearer tokens.
 *
 * Tokens come from /api/mobile/v1/auth/login (platform "web"; browsers skip
 * device enrolment) and live in localStorage; the service worker gets a copy
 * so it can attach the Authorization header to page navigations and image
 * loads. The server re-checks identity after 30 idle minutes: a 401
 * "reauth_required" is answered here with a passkey (Touch ID / Face ID /
 * Windows Hello) or the password, then the original call is retried. */
(function () {
  const STORAGE_KEY = 'grader.auth';
  const DEVICE_KEY = 'grader.device_id';
  const API = '/api/mobile/v1';
  let refreshing = null;
  let reauthing = null;

  function read() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); } catch (_) { return null; }
  }
  function write(tokens) {
    try {
      if (tokens) localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
      else localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
    syncWorker();
  }
  function deviceId() {
    let id = null;
    try { id = localStorage.getItem(DEVICE_KEY); } catch (_) {}
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
      try { localStorage.setItem(DEVICE_KEY, id); } catch (_) {}
    }
    return id;
  }
  function deviceName() {
    const ua = navigator.userAgent;
    const os = /iPhone|iPad/.test(ua) ? 'iOS' : /Android/.test(ua) ? 'Android' : /Mac/.test(ua) ? 'macOS' : /Windows/.test(ua) ? 'Windows' : 'Web';
    const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : /Firefox\//.test(ua) ? 'Firefox' : 'Browser';
    return `${browser} on ${os}`;
  }
  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }
  function syncWorker() {
    const tokens = read();
    const message = tokens ? { type: 'AUTH_TOKENS', tokens: { ...tokens, device_id: deviceId() } } : { type: 'AUTH_CLEAR' };
    try { navigator.serviceWorker?.controller?.postMessage(message); } catch (_) {}
    try { navigator.serviceWorker?.ready?.then(reg => reg.active?.postMessage(message)); } catch (_) {}
  }
  async function postJson(path, body, { auth = false } = {}) {
    const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
    if (auth) Object.assign(headers, bearer());
    const response = await fetch(API + path, { method: 'POST', headers, body: JSON.stringify(body || {}), credentials: 'same-origin' });
    let payload = {};
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) {
      const error = new Error(payload.message || payload.error || `Request failed (HTTP ${response.status})`);
      error.code = payload.error || 'request_failed';
      error.status = response.status;
      throw error;
    }
    return payload;
  }
  function bearer() {
    const tokens = read();
    return tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {};
  }

  async function login(username, password) {
    const payload = await postJson('/auth/login', {
      username, password, device_id: deviceId(), device_name: deviceName(), platform: 'web',
    });
    write({
      access_token: payload.access_token,
      refresh_token: payload.refresh_token,
      expires_at: Date.now() + (Number(payload.expires_in) || 900) * 1000,
      username: payload.user?.username || username,
      user_id: payload.user?.id,
      has_passkey: read()?.has_passkey || false,
    });
    return payload;
  }

  function refresh() {
    if (refreshing) return refreshing;
    const tokens = read();
    if (!tokens?.refresh_token) return Promise.reject(Object.assign(new Error('Not signed in'), { code: 'not_signed_in' }));
    refreshing = postJson('/auth/refresh', { refresh_token: tokens.refresh_token, device_id: deviceId() })
      .then(payload => {
        write({ ...read(), access_token: payload.access_token, refresh_token: payload.refresh_token || tokens.refresh_token,
                expires_at: Date.now() + (Number(payload.expires_in) || 900) * 1000 });
        return payload;
      })
      .catch(error => { if (error.status === 401) write(null); throw error; })
      .finally(() => { refreshing = null; });
    return refreshing;
  }

  async function reauthPassword(password) {
    const payload = await postJson('/auth/reauth', { password }, { auth: true });
    write({ ...read(), access_token: payload.access_token, expires_at: Date.now() + (Number(payload.expires_in) || 900) * 1000, auth_time: payload.auth_time });
    return payload;
  }

  function passkeysSupported() {
    return Boolean(window.PublicKeyCredential && navigator.credentials && window.isSecureContext);
  }
  async function platformAuthenticatorAvailable() {
    try { return passkeysSupported() && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(); } catch (_) { return false; }
  }
  function parseCreation(options) {
    return PublicKeyCredential.parseCreationOptionsFromJSON
      ? PublicKeyCredential.parseCreationOptionsFromJSON(options)
      : decodeOptions(options, ['challenge', 'user.id'], 'excludeCredentials');
  }
  function parseRequest(options) {
    return PublicKeyCredential.parseRequestOptionsFromJSON
      ? PublicKeyCredential.parseRequestOptionsFromJSON(options)
      : decodeOptions(options, ['challenge'], 'allowCredentials');
  }
  function b64urlToBytes(value) {
    const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
  }
  function bytesToB64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function decodeOptions(options, paths, listKey) {
    const copy = JSON.parse(JSON.stringify(options));
    paths.forEach(path => {
      const parts = path.split('.');
      let target = copy;
      for (let i = 0; i < parts.length - 1; i += 1) target = target[parts[i]];
      target[parts[parts.length - 1]] = b64urlToBytes(target[parts[parts.length - 1]]);
    });
    (copy[listKey] || []).forEach(item => { item.id = b64urlToBytes(item.id); });
    return copy;
  }
  function credentialToJSON(credential) {
    if (credential.toJSON) return credential.toJSON();
    const response = credential.response;
    const out = { id: credential.id, rawId: bytesToB64url(credential.rawId), type: credential.type, response: {
      clientDataJSON: bytesToB64url(response.clientDataJSON) } };
    if (response.attestationObject) out.response.attestationObject = bytesToB64url(response.attestationObject);
    if (response.authenticatorData) out.response.authenticatorData = bytesToB64url(response.authenticatorData);
    if (response.signature) out.response.signature = bytesToB64url(response.signature);
    if (response.userHandle) out.response.userHandle = bytesToB64url(response.userHandle);
    if (response.getTransports) out.response.transports = response.getTransports();
    return out;
  }
  async function registerPasskey(label) {
    const { challenge_id, options } = await postJson('/auth/passkeys/register/options', {}, { auth: true });
    const credential = await navigator.credentials.create({ publicKey: parseCreation(options) });
    const payload = await postJson('/auth/passkeys/register/verify', { challenge_id, credential: credentialToJSON(credential), label: label || deviceName() }, { auth: true });
    write({ ...read(), has_passkey: true });
    return payload.passkey;
  }
  async function reauthPasskey() {
    const { challenge_id, options } = await postJson('/auth/passkeys/reauth/options', {}, { auth: true });
    const credential = await navigator.credentials.get({ publicKey: parseRequest(options) });
    const payload = await postJson('/auth/passkeys/reauth/verify', { challenge_id, credential: credentialToJSON(credential) }, { auth: true });
    write({ ...read(), access_token: payload.access_token, expires_at: Date.now() + (Number(payload.expires_in) || 900) * 1000, auth_time: payload.auth_time, has_passkey: true });
    return payload;
  }

  async function logout() {
    const tokens = read();
    try { if (tokens?.refresh_token) await postJson('/auth/logout', { refresh_token: tokens.refresh_token }, { auth: true }); } catch (_) {}
    write(null);
  }

  /* ---- In-page re-authentication prompt (after 30 idle minutes) ---- */
  function requireReauth(reason) {
    if (reauthing) return reauthing;
    reauthing = new Promise((resolve, reject) => {
      const tokens = read();
      const overlay = document.createElement('div');
      overlay.className = 'gpwa-reauth';
      overlay.innerHTML = `
        <div class="gpwa-reauth-card" role="dialog" aria-modal="true" aria-labelledby="gpwa-reauth-title">
          <h2 class="h5 mb-1" id="gpwa-reauth-title">Confirm it's you</h2>
          <p class="small text-body-secondary mb-3">${reason || 'You have been inactive for a while. Please re-authenticate to continue grading.'}</p>
          <button type="button" class="btn btn-primary w-100 mb-2 d-none" data-reauth-passkey>
            <i class="fa-solid fa-fingerprint me-1" aria-hidden="true"></i>Use passkey
          </button>
          <form data-reauth-form class="d-flex flex-column gap-2">
            <input class="form-control" type="password" name="password" placeholder="Password for ${tokens?.username || ''}" autocomplete="current-password" required>
            <button class="btn btn-outline-secondary w-100" type="submit">Confirm with password</button>
          </form>
          <div class="small text-danger mt-2 d-none" data-reauth-error></div>
          <button type="button" class="btn btn-link btn-sm w-100 mt-1" data-reauth-signout>Sign out</button>
        </div>`;
      document.body.appendChild(overlay);
      const errorBox = overlay.querySelector('[data-reauth-error]');
      const fail = message => { errorBox.textContent = message; errorBox.classList.remove('d-none'); };
      const done = payload => { overlay.remove(); reauthing = null; resolve(payload); };
      const passkeyButton = overlay.querySelector('[data-reauth-passkey]');
      if (tokens?.has_passkey) {
        platformAuthenticatorAvailable().then(ok => { if (ok) passkeyButton.classList.remove('d-none'); });
      }
      passkeyButton.addEventListener('click', async () => {
        passkeyButton.disabled = true;
        try { done(await reauthPasskey()); } catch (error) { fail(error.message || 'Passkey failed'); passkeyButton.disabled = false; }
      });
      overlay.querySelector('[data-reauth-form]').addEventListener('submit', async event => {
        event.preventDefault();
        const password = event.target.password.value;
        try { done(await reauthPassword(password)); } catch (error) { fail(error.message || 'Password not accepted'); }
      });
      overlay.querySelector('[data-reauth-signout]').addEventListener('click', async () => {
        await logout();
        reauthing = null;
        reject(Object.assign(new Error('Signed out'), { code: 'signed_out' }));
        window.location.assign('/grader/login');
      });
      overlay.querySelector('input[name="password"]').focus();
    });
    return reauthing;
  }

  /* fetch with bearer, transparent refresh, and re-authentication on demand */
  async function authFetch(url, options = {}) {
    const run = async () => fetch(url, { ...options, headers: { ...(options.headers || {}), ...bearer() } });
    let response = await run();
    if (response.status === 401) {
      let payload = null;
      try { payload = await response.clone().json(); } catch (_) {}
      const code = payload?.error?.code || payload?.error || payload?.message || '';
      if (/reauth_required/.test(String(code))) {
        await requireReauth();
        response = await run();
      } else if (read()?.refresh_token) {
        try { await refresh(); response = await run(); } catch (_) {}
      }
    }
    return response;
  }

  async function ensureWorker(url, scope) {
    if (!('serviceWorker' in navigator)) return null;
    try {
      const registration = await navigator.serviceWorker.register(url, { scope });
      await navigator.serviceWorker.ready;
      syncWorker();
      return registration;
    } catch (_) { return null; }
  }

  try {
    navigator.serviceWorker?.addEventListener('message', event => {
      if (event.data?.type === 'AUTH_TOKENS_UPDATED' && event.data.tokens) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...read(), ...event.data.tokens })); } catch (_) {}
      }
    });
  } catch (_) {}

  window.GraderAuth = {
    read, write, bearer, headers: bearer, deviceId, login, refresh, logout, reauthPassword, reauthPasskey,
    registerPasskey, passkeysSupported, platformAuthenticatorAvailable, requireReauth, fetch: authFetch,
    ensureWorker, syncWorker, isSignedIn: () => Boolean(read()?.refresh_token),
  };
  syncWorker();
})();
