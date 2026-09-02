# Grader PWA — Implementation Plan

Status: **proposed, not started**
Date: 2026-09-02
Scope: an installable, app-like grading client for iOS, iPadOS, Android, macOS and Windows.

---

## 1. Goal

Give graders a focused "log in and grade" application, installable to the home
screen / dock, that reaches the grading workbench in as few taps as possible —
**without changing how a fundus image looks or how a grade is captured.**

Two constraints drive every decision below:

1. **Rendering must be identical to the web workbench.** Filters, brightness,
   contrast, zoom, pan and the loupe must produce the same image on a phone as on
   a desktop, because grading consistency between graders (and between a grader's
   own web and mobile sessions) is a scientific requirement, not a cosmetic one.
2. **Direct links must work.** A grader should be able to follow a link to a task
   and land in the app.

## 2. Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| Client technology | Same-origin web PWA served by Flask at `/grader/` | Only option that reuses `grading-viewer.js` verbatim, which is what makes rendering identical. A Flutter port would mean reimplementing 2,507 lines of viewer in Dart with no way to prove pixel equivalence. |
| Authentication | Existing Flask session cookie + CSRF | Zero backend auth work. Grading APIs are already `@roles_required` → Flask-Login. Login keeps its captcha and lockout behaviour. |
| Backend work | Essentially none | The workbench API is already a complete headless JSON state machine. |

Superseded alternatives: extending the Flutter field app (`apps/fundus_glaucoma_mobile`),
and adding JWT auth to the grading routes. Both were rejected — see §8.

## 3. What already exists (no work needed)

The backend is already headless. `api/grading_workbench.py` exposes the full
session state machine, and `grading/workbench/contracts.py` returns rich DTOs
covering everything a client needs.

```
POST   /api/grading/workbench/acquire                       -> {workbench, session_token}
POST   /api/grading/workbench/linked-followups/acquire
POST   /api/grading/workbench/tasks/<task_uuid>/sessions
POST   /api/grading/workbench/grades/<grade_id>/revision-session
POST   /api/grading/workbench/packages/<package_uuid>/sessions
GET    /api/grading/workbench/sessions/<uuid>
POST   /api/grading/workbench/sessions/<uuid>/resume
POST   /api/grading/workbench/sessions/<uuid>/heartbeat
POST   /api/grading/workbench/sessions/<uuid>/release
PUT    /api/grading/workbench/sessions/<uuid>/draft
POST   /api/grading/workbench/sessions/<uuid>/submit
GET    /api/grading/workbench/me/active-sessions
GET    /api/grading/workbench/me/submissions

GET    /api/grading/me/queues            /api/grading/me/queues/<disease_id>
GET    /api/grading/me/eligibility       /api/grading/me/history
GET    /api/encounter-viewer/images/<image_uuid>
```

Transport contract:

- Lease is carried in `X-Workbench-Token` + `X-Workbench-Generation` headers.
- Mutations need `X-CSRFToken` (`api_bp` is **not** CSRF-exempt; only `mobile_api_bp` is).
- `submit` with `action: "save_next"` returns the **next** workbench inline —
  this is the continuous grading loop, and it means a whole grading run costs one
  request per case.
- The workbench page was made responsive for phones and tablets in `2b515f86`,
  so the layout groundwork is done.

## 4. The identical-rendering contract

This is the part that most needs care, and where the two real hazards are.

### 4.1 The filter definitions live in `base.html`

Filters are applied as a CSS filter chain built in `grading-viewer.js`:

```js
chain = `url(#pswp-greenmono) brightness(1.2) contrast(1.1)`
mainImg.style.filter = chain;
```

Those `url(#...)` references resolve to SVG `<filter>` elements defined in
**`templates/base.html:180-260`** (`pswp-greenmono`, `pswp-greenboost`,
`pswp-gray`, `pswp-contrast`, `pswp-enhance`, `pswp-bluemono`).

A chrome-less PWA shell that does not extend `base.html` would **silently lose
every filter** — `url(#pswp-greenmono)` would resolve to nothing, the image would
render unfiltered, and nothing would error. A grader would be reading an
unprocessed image while believing red-free was on.

**Mitigation:** extract the `<defs>` block into
`templates/_viewer_filter_defs.html`, included by both `base.html` and the PWA
shell. Add a regression test asserting every filter id referenced by
`grading-viewer.js` is present in the rendered PWA shell.

Good news: every filter already pins `color-interpolation-filters="sRGB"`, so
the filter math is browser-independent. That hygiene is already correct.

A second, quieter dependency: `static/css/app.css:821-826` also applies the
filters declaratively, scoped as `.card:has(.imggr-filters input:checked)
.imggr-main-img`. The PWA's viewer must therefore keep a `.card` ancestor
around the panel markup (or those rules move to a scope both hosts share), or
the CSS path and the JS path disagree about which filter is active.

### 4.1a Layout may change; the capture contract may not

The screen designs (`Grader PWA Screens` canvas) move controls around for
touch — the grade options live in a bottom sheet, annotation becomes a mode
with a right-edge tool rail, brightness/contrast collapse behind a button on
phones. What is held fixed, on purpose:

- the filter radios: same seven values, same order, same one-letter labels,
  same active style (`.imggr-filters .btn-check:checked + .btn`);
- the grade options: same impressions, same order, same 2-column grid;
- the feature list, guidelines text and comment field;
- brightness/contrast ranges (`0.5–5`, step `0.05`) and the loupe defaults;
- the annotation tool set (`box`, `rect`, `ellipse`, `polygon`, `brush_mask`,
  `pyramid`) and the per-feature colour palette in `feature-geometry-colors.js`.

Point handles grow to 44px. Phones get the full tool set; whether that ships
in v1 or as view-only is open question 2.

### 4.2 Pan versus draw on touch

How it works today. When a drawing tool is active the editor sets
`data-imggr-pan-locked="true"` on the viewer root
(`feature-geometry-editor.js:1017`), and the viewer's `handleTouchStart`
returns early whenever `isPanLocked()` (`grading-viewer.js:2172`) — **before**
it distinguishes one touch from two. So on a touch screen with a tool active,
one-finger pan *and* two-finger pinch are both dead; the grader has to switch
back to the pointer tool to move the image. Mouse users never notice because
they pan with WASD.

The PWA rule, in priority order:

1. **Pointer type wins.** `pointerType === "pen"` (Apple Pencil, S-Pen) always
   draws, regardless of the tool state of fingers; a finger while a pen is
   down pans. The editor already reads `pointerType` for the pen eraser button
   (`feature-geometry-editor.js:2107`), so this extends an existing branch.
2. **Finger count decides.** One finger draws with the active tool; the moment a
   second finger lands, the editor cancels the in-progress stroke or shape
   (treat it as `pointercancel`, undoable) and the viewer takes the gesture as
   pan/pinch until all fingers lift.
3. **Pan-lock becomes one-finger-only.** `isPanLocked()` stays, but the viewer
   consults it only on the single-touch branch; the two-touch branch ignores it.
4. **The pointer tool is the escape hatch** it already is: with no drawing tool
   active, one finger pans as today.

Concrete edits, all small: `grading-viewer.js` `handleTouchStart` /
`handleTouchMove` (move the lock check inside the `touches.length === 1`
branch), `feature-geometry-editor.js` `handlePointerDown` (ignore
`!event.isPrimary`, cancel on a second active pointer), and `touch-action:
none` on the stage so the browser never claims the gesture. Web behaviour is
unchanged for mouse users; tablets and phones gain zoom-while-drawing.

### 4.3 Where the list of marks lives

On the web the sidebar shows an "Annotation" `<select>` of instances for the
active feature plus eye / edit / delete / clear-all buttons
(`feature-geometry-editor.js:1255-1272`). On the phone the same set becomes the
**Marks sheet**: tap the feature pill in Annotate mode and each instance is a
row (type icon, `#n · Box`, size, hide, edit-points, delete), with *Delete all*
for the feature and the other features listed beneath with their counts. Tapping
a row selects the mark and centres the viewer on it. The feature rows on the
grade sheet carry the per-feature count ("3 marks") as the second entry point.

### 4.4 Encounter sets and linked diseases

Both are already one workbench session with several panels; the PWA changes
navigation, not the contract.

- **Package workflow** (multi-image encounter set): panels are the images plus
  one `encounter` target, ordered by `ordered_package_tasks`. Phone: swipe
  between image targets (the carousel already exists — it just needs
  `data-bs-touch` enabled on the sheet, not the image, because image drag is
  pan), progress dots on the image edge, and the **E target** replaces the
  viewer with the per-eye thumbnail summary already rendered by
  `workbench.html:211-265`. The set-level grade stays locked until every image
  panel has a grade — the existing `firstIncompletePanel` submit rule, surfaced
  earlier as a red "Grade image 4" button instead of a rejection at submit time.
- **Linked workflow**: one image, one panel per disease (primary first, then
  `linked_disease_ids`). Phone: disease **tabs** at the top of the sheet; a tick
  when graded, a lock when read-only (arbitrator context). *Next disease*
  advances tabs (`data-next-disease`); *Save & Next* appears once every editable
  tab has a grade. A `save_next` that returns `queue_request.linked_followup`
  chains into the follow-up session exactly as on the web.

### 4.2 Device colour handling is outside the app's control

Identical code does not guarantee identical pixels. On iPhone/iPad, Safari
composites to a wide-gamut (Display P3) screen and the OS applies **True Tone**,
**Night Shift** and **auto-brightness**. A web application cannot disable any of
these. The same sRGB fundus image will therefore not look identical on an iPad
in a bright room and a colour-managed desktop monitor, no matter what we ship.

This is a **policy question, not a code fix**, and it should be decided before
mobile grading is used for anything comparative:

- Are mobile grades acceptable for all disease workflows, or only some?
- Should graders be instructed to disable True Tone / Night Shift and fix
  brightness while grading?
- Should the submission record which platform a grade was made on, so
  inter-rater analyses can control for it?

The third option is cheap and worth doing regardless — the workbench already has
an audit trail (`grading/workbench/audit.py`) to hang it on.

### 4.3 What "identical" concretely means here

Achieved by reusing, unchanged: `grading-viewer.js`, `feature-geometry-*.js`,
`submission-guard.js`, the filter `<defs>`, and the panel markup contract
(`.imggr-*` class names) that the viewer queries by selector. The plan does not
fork or re-style any of them.

## 5. Direct links — what is actually achievable

Honest per-platform behaviour, because this is easy to over-promise:

| Platform | Following an `https://…/grader/…` link | Notes |
|---|---|---|
| Android (Chrome) | Opens the installed PWA | Requires in-scope URL. Reliable. |
| Desktop Chrome/Edge (Win/macOS) | Opens the installed PWA | Via link capturing + `launch_handler`. |
| **iOS / iPadOS** | **Opens Safari, not the installed app** | No workaround exists. Apple does not let a home-screen web app capture https links. |

The iOS case has a second-order problem: an installed iOS PWA has **its own
cookie jar**, separate from Safari's. So a grader who is logged into the
installed app and then taps a link is logged out in the Safari copy that opens.

Options, to be decided:

- **Accept it.** Links open in Safari and prompt a login; the installed app stays
  the primary way to grade. Zero extra work.
- **Ship a TWA for Android** (Trusted Web Activity + Digital Asset Links) to get
  true link capture and Play Store distribution. You already publish an Android
  APK for the field app, so the release pipeline exists. Does nothing for iOS.
- **Native wrapper for iOS.** Only way to capture links there; a large step up in
  cost and review burden. Not recommended for v1.

Recommendation for v1: accept it, and make the login screen honour `?next=` so a
Safari-opened link costs one login and then lands on the right task.

## 6. Native feel — the concrete checklist

- **Dark by default.** The shell sets `data-bs-theme="dark"` and the manifest's
  `theme_color` / `background_color` are `#212529`; the viewer stage stays
  `#000` so the image is never tinted. `base.html`'s theme toggle logic is not
  loaded in the PWA shell, so the user's web-side theme preference does not
  leak in — the PWA has one theme.
- **Loading and saving reuse the workbench's own loader.** `.gwb-submit-overlay`
  (`rgba(body-bg, .88)` + 2px blur) and `.gwb-loader-mark` (counter-spinning
  primary ring around the rotating `retina_svg_logo.svg`) move out of
  `workbench.html`'s inline `<style>` into a shared stylesheet in Phase 0 and
  are used for submit, acquire-next, session resume, and the initial shell
  load. No second spinner.
- `display: standalone`, `scope: /grader/`, `start_url: /grader/?source=pwa`
- `viewport-fit=cover` + `env(safe-area-inset-*)` padding for notch/home indicator
- `overscroll-behavior: none` to kill pull-to-refresh mid-grade
- `touch-action` pinned on the viewer stage so pan/zoom never scrolls the page
- No text selection or callout on controls (`-webkit-touch-callout: none`)
- `apple-mobile-web-app-capable`, status-bar style, iOS splash screens
- **Screen Wake Lock** while a grading session is open — keeps the screen on and,
  importantly, keeps heartbeats firing (see §8.1)
- Vibration API for submit confirmation on Android
- Maskable icons at 192/512, reusing `assets/brand/retina_logo`

## 7. Phases

### Phase 0 — Extraction (pure refactor, no behaviour change)

The workbench's session logic is **inline `<script>` inside
`templates/grading/workbench.html`** — it is the only place `X-Workbench-Token`
appears. The panel and viewer markup are inline in the same 1,168-line template.
Reusing them is what prevents the PWA becoming a second, drifting copy of the
grading state machine.

1. Extract the SVG filter `<defs>` → `templates/_viewer_filter_defs.html`;
   include from `base.html`. **(§4.1 — do this first, it is the correctness one.)**
2. Extract inline session JS → `static/js/grading-workbench-session.js`
   (lease + heartbeat, draft autosave, submit / `save_next`, token headers).
3. Extract panel + viewer markup → `templates/grading/_workbench_panel.html`.
4. **Verify `/grade` is byte-for-byte unchanged in behaviour before proceeding.**

Exit gate: existing grading tests green, and a manual pass over the workbench
confirming all seven filters, brightness, contrast, loupe, zoom, pan,
annotations, draft autosave and submit still work.

### Phase 1 — PWA shell

- Blueprint serving `GET /grader/`, rendering a chrome-less shell that includes
  the shared filter defs. `@roles_required("ophthalmologist", "field_ophthalmologist")`.
- Anonymous → redirect to `/login?next=/grader/` (keeps captcha + lockout).
- `manifest.webmanifest` + icons, served under `/grader/` scope.

### Phase 2 — Service worker

- Precache the **app shell only**: shell HTML, CSS, JS bundle, icons, fonts.
- **Network-only, never cached:** everything under `/api/`, all image and media
  responses, and the shell's authenticated HTML. No PHI may enter CacheStorage.
- Offline fallback screen. Grading holds a **server-side lease**, so offline
  grading cannot be faked safely — the app must say "you are offline" rather than
  queue grades.
- Update flow: `skipWaiting` + an in-app "new version — reload" prompt.
  A stale cached shell against a newer API is a real hazard for a clinical tool.

### Phase 3 — Screens

1. **Login gate** — hand off to the server login, return via `?next=`.
2. **Home** — eligibility + queues (`/api/grading/me/queues`), plus resumable
   sessions from `/workbench/me/active-sessions`.
3. **Grade** — `acquire` → panels → viewer → grades/features/comment/annotations
   → draft autosave + heartbeat → `submit` with `action:"save_next"` to chain
   directly into the next case.
4. **History** — `/api/grading/me/history` and `/workbench/me/submissions`.

### Phase 4 — Docs, tests, beads

- Fill in the stub `docs/API/grading-workbench/README.md` with the full client
  contract (it is currently a placeholder, and this plan depends on it).
- Add `docs/16-NewFeature/grader_pwa/` usage docs; update the `README.md` index.
- Tests: route/role gating; manifest + service worker headers and scope;
  **filter-defs presence regression test (§4.1)**; end-to-end
  acquire → draft → submit against `test-db` from inside the Compose network.
- Create the tracking bead; resolve the duplicate `fundus_img_xtract-wx0o` /
  `fundus_img_xtract-fs66` pair, which already circles the PWA security boundary.

## 8. Risks

### 8.1 Leases versus mobile backgrounding — highest risk

Grading holds a server lease refreshed by heartbeat. iOS and Android suspend
background tabs aggressively, so **the lease expires whenever the phone locks or
the grader switches apps mid-case**, and unsaved work is at risk.

Mitigations, in order of value:

- Screen Wake Lock while a session is open (§6).
- Flush a draft save on `visibilitychange` → hidden, before suspension.
- Resume-on-focus: on return, re-`resume` the session and reconcile, with a clear
  "your session expired, reopening" path rather than a silent failure.
- Consider a longer idle window for PWA-originated sessions —
  `WorkbenchLeaseDTO` already carries `heartbeat_interval_seconds` and
  `expiry_warning_seconds` per session, so this is a service-layer change, not a
  protocol change.

### 8.2 iOS cookie eviction

ITP can evict an installed iOS PWA's cookie jar after ~7 days of non-use,
forcing re-login. Acceptable, but graders should be told rather than surprised.

### 8.3 Annotation editing on touch

`feature-geometry-editor.js` is the heaviest interaction to get right on a small
touch screen. Recommend v1 ships annotation **viewing** on phones and full
editing on tablet and desktop, rather than shipping a cramped editor. To be
confirmed — this is a product call.

### 8.4 Refactor blast radius

Phase 0 touches the working web workbench, which is in active daily use and had
eight commits in the last two days. It is a pure refactor with no behaviour
change, but it must land behind its exit gate (above) and not be bundled with
PWA feature work in the same commit.

## 9. Open questions

1. Are mobile-made grades acceptable for all diseases, or should the platform be
   recorded and controlled for in inter-rater analysis? (§4.2)
2. Annotation editing on phones in v1: full, view-only, or tablet-and-up? (§8.3)
3. Is an Android TWA wanted for true link capture and Play Store presence, or is
   home-screen install enough for v1? (§5)
4. Should PWA sessions get a longer lease idle window than desktop ones? (§8.1)
