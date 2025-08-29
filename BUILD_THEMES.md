Bootstrap theming (Sass build)

Overview
- We’ll compile Bootstrap 5.3 from Sass with our Healthcare Calm palette.
- Output: overwrite `static/css/bootstrap.min.css` so templates don’t change.
- Also ships separate light-only and dark-only bundles for static pages.

Prereqs
- Node.js 18+ (recommended) and npm.

Install once
1. npm init -y
2. npm install --save-dev sass
3. npm install bootstrap@5.3.3

Build CSS
- One‑off build:
  npm run build:css

- Watch while developing:
  npm run watch:css

- Build separate bundles:
  - Dual-mode Healthcare (default): npm run build:css
  - Light-only:                     npm run build:css:light
  - Dark-only:                      npm run build:css:dark
  - All of the above:               npm run build:css:all

Where things live
- Source SCSS (dual):   `assets/scss/bootstrap-theme.scss` (Healthcare)
- Source SCSS (single): `assets/scss/bootstrap-theme-light.scss`, `assets/scss/bootstrap-theme-dark.scss`
- Outputs: `static/css/bootstrap.min.css`, `static/css/bootstrap.light.min.css`, `static/css/bootstrap.dark.min.css`

Notes on Sass 1.70+ (Dart Sass)
- This repo uses the modern module system:
  - `@use "bootstrap/scss/bootstrap" as * with (...)` instead of deprecated `@import`.
  - `sass --load-path=node_modules` in scripts so Bootstrap can be resolved.
  - Built‑in color helpers use `sass:color` (e.g., `color.mix`, `color.change`).

Notes
- We set `$color-mode-type: data` so Bootstrap emits `[data-bs-theme]` color modes (dark via the footer toggle).
- Our variable overrides define both light and dark palettes; alerts/badges and body backgrounds follow automatically.
- After rebuilds, bump `ASSETS_VERSION` in `.env` to bust caches.

Optional cleanup
- If you prefer pure Sass theming, you can remove runtime overrides in `static/css/app.css` (palette tokens and `.btn-primary` block). They won’t break anything if left in.
