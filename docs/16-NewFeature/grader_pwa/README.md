# Grader PWA

An installable, same-origin grading client served under `/grader/`. It renders
the **same** workbench body as the web page (`templates/grading/_workbench_body.html`)
inside a chrome-less, dark-only layout, so image filters, grade capture and
annotation tools behave identically on phones, tablets and desktops.

Design and rationale: [PLAN.md](PLAN.md). Screen designs: the "Grader PWA Screens" canvas.

## URLs

| Route | Auth | Purpose |
|---|---|---|
| `GET /grader/` | grading role | Home: queues, project encounter sets, sessions to resume |
| `GET /grader/start/<disease_id>/<role_slot>` | grading role | Lease the next case (optional `?lab_unit_id=`) |
| `GET /grader/linked-followup/<primary_id>/<linked_id>` | grading role | Linked follow-up queue |
| `GET /grader/open/task/<task_uuid>/<role_slot>` | grading role | **Direct link** to one task |
| `GET /grader/open/package/<package_uuid>/<role_slot>` | grading role | Direct link to an EncounterSet package |
| `GET /grader/open/grade/<grade_id>` | grading role | Revision session for a submitted grade |
| `GET /grader/resume/<session_uuid>` | grading role | Resume an active session |
| `GET /grader/workbench/<session_uuid>` | grading role | The workbench page |
| `GET /grader/history` | grading role | Grading history (`date`, `type`, `disease_id`, `page`) |
| `GET /grader/manifest.webmanifest` | public | Web app manifest |
| `GET /grader/sw.js` | public | Service worker (`Service-Worker-Allowed: /grader/`) |
| `GET /grader/offline` | public | Offline fallback page |

Grading roles: `ophthalmologist`, `field_ophthalmologist` — the same as the web
workbench. Anonymous visitors are redirected to `/login?next=<url>` and land back
on the requested case after sign-in (`auth.login` now honours a same-origin `next`).

The PWA calls the existing JSON API for every mutation (`/api/grading/workbench/*`)
with the session cookie, `X-CSRFToken`, `X-Workbench-Token` and
`X-Workbench-Generation` — see `docs/API/grading-workbench/README.md`.

## What is shared with the web workbench (Phase 0 extraction)

| Piece | File | Used by |
|---|---|---|
| SVG colour filters | `templates/_viewer_filter_defs.html` | `base.html`, `grader_pwa/_layout.html` |
| Workbench layout CSS | `static/css/grading-workbench.css` | both |
| Workbench body (panels, footer, scripts) | `templates/grading/_workbench_body.html` | both |
| Session controller (heartbeat, drafts, submit) | `static/js/grading-workbench-session.js` | both |
| Acquisition / resume / render helpers | `grading/workbench_page.py` | `grading` blueprint, `grader_pwa` |

The body partial reads its per-session values from a `[data-workbench-config]`
JSON block. Two optional context values let a host point links at itself:
`workbench_dashboard_url` (Dashboard / Save & Close) and `workbench_url_template`
(`/grader/workbench/{uuid}` — where Save & Next navigates).

A regression test asserts every `url(#pswp-*)` id the viewer references is
defined, with `color-interpolation-filters="sRGB"`, in both layouts.

## Phone layout

`static/css/grader-pwa.css` + `static/js/grader-pwa.js`, scoped under `body.gpwa`:

- The viewer card fills the screen on a black stage; the grade card becomes a
  bottom sheet. Peeked, it shows the grade options and Save & Next; a handle (or
  choosing a grade that carries features) opens features, comment and Save & Close.
- The filter bar is the unchanged `.imggr-filters` radio group (N R G B Y H E).
- **Annotate mode**: the existing Tools toggle shows the editor sidebar as the
  tool panel and hides the grade sheet; "Done annotating" returns.
- Tablets and desktops get the standard workbench with 44px targets.

## Touch: pan versus draw

- One finger draws when a tool is active; **two fingers always pan / pinch-zoom**
  (`grading-viewer.js` consults the pan lock only for single-touch gestures).
- While two fingers are down the viewer sets `data-imggr-multi-touch="true"` on
  the viewer root and the editor ignores touch pointer moves, so the stroke is
  frozen at its pre-gesture state rather than distorted. Secondary touch
  pointers never start a stroke.
- Mouse behaviour on the web is unchanged.

## Annotation coordinate and memory audit (2026-09-02)

Checked live on the demo at phone (375 px, dpr 2) and desktop widths by
drawing boxes with synthetic touch pointer events and comparing the stored
image-pixel ROI with an independent mapping from the rendered image rect:

- Fit zoom and 250-300 % zoom with pan: stored coordinates matched to full
  floating-point precision in every case; strokes rendered exactly on the
  expected edges, and a box drawn at fit zoom stayed on its true edges after
  zooming and panning.
- The mapping (`clientToPixel` in `feature-geometry-editor.js`) works purely in
  CSS-pixel rects from `getBoundingClientRect`, so Retina/high-DPI screens and
  browser zoom cannot skew it; `devicePixelRatio` only scales the canvas
  backing store through `setTransform`.
- **Fixed:** the overlay canvas was sized to the whole scaled image, so at
  250 % zoom on a desktop it allocated 4275 x 4275 device pixels (~73 MB) and
  redrew all of it on every pan. It now covers only the visible intersection
  of the image and the viewer, carries the offset in the context transform
  (drawing code unchanged), caps the backing scale at 2x and the area at
  4096^2. Same zoom afterwards: 1718 x 1718 (~11 MB); panning no longer
  reallocates the canvas.
- **Fixed:** an encounter-level target (no image, no sidebar host) used to
  mount its annotation panel into the first image's sidebar. Contexts without
  their own host now get no controls.

## Service worker policy

`templates/grader_pwa/sw.js` is rendered by Flask so precached URLs carry the
same `?v=` as the layout. It caches **only** `/static/` files plus `/grader/offline`.
Navigations, `/api/*` and image responses are network-only; nothing containing
PHI enters CacheStorage. A new build shows a "Reload" toast; `SKIP_WAITING`
activates it.

## Other behaviours

- Dark-only (`data-bs-theme="dark"`); the web theme toggle is not loaded.
- Screen Wake Lock is held while a workbench is open so heartbeats keep firing.
- Service worker registration could not be confirmed in the embedded review
  browser (registration rejected despite a 200 script and `worker-src 'self'`);
  verify once in Chrome/Safari on a device. The page works without it.
- The session controller flushes the draft on `visibilitychange` → hidden
  (this also applies to the web workbench).
- Loading/saving reuse the workbench's own `.gwb-submit-overlay` / `.gwb-loader-mark`.

## Platform notes

- iOS does not let an installed web app capture `https` links: a tapped link
  opens Safari (separate cookie jar → one login), then lands on the case via `next`.
  Android and desktop Chrome open the installed app.
- iOS may evict an unused installed app's cookies after ~7 days; graders re-login.
- Colour rendering: identical code does not guarantee identical pixels across
  displays (True Tone, Night Shift, wide-gamut). See PLAN.md §4.2.

## Demo mode

`GET /grader/demo` is public and renders the real workbench body over a
synthetic encounter set: four generated fundus views (OD and OS, one
disc-centred and one macula-centred each) with an encounter-level target per
disease, in the package workflow — so swiping between images, the E target's
per-eye summary, *Next Disease* and Save & Next all behave as in a live session.

- Grade options and features are read from the configured diseases
  (`DR` / `DR Encounter Status`, `Glaucoma` / `Glaucoma Encounter Status`,
  see `grader_pwa/demo.py::DEMO_SCOPES`); a deployment without them gets a
  built-in fallback set with negative ids.
- The session controller sees `"demo": true` in its config and answers every
  API call locally (heartbeat, draft, submit). Nothing is leased or written.
- Images are generated by `scripts/make_demo_fundus.py` (no patient data) into
  `static/grader-pwa/demo/`. Re-run it inside Compose to regenerate.
- A yellow "Demo · synthetic images · nothing is saved" pill marks the page; the
  home screen links to it under *Try the demo*.

## Tests

`tests/unit/grader_pwa/test_grader_pwa.py` (run inside Compose):

```bash
docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web uv run pytest tests/unit/grader_pwa tests/unit/grading/test_workbench_page.py tests/unit/grading/test_encounter_set_package_grading.py -q
```
