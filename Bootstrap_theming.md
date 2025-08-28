A **compact blueprint**  to add a bundler + purge + theming (works great with Flask):

1. Install tooling

```bash
npm init -y
npm i bootstrap @popperjs/core
npm i -D vite sass postcss autoprefixer @fullhuman/postcss-purgecss
```

2. Files

* **src/styles/app.scss**

```scss
/* 1) Theme first: override Bootstrap vars before import */
$primary: #0f766e;
$border-radius: .5rem;
/* ...your theme tokens... */

/* 2) Then import Bootstrap + your components */
@import "bootstrap/scss/bootstrap";
@import "./custom";  // optional: src/styles/_custom.scss
```

* **postcss.config.js**

```js
const purgecss = require('@fullhuman/postcss-purgecss');
const contentGlobs = [
  'templates/**/*.html',
  'static/js/**/*.js'
];
module.exports = {
  plugins: [
    require('autoprefixer'),
    purgecss({
      content: contentGlobs,
      defaultExtractor: content => content.match(/[\w-/:]+(?<!:)/g) || [],
      safelist: {
        standard: [
          // Bootstrap runtime states & your own prefixes
          'show','collapsing','collapse','modal','fade','offcanvas',
          /^dropdown/, /^nav/, /^toast/, /^alert/,
          /^btn(-outline)?-/, /^badge-/, /^bg-/, /^text-/,
          /^row$/, /^col(-|$)/, /^g-\d+$/,
          /^pswp/, /^sv-/      // your PhotoSwipe + viewer classes
        ]
      }
    })
  ]
};
```

* **vite.config.js**

```js
import { defineConfig } from 'vite';
export default defineConfig({
  root: '.',
  build: {
    outDir: 'static/assets',
    emptyOutDir: true,
    rollupOptions: { input: 'src/styles/app.scss' }
  }
});
```

3. Scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  }
}
```

4. Template include (after build)

```html
<link rel="stylesheet" href="{{ url_for('static', filename='assets/style.css') }}?v={{ config['ASSETS_VERSION'] }}">
```

**Notes for future you**

* Do *all* color/spacing/typography theming via SCSS variables before importing Bootstrap.
* PurgeCSS is aggressive—keep the safelist up to date (modals, dropdowns, offcanvas, `pswp*`, `sv-*`, dynamic `btn-*`, grid classes, etc.).
* Keep custom CSS in `src/styles/_custom.scss` so theming stays tidy.

We can revisit when you want to switch—this plan will slot in cleanly without disrupting your Flask setup.
