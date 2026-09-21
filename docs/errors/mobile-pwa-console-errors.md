# Mobile PWA — console errors at `/mobile/#/login`

Observed 2026-09-21 in Chrome DevTools while loading the Flutter PWA at
`/mobile/#/login`. This page triages every line in that console dump.

**The app not loading at all is #1 — a blocked CanvasKit download. Everything else is
secondary.**

| # | Error | Source | Real? |
|---|---|---|---|
| 1 | Flutter engine fetch to `gstatic.com` fails → **app never paints** | build config + firewall | **Yes — blocker** |
| 2 | Roboto webfont `ERR_CONNECTION_TIMED_OUT` | same root cause as #1 | **Yes — cosmetic** |
| 3 | `Manifest: Line: 2, column: 1, Syntax error.` | Flask login guard | **Yes — host-dependent** |
| 4 | `FrameDoesNotExistError`, `runtime.lastError`, `unload` violation | browser extensions | No — ignore |

---

## 1. App never loads — CanvasKit is fetched from a firewalled CDN

```
Flutter Web engine failed to complete HTTP request to fetch
  "https://fonts.gstatic.com/...": TypeError: Failed to fetch
```

The build uses the **CanvasKit renderer**, which cannot start without
`canvaskit.wasm`. `static/mobile-pwa/flutter_bootstrap.js` carries:

```js
_flutter.buildConfig = {"engineRevision":"42d3d75a56efe1a2e9902f52dc8006099c45d937",
  "builds":[{"compileTarget":"dart2js","renderer":"canvaskit","mainJsPath":"main.dart.js"}]}
```

There is **no `useLocalCanvasKit` flag**, so the loader falls through to its CDN default:

```js
useLocalCanvasKit ? … : I("https://www.gstatic.com/flutter-canvaskit/42d3d75a…/")
```

`www.gstatic.com` is unreachable from the deployment network — the same timeout that
kills the Roboto font in #2. The font is cosmetic; **CanvasKit is the engine**. It
never arrives, Flutter never paints, and the user sees the splash background forever.

This is not a CSP problem. The CSP served with `/mobile/` already allows
`script-src … https://www.gstatic.com` and `connect-src … https://www.gstatic.com`.
`ERR_CONNECTION_TIMED_OUT` is network-level.

### The engine is already on disk and already served

`static/mobile-pwa/canvaskit/` ships the full set — `canvaskit.wasm`, `canvaskit.js`,
`skwasm.wasm`, `skwasm_heavy.wasm`, `chromium/` — and the server serves them:

```
200  /mobile/canvaskit/canvaskit.wasm
200  /mobile/canvaskit/canvaskit.js
```

The files are present; the build simply does not point at them. This is what a web
build made **without** `--no-web-resources-cdn` looks like.

### Fix A — proper, in the client repo (preferred)

In `apps/fundus_glaucoma_mobile`:

```bash
flutter build web --no-web-resources-cdn
```

Sets `useLocalCanvasKit` and self-hosts both the engine and its fonts. Requires
rebuilding and redeploying `static/mobile-pwa/`.

### Fix B — immediate, no rebuild

Pin the base URL in `static/mobile-pwa/index.html` ahead of the loader so the shipped
local copy is used:

```html
<script>window.flutterConfiguration = { canvasKitBaseUrl: "/mobile/canvaskit/" };</script>
```

Unblocks the existing build, but a later `flutter build` overwrites `index.html`, so
Fix A should still follow.

Neither applied yet — documented only.

---

## 2. Roboto webfont times out

```
fonts.gstatic.com/s/roboto/v32/KFOmCnqEu92Fr1Me4GZLCzYlKw.woff2:1
  Failed to load resource: net::ERR_CONNECTION_TIMED_OUT
```

Same root cause as #1 — blocked egress to Google's CDN — and the same fix
(`--no-web-resources-cdn`) resolves both. On its own this is cosmetic: Flutter falls
back to a system font, so the app would render off-design but usable. It only looks
fatal here because #1 is fatal.

Optionally self-host the woff2 under `static/mobile-pwa/` and drop `fonts.gstatic.com`
from the CSP once nothing needs it.

---

## 3. `manifest.webmanifest` parses as HTML — host-dependent

```
mobile/manifest.webmanifest:2 Manifest: Line: 2, column: 1, Syntax error.
```

The browser asks for JSON and receives a `<!doctype html>` redirect body, failing on
line 2 column 1. The file on disk is valid JSON (967 bytes, verified).

**This does not reproduce on every host.** Where nginx serves `/mobile/` off disk the
request never reaches Flask:

| Host | `/mobile/` served by | Anonymous manifest |
|---|---|---|
| `eyeimg.aiims.edu.in` | nginx, static (`cache-control: public, max-age=604800`) | 200, valid JSON — unaffected |
| `eye.epidemiology.tech` | nginx → Flask | 302 → `/login` |
| local container `:5001` | Flask | 200 after the fix below |
| `eyeimg.aiims.edu` | — | does not resolve (listed in CSP `connect-src`) |

### Root cause (Flask-served hosts only)

1. **The login guard did not exempt `/mobile/`.** `PUBLIC_SESSION_PATHS` (`app.py:612`)
   lists the bare string `"/mobile"`, and the guard tests
   `path in PUBLIC_SESSION_PATHS or path.startswith(PUBLIC_SESSION_PREFIXES)`
   (`app.py:719`). The serving routes are `/mobile/` and `/mobile/<path:requested_path>`
   (`app.py:906`), so only the bare `/mobile` was public — and it merely 308-redirects
   to `/mobile/`, which was not. Every asset under `/mobile/` 302'd to `/login` for an
   anonymous caller.
2. **Manifest fetches omit credentials.** `static/mobile-pwa/index.html:32` declares
   `<link rel="manifest" href="manifest.webmanifest">` with no `crossorigin`, so Chrome
   fetches it with credentials mode `omit` — no session cookie.

That combination is why the symptom looked erratic: a signed-in browser sends cookies
for every other asset, so those load, while the cookie-less manifest request alone is
bounced to `/login`.

### Fix applied

`app.py:644` — `/mobile/` added to the prefix list, matching how `/static/` is handled
and restoring the public contract documented in `docs/API/mobile/README.md`:

```python
PUBLIC_SESSION_PREFIXES = ("/static/", "/help", "/mobile/")
```

Verified anonymously against the local container: `/mobile/`, `index.html`,
`flutter_bootstrap.js`, `version.json`, `flutter_service_worker.js`, `main.dart.js`
and `manifest.webmanifest` all return `200`, the last with
`Content-Type: application/manifest+json`.

### Consequence while broken

The PWA is not installable when signed out — no name, icon, `display: standalone` or
theme colour, and iOS "Add to Home Screen" degrades to a plain bookmark.

---

## 4. Browser-extension noise — safe to ignore

None of these come from our code. They originate in extension bundles
(`background.js`, `content.js`) and the React DevTools hook (`installHook.js`), none of
which we ship. Reproduce in an incognito window with extensions disabled and they
disappear.

```
background.js:1 Uncaught (in promise) FrameDoesNotExistError: Frame 8 does not exist in tab 254115210
background.js:1 Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'href')
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.
Unchecked runtime.lastError: The message port closed before a response was received.
Unchecked runtime.lastError: The page keeping the extension port is moved into
    back/forward cache, so the message channel is closed.
content.js:2 [Violation] Permissions policy violation: unload is not allowed in this document.
```

- `FrameDoesNotExistError` / `runtime.lastError` — an extension messaging a frame or
  tab that has already gone away. Ordinary extension lifecycle races.
- `Permissions policy violation: unload` — an extension content script registering a
  deprecated `unload` handler. Reported against the injecting script, not the page.
- `installHook.js` — React DevTools, only relaying the above.

One line in that block **is** ours and is benign:

```
flutter_bootstrap.js:1 Injecting <script> tag. Using callback.
```

Flutter's normal loader progress message, not an error.

---

## Reproducing

```bash
# 1 — build points at the CDN instead of the shipped engine
grep -o 'useLocalCanvasKit[^,;}]*' static/mobile-pwa/flutter_bootstrap.js
grep -o '_flutter\.buildConfig = {[^;]*' static/mobile-pwa/flutter_bootstrap.js

# 1 — but the engine is present and served
ls static/mobile-pwa/canvaskit/
curl -sk -o /dev/null -w '%{http_code}\n' https://eyeimg.aiims.edu.in/mobile/canvaskit/canvaskit.wasm

# 3 — manifest content type and status, per host (no cookie, like a real manifest fetch)
for h in eyeimg.aiims.edu.in eye.epidemiology.tech; do
  curl -sk -D- -o /dev/null "https://$h/mobile/manifest.webmanifest" | grep -iE '^HTTP|^location|^content-type'
done

# 3 — the file itself is valid JSON
python3 -c "import json; json.load(open('static/mobile-pwa/manifest.webmanifest')); print('valid')"
```

## References

- `static/mobile-pwa/flutter_bootstrap.js` — `buildConfig`, CanvasKit base URL
- `static/mobile-pwa/canvaskit/` — the local engine that is shipped but unused
- `static/mobile-pwa/index.html:32` — manifest link
- `app.py:612` `PUBLIC_SESSION_PATHS` · `app.py:644` `PUBLIC_SESSION_PREFIXES` · `app.py:719` guard · `app.py:906` PWA route
- `docs/API/mobile/README.md` — hosted-PWA contract
