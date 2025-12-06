# Model Performance Analytics Handoff

## What was delivered
- Built the `/analytics/model-performance` page (Flask, Jinja, JS) using the `mvw_grading_data_all` materialized view. Access scoped by `get_user_lab_unit_ids_no_admin_override` for every user (including admin/data_manager). All filters and data operate only on lab units the user is allowed to see.
- Filters: required disease; AI model; upload type (zip/direct/all); camera; lab units (checkbox dropdown); reference source (consensus/arbitrator/resident/resident2); threshold; bootstrap samples; optional download to Excel; class builder.
- Class builder: drag-and-drop labels into user-defined classes; explicit “Add Class” and “Auto-fill” (one per label). Unassigned labels are dropped. Positive class selected via radio; class order preserved; rename/remove supported; reset button clears filters; no auto-create on disease change.
- Label recoding: `class_map` maps original labels to classes. Reference and prediction labels are recoded; any label not in a class is excluded from analysis. Positive class is mandatory for binary metrics. Uses image_uuid+disease to pair latest task per image; consensus pulled when task_state is final.
- Metrics (scikit-learn only): confusion matrix (prediction rows, reference columns) with totals and JS toggle for total/row/col %; per-label metrics; overall accuracy, balanced accuracy (shown as “weighted agreement”), Cohen’s kappa, weighted kappa. Binary metrics (positive vs rest) with bootstrap 95% CIs (sensitivity, specificity, PPV, NPV, F1, accuracy, balanced accuracy, kappa, weighted kappa, support/TP/FP/TN/FN). Binary metrics hidden with a warning for multi-class.
- ROC/AUC: parsed AI probability from grade comment `AI probability: <float>`; bootstrap CI; cleaned NaN/Inf; skip ROC/AUC when no probabilities. ROC chart is square and taller; confusion matrix plot generated via matplotlib `ConfusionMatrixDisplay` with YlGnBu cmap.
- Layout: Row 1 shows Binary Metrics card + Confusion Matrix table side by side. Row 2 shows ROC curve (Chart.js) + confusion matrix image side by side at matched heights. Metrics header cards summarize totals, accuracy, balanced agreement, and kappas.
- Mismatches: table with counts and filters (All/FP/FN), FP/FN badges, per-row PhotoSwipe “View” button, showing reference/predicted classes/labels, AI prob, lab unit, camera.
- Downloads: Excel export (openpyxl) includes raw labels, recoded classes, AI probability, lab unit, camera, hospital. Matplotlib output stored under `app/tmp/matplotlib` (MPLCONFIGDIR set).
- CSP-safe JS: all page logic moved to `static/js/model-performance.js`; base.html includes the new script plus PhotoSwipe and Chart.js links.

## Open decisions / nuances
- “Weighted agreement” currently uses balanced accuracy; confirm if another metric is desired.
- Binary metrics are hidden entirely when more than two classes remain; if you want binary-on-multiclass via one-vs-rest, we’d need UI/UX guidance.
- Positive class is mandatory; if the user removes the positive-class definition, the form blocks submission.
- ROC/AUC available only when probabilities exist and both classes present; bootstrap CIs require ≥20 cases; sample size capped at 10k resamples.
- Lab units shown only from `get_user_lab_unit_ids_no_admin_override`; admin does not see all units by default.

## Quick how-to
- Run: `uv run app.py` (port 5001).
- Navigate: Analytics → Model Performance.
- Build classes: use drag/drop, set one positive class. Unassigned labels are dropped.
- Download analyzed rows: “Download Excel” on the confusion matrix card.

## Next steps (suggested)
1) Clarify “Weighted agreement” definition if balanced accuracy is not the intended measure.
2) Decide if binary metrics should still display in multiclass via selected positive class (one-vs-rest) or remain hidden.
3) Add server-side validation for minimum case count per class if needed for stability.
4) Consider caching queries/plots for large datasets or repeated filter sets.
5) Improve UI hints for probability parsing (e.g., show count of rows with usable AI probability).*** End Patch
