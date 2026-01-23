Bootstrap theming (Sass build)

Overview
- We’ll compile Bootstrap 5.3 from Sass with our  custom palette.
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



Where things live
- Source SCSS (dual):   `assets/scss/bootstrap-theme.scss` 
- Outputs: `static/css/bootstrap.min.css` 

Notes on Sass 1.70+ (Dart Sass)
- This repo uses the modern module system:
  - `@use "bootstrap/scss/bootstrap" as * with (...)` instead of deprecated `@import`.
  - `sass --load-path=node_modules` in scripts so Bootstrap can be resolved.
  - Built‑in color helpers use `sass:color` (e.g., `color.mix`, `color.change`).

Notes
- We set `$color-mode-type: data` so Bootstrap emits `[data-bs-theme]` color modes (dark via the footer toggle).
- Our variable overrides define both light and dark palettes; alerts/badges and body backgrounds follow automatically.
- After rebuilds, bump `ASSETS_VERSION` in `.env` to bust caches.