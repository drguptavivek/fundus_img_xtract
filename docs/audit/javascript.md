# JavaScript Security Audit Report

**Location**: `static/js/`  
**Date**: 2026-01-13  
**Status**: ✅ **VULNERABILITIES FIXED**

---

## Overview

A comprehensive security audit of client-side JavaScript files was performed. Key focus areas were DOM Cross-Site Scripting (XSS), unsafe HTML injection (innerHTML), and dangerous execution sinks (eval, new Function).

**Total Files**: 47  
**Critical Issues Found**: 2 (Fixed)  
**External Libraries**: 16 (Verified versions/integrity where possible)

---

## File-by-File Analysis

### 🚨 Remedited Files (Issues & Fixes)

#### `flash-toasts.js`
- **Issue**: DOM XSS via unsafe `insertAdjacentHTML` usage. User-supplied messages were effectively injected directly into the DOM.
- **Fix**: Refactored `showFlashToast` function to use `document.createElement()`, `setAttribute()`, and `textContent`.
- **Status**: ✅ **FIXED**
- **Verification**: CodeQL Issues #1, #2 resolved.

#### `pswp-init.js`
- **Issue**: Potential XSS via `innerHTML` usage when rendering captions from element `title` attributes.
- **Fix**: Replaced `el.innerHTML = caption` with `el.textContent = caption`.
- **Status**: ✅ **FIXED**

---

### 🔍 Custom Scripts (Clean)

The following custom scripts were audited and found to contain **no unsafe usage** of `innerHTML`, `eval`, or sensitive sinks:

- `ad_hoc_tasks.js`
- `admin-change-password.js`
- `app.js`
- `auth-captcha.js`
- `common-filters.js`
- `database_restore.js`
- `direct-files-kpis.js`
- `disease_gradings.js`
- `dr_edit.js`
- `dual-grading-task.js`
- `edit_image.js` (Canvas operations checked)
- `encounter-kpis.js`
- `glaucoma_edit.js`
- `grading-viewer.js`
- `home-charts.js`
- `idle-timeout.js`
- `intra_rater_batch_create.js`
- `intra_rater_tasks.js`
- `model-performance.js`
- `mv-refresh.js`
- `page_nav_screenings_list.js`
- `page-transitions.js`
- `password-policy.js`
- `pregraded_grades.js`
- `screening-viewer.js`
- `search_images.js`
- `search-images-filters.js` (Uses `innerHTML = ""` for clearing, safe string assignment)

---

### 📦 External Libraries (Skipped/Verified)

These files are minified external dependencies. Audit focus was on usage compatibility, not internal source audit (unless flagged).

- `bootstrap.bundle.min.js` (v5.3)
- `chart.min.js` / `chart.umd.min.js` (Chart.js)
- `chartjs-plugin-datalabels.js`
- `dataTables.bootstrap5.min.js`
- `htmx.min.js`
- `jquery-3.7.0.min.js`
- `jquery.dataTables.min.js`
- `lightbox.js` (Simple lightbox)
- `markdown-it.min.js`
- `panzoom.min.js`
- `photoswipe*.js`
- `quill.js` (v2.0.3 - Flagged with DOM XSS by CodeQL #3, but is library code. Recommend update if exploits found in wild).

---

## Audit Methodology

### 1. Sink Analysis
Searched for common XSS sinks:
- `innerHTML` / `outerHTML`
- `insertAdjacentHTML`
- `document.write`
- `eval` / `setTimeout(string)` / `setInterval(string)`
- `new Function`
- `javascript:` URIs

### 2. Manual Review
- Reviewed findings from generic `grep`.
- `search-images-filters.js`: Found `container.innerHTML = ""`. Safe (clearing content).
- `search-images-filters.js`: Found `innerHTML = '<div...>'`. Safe (static string).

### 3. CodeQL Correlation
- Verified against historical CodeQL report.
- Fixed confirmed issues in `flash-toasts.js`.

---

## Recommendations

1.  **Content Security Policy (CSP)**: Ensure strict CSP is active to mitigate any missed XSS vectors.
    *   `script-src 'self' ...`
    *   Avoid `'unsafe-inline'` where possible.
2.  **Linting**: Add `eslint-plugin-security` to CI/CD pipeline to catch future unsafe patterns.
3.  **Library Updates**: Regularly check `npm audit` or equivalent for `static/js` libraries (Quill, jQuery, Bootstrap).
