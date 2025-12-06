# CSS Optimization Implementation Plan

## Quick Wins (Can be implemented immediately)

### 1. Remove Duplicate CSS Rules

**File: `/static/css/app.css`**

**Remove duplicate `.scr-badge-enhanced` (lines 567-571):**
```css
/* DELETE THESE LINES - DUPLICATE OF LINES 28-32 */
.scr-badge-enhanced {
  font-size: 0.75rem;
  padding: 0.25em 0.5em;
  border-radius: 0.375rem;
}
```

**Remove duplicate `.pswp__pdfwrap` (lines 128-142):**
```css
/* DELETE THESE LINES - DUPLICATE OF LINES 48-65 */
.pswp__pdfwrap {
  position: absolute;
  top: 6rem;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
}

.pswp__pdfwrap iframe {
  width: 100%;
  height: 100%;
  border: 0;
  filter: none !important;
}
```

**Remove duplicate `.style-guide-snippet` (lines 1116-1122):**
```css
/* DELETE THESE LINES - DUPLICATE OF LINES 984-990 */
.style-guide-snippet {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.875rem;
}
```

**Remove duplicate `.style-guide-copy` (lines 1135-1158):**
```css
/* DELETE THESE LINES - DUPLICATE OF LINES 1003-1027 */
.style-guide-copy {
  /* ... duplicate styles ... */
}
```

**Expected impact: ~50 lines removed**

### 2. Fix Incomplete CSS Rules

**Fix incomplete `.page-box` rule (line 653):**
```css
.page-box {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--bs-border-color);
  border-radius: .25rem;
  height: calc(1.5em + .5rem + 2px);
  padding: 0;
  background: transparent; /* ADD MISSING SEMICOLON */
}
```

### 3. Replace Custom `.vr` with Bootstrap

**Remove custom `.vr` (lines 544-549):**
```css
/* DELETE - Use Bootstrap's .vr utility instead */
.vr {
  width: 1px;
  height: 1.25rem;
  background-color: var(--bs-border-color, #dee2e6);
  opacity: .6;
}
```

**Update HTML templates to use Bootstrap's `.vr` utility**

### 4. Optimize Range Slider Styles

**Consolidate duplicate form-range styles (lines 816-894 and 1056-1114):**
```css
/* Move to a dedicated form-enhancements.css file */
.form-range {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 8px;
  cursor: pointer;
  background: transparent;
  accent-color: #0ea5a6;
}

/* Consolidate all form-range variants here */
.form-range.form-range-light {
  accent-color: #f8fafc;
}

.imggr-bright,
.imggr-contrast {
  width: 140px;
  min-width: 120px;
  max-width: 200px;
}
```

## Medium-Term Optimizations (Week 2)

### 1. Critical CSS Extraction

**Create `/static/css/critical.css`:**
```css
/* Above the fold critical styles */
:root {
  --bs-primary: #0ea5a6;
  --bs-secondary: #5b6073;
}

/* Navigation */
.navbar {
  padding: var(--bs-navbar-padding-y) var(--bs-navbar-padding-x);
}

/* Layout */
.container, .container-fluid {
  --bs-gutter-x: 1.5rem;
  --bs-gutter-y: 0;
  width: 100%;
  padding-right: calc(var(--bs-gutter-x) * .5);
  padding-left: calc(var(--bs-gutter-x) * .5);
  margin-right: auto;
  margin-left: auto;
}

/* Core Components */
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  word-wrap: break-word;
  background-color: var(--bs-card-bg);
  background-clip: border-box;
  border: var(--bs-card-border-width) solid var(--bs-card-border-color);
  border-radius: var(--bs-card-border-radius);
}

.card-body {
  flex: 1 1 auto;
  padding: var(--bs-card-spacer-y) var(--bs-card-spacer-x);
  color: var(--bs-card-color);
}

/* Forms */
.form-control {
  display: block;
  width: 100%;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 400;
  line-height: 1.5;
  color: var(--bs-body-color);
  background-color: var(--bs-body-bg);
  background-clip: padding-box;
  border: var(--bs-border-width) solid var(--bs-border-color);
  appearance: none;
  border-radius: var(--bs-border-radius);
  transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

.btn {
  --bs-btn-padding-x: 0.75rem;
  --bs-btn-padding-y: 0.375rem;
  --bs-btn-font-family: ;
  --bs-btn-font-size: 0.875rem;
  --bs-btn-font-weight: 400;
  --bs-btn-line-height: 1.5;
  --bs-btn-color: var(--bs-body-color);
  --bs-btn-bg: transparent;
  --bs-btn-border-width: var(--bs-border-width);
  --bs-btn-border-color: transparent;
  --bs-btn-border-radius: var(--bs-border-radius);
  --bs-btn-hover-border-color: transparent;
  --bs-btn-box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0), 0 1px 1px rgba(0, 0, 0, 0.075);
  --bs-btn-disabled-opacity: 0.65;
  --bs-btn-focus-box-shadow: 0 0 0 0.25rem rgba(var(--bs-btn-focus-shadow-rgb), .5);
  display: inline-block;
  padding: var(--bs-btn-padding-y) var(--bs-btn-padding-x);
  font-family: var(--bs-btn-font-family);
  font-size: var(--bs-btn-font-size);
  font-weight: var(--bs-btn-font-weight);
  line-height: var(--bs-btn-line-height);
  color: var(--bs-btn-color);
  text-align: center;
  text-decoration: none;
  vertical-align: middle;
  cursor: pointer;
  user-select: none;
  border: var(--bs-btn-border-width) solid var(--bs-btn-border-color);
  border-radius: var(--bs-btn-border-radius);
  background-color: var(--bs-btn-bg);
  transition: color 0.15s ease-in-out, background-color 0.15s ease-in-out, border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

/* Basic utilities */
.d-flex { display: flex !important; }
.flex-column { flex-direction: column !important; }
.align-items-center { align-items: center !important; }
.justify-content-between { justify-content: space-between !important; }
.gap-2 { gap: 0.5rem !important; }
.mb-3 { margin-bottom: 1rem !important; }
.text-muted { color: var(--bs-secondary-color) !important; }
```

### 2. Update Base Template for Critical CSS

**Update `templates/base.html`:**
```html
<head>
  <!-- Critical CSS inline -->
  <style>
    /* Inline critical.css content here */
  </style>

  <!-- Non-critical CSS with preload -->
  <link rel="preload" href="{{ url_for('static', filename='css/app.css') }}" as="style" onload="this.onload=null;this.rel='stylesheet'">
  <noscript><link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}"></noscript>
</head>
```

### 3. Modular CSS Structure

**Create modular CSS files:**

**`/static/css/components/viewers.css`:**
```css
/* Medical imaging viewer components */
.pswp__pdfwrap,
.pswp__img-filter-*,
.pswp__zoom-slider,
.sv-viewer-root,
.imggr-viewer-root,
.imggr-loupe {
  /* All viewer-related styles */
}
```

**`/static/css/components/screening.css`:**
```css
/* Screening system components */
.scr-card,
.scr-detail-item,
.scr-badge-enhanced,
.scr-thumb-container,
.scr-meta {
  /* All screening-related styles */
}
```

**`/static/css/components/forms.css`:**
```css
/* Enhanced form controls */
.page-box,
.form-range,
.imggr-bright,
.imggr-contrast {
  /* All form enhancements */
}
```

### 4. Bootstrap Configuration Optimization

**Update `package.json` build script:**
```json
{
  "scripts": {
    "build:css": "npm run build:themes && npm run build:components && npm run build:critical",
    "build:themes": "sass assets/scss/bootstrap-theme.scss static/css/bootstrap-theme.min.css --style=compressed",
    "build:components": "sass assets/scss/components.scss static/css/components.min.css --style=compressed",
    "build:critical": "node scripts/extract-critical-css.js",
    "purge:css": "purgecss --css static/css/*.css --content templates/**/*.html --output static/css/purged/"
  }
}
```

**Create PurgeCSS configuration:**
```javascript
// purgecss.config.js
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js'
  ],
  css: [
    './static/css/app.css',
    './static/css/bootstrap-theme.min.css'
  ],
  defaultExtractor: content => {
    // Extract class names from content
    const broadMatches = content.match(/[^<>"'`\s]*[^<>"'`\s:]/g) || []
    const innerMatches = content.match(/[^<>"'`\s.()]*[^<>"'`\s.():]/g) || []
    return broadMatches.concat(innerMatches)
  },
  safelist: [
    // Medical imaging components
    /^pswp-/,
    /^imggr-/,
    /^scr-/,
    /^sv-/,
    // Theme system
    /^theme-/,
    /^card-soft-/,
    /^badge-soft-/,
    /^kpi-/,
    // Dynamic classes
    /^state-/,
    // Bootstrap dark mode
    'data-bs-theme="dark"',
    'data-bs-theme="light"'
  ]
}
```

## Advanced Optimizations (Week 3+)

### 1. CSS Performance Monitoring

**Create `/static/js/css-performance.js`:**
```javascript
// CSS loading performance monitoring
class CSSPerformanceMonitor {
  constructor() {
    this.criticalCSSLoaded = false;
    this.nonCriticalCSSLoaded = false;
  }

  markCriticalCSSLoaded() {
    this.criticalCSSLoaded = true;
    performance.mark('critical-css-loaded');
    this.reportPerformance();
  }

  markNonCriticalCSSLoaded() {
    this.nonCriticalCSSLoaded = true;
    performance.mark('non-critical-css-loaded');
    this.reportPerformance();
  }

  reportPerformance() {
    if (this.criticalCSSLoaded && this.nonCriticalCSSLoaded) {
      performance.measure('css-loading-time', 'critical-css-loaded', 'non-critical-css-loaded');
      const measure = performance.getEntriesByName('css-loading-time')[0];
      console.log(`CSS loading time: ${measure.duration}ms`);

      // Send to analytics if available
      if (typeof gtag !== 'undefined') {
        gtag('event', 'css_loading_time', {
          'value': measure.duration,
          'custom_parameter': 'fundus_img_xtract'
        });
      }
    }
  }
}

// Initialize monitoring
const cssMonitor = new CSSPerformanceMonitor();
```

### 2. CSS-in-JS for Dynamic Components

**Create `/static/js/dynamic-styles.js`:**
```javascript
// Dynamic CSS for medical imaging components
class DynamicStyleManager {
  constructor() {
    this.styleSheet = document.createElement('style');
    document.head.appendChild(this.styleSheet);
  }

  applyViewerFilter(filterName) {
    const filterCSS = `
      .imggr-main-img[data-filter="${filterName}"] {
        filter: url(#${filterName});
      }
    `;
    this.updateStyles(filterCSS);
  }

  updateViewerLayout(mode) {
    const layoutCSS = `
      .imggr-viewer-root[data-mode="${mode}"] .imggr-main {
        ${this.getLayoutStyles(mode)}
      }
    `;
    this.updateStyles(layoutCSS);
  }

  getLayoutStyles(mode) {
    switch(mode) {
      case 'fullscreen':
        return 'height: 100vh; width: 100vw; max-width: none;';
      case '1:1':
        return 'aspect-ratio: 1/1; height: 85vh; max-width: 90vh;';
      default:
        return '';
    }
  }

  updateStyles(css) {
    this.styleSheet.textContent += css;
  }

  clearStyles() {
    this.styleSheet.textContent = '';
  }
}
```

### 3. Automated CSS Testing

**Create `/scripts/css-audit.js`:**
```javascript
// Automated CSS audit script
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const css = require('css');

class CSSAuditor {
  constructor() {
    this.issues = [];
    this.stats = {
      totalRules: 0,
      duplicateRules: 0,
      unusedClasses: 0,
      optimizationPotential: 0
    };
  }

  async auditProject() {
    console.log('🔍 Starting CSS audit...');

    // Scan all CSS files
    await this.scanCSSFiles();

    // Scan HTML templates for class usage
    await this.scanHTMLTemplates();

    // Find unused classes
    this.findUnusedClasses();

    // Find duplicate rules
    this.findDuplicateRules();

    // Generate report
    this.generateReport();
  }

  async scanCSSFiles() {
    const cssFiles = this.findFiles('./static/css', '.css');

    for (const file of cssFiles) {
      const content = fs.readFileSync(file, 'utf8');
      const ast = css.parse(content);

      this.analyzeCSSAST(ast, file);
    }
  }

  async scanHTMLTemplates() {
    const htmlFiles = this.findFiles('./templates', '.html');

    for (const file of htmlFiles) {
      const content = fs.readFileSync(file, 'utf8');
      const dom = new JSDOM(content);

      this.extractUsedClasses(dom.window.document);
    }
  }

  generateReport() {
    const report = {
      timestamp: new Date().toISOString(),
      stats: this.stats,
      issues: this.issues,
      recommendations: this.generateRecommendations()
    };

    fs.writeFileSync(
      './css-audit-report.json',
      JSON.stringify(report, null, 2)
    );

    console.log('📊 CSS audit report generated: css-audit-report.json');
  }
}

// Run audit if called directly
if (require.main === module) {
  const auditor = new CSSAuditor();
  auditor.auditProject().catch(console.error);
}
```

### 4. CSS Bundle Optimization

**Create `/scripts/optimize-bundles.js`:**
```javascript
const postcss = require('postcss');
const cssnano = require('cssnano');
const autoprefixer = require('autoprefixer');

class BundleOptimizer {
  constructor() {
    this.plugins = [
      autoprefixer(),
      cssnano({
        preset: [
          'default',
          {
            discardComments: { removeAll: true },
            normalizeWhitespace: true,
            minifySelectors: true
          }
        ]
      })
    ];
  }

  async optimizeCSS(input, outputPath) {
    try {
      const result = await postcss(this.plugins).process(input, { from: undefined });

      const beforeSize = Buffer.byteLength(input, 'utf8');
      const afterSize = Buffer.byteLength(result.css, 'utf8');
      const savings = ((beforeSize - afterSize) / beforeSize * 100).toFixed(2);

      fs.writeFileSync(outputPath, result.css);

      console.log(`✅ Optimized ${outputPath}: ${savings}% size reduction`);
      console.log(`   Before: ${beforeSize} bytes, After: ${afterSize} bytes`);

      return { css: result.css, savings };
    } catch (error) {
      console.error(`❌ Error optimizing ${outputPath}:`, error);
      throw error;
    }
  }

  async optimizeAll() {
    const cssFiles = [
      'static/css/app.css',
      'static/css/help.css',
      'assets/scss/bootstrap-theme.scss'
    ];

    for (const file of cssFiles) {
      const input = fs.readFileSync(file, 'utf8');
      const outputPath = file.replace(/(\.css|\.scss)$/, '.min.css');

      await this.optimizeCSS(input, outputPath);
    }
  }
}
```

## Implementation Checklist

### Week 1: Quick Wins
- [ ] Remove duplicate `.scr-badge-enhanced` from app.css
- [ ] Remove duplicate `.pswp__pdfwrap` from app.css
- [ ] Remove duplicate `.style-guide-snippet` from app.css
- [ ] Fix incomplete `.page-box` CSS rule
- [ ] Replace custom `.vr` with Bootstrap utility
- [ ] Consolidate duplicate `.form-range` styles
- [ ] Test all pages for visual regression

### Week 2: Critical CSS & Modularization
- [ ] Extract critical CSS to separate file
- [ ] Update base template with critical CSS loading
- [ ] Split app.css into modular components
- [ ] Configure PurgeCSS for Bootstrap optimization
- [ ] Implement CSS loading performance monitoring
- [ ] Test Core Web Vitals improvement

### Week 3+: Advanced Optimizations
- [ ] Implement CSS-in-JS for dynamic components
- [ ] Set up automated CSS audit pipeline
- [ ] Create bundle optimization scripts
- [ ] Add CSS performance analytics
- [ ] Document maintenance procedures

## Expected Performance Improvements

### Immediate (Week 1)
- **CSS Size Reduction**: 5-10%
- **Duplicate Elimination**: ~50 lines removed
- **Maintenance**: Cleaner, more maintainable CSS

### Short-term (Week 2)
- **First Contentful Paint**: 15-25% improvement
- **CSS Bundle Size**: 20-30% reduction
- **Page Load Time**: 10-20% faster

### Long-term (Week 3+)
- **Maintainability**: Modular CSS architecture
- **Performance**: Ongoing optimization
- **Developer Experience**: Automated CSS auditing

## Risk Mitigation

### Testing Strategy
1. **Visual Regression Testing**: Use Playwright to screenshot all pages
2. **Performance Testing**: Measure Core Web Vitals before/after
3. **Cross-browser Testing**: Test in Chrome, Firefox, Safari
4. **Mobile Testing**: Verify responsive behavior

### Rollback Plan
1. **Git Branch Strategy**: Work in feature branch, merge via PR
2. **Backup Original Files**: Keep copies of original CSS files
3. **Gradual Rollout**: Deploy changes incrementally
4. **Monitoring**: Watch for performance regressions

This implementation plan provides a structured approach to CSS optimization with clear deliverables, timelines, and success metrics.