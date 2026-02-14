(function () {
  const MODES = {
    ROI: "roi",
    POLYGON: "polygon",
    ELLIPSE: "ellipse",
    ADD: "add",
    SUBTRACT: "subtract",
    MOVE: "move",
    PAN: "pan",
  };

  const GRID_MIN = 3;
  const GRID_MAX = 32;
  const DEFAULT_GRID = 8;
  const AUTO_FOCUS_MARGIN = 0.15;
  const POLYGON_CLOSE_RADIUS_PX = 12;
  const ELLIPSE_SEGMENTS = 24;
  const BOX_HANDLE_RADIUS_PX = 10;

  const state = {
    viewerRoot: null,
    main: null,
    mainImg: null,
    canvas: null,
    ctx: null,
    contexts: new Map(),
    activeContextKey: null,
    activeFeatureId: null,
    mode: MODES.ROI,
    tempPan: false,
    drawing: null,
    pointDrag: null,
    painting: null,
    overlayVisible: true,
    rafId: null,
    observersReady: false,
    quickBindingsDone: false,
    refreshQueued: false,
    featuresObservers: [],
    imageMutationObserver: null,
    imageResizeObserver: null,
    boxActionsEl: null,
    selectedBoxRef: null,
  };

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function toInt(v, fallback) {
    const n = Number(v);
    if (Number.isNaN(n)) return fallback;
    return Math.trunc(n);
  }

  function safeParse(raw) {
    if (!raw || typeof raw !== "string") return null;
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function ensureStyle() {
    if (document.getElementById("feature-geometry-editor-style")) return;
    const style = document.createElement("style");
    style.id = "feature-geometry-editor-style";
    style.textContent = `
      .fgx-overlay-canvas { position:absolute; inset:0; width:100%; height:100%; z-index:15; cursor:crosshair; }
      .fgx-panel { display:flex; flex-direction:column; gap:.5rem; }
      .fgx-group { display:flex; flex-wrap:wrap; gap:.35rem; align-items:center; }
      .fgx-toolbar .btn { min-width:2.4rem; }
      .fgx-feature-row { display:flex; gap:.35rem; align-items:center; }
      .fgx-color-dot { width:.75rem; height:.75rem; border-radius:999px; display:inline-block; border:1px solid rgba(0,0,0,.2); }
      .fgx-grid-row { display:flex; gap:.35rem; align-items:center; }
      .fgx-feature-row select, .fgx-grid-row select { width:100%; min-width:0; }
      .fgx-toolbar .btn.active { font-weight:600; }
      .fgx-block-label { font-size:.73rem; color:var(--bs-secondary-color); text-transform:uppercase; letter-spacing:.03em; }
      .fgx-ann-actions { display:flex; flex-wrap:nowrap; gap:.25rem; }
      .fgx-ann-actions .btn { width:2rem; min-width:2rem; padding:.2rem .25rem; display:inline-flex; align-items:center; justify-content:center; }
      .fgx-box-actions .btn { width:1.85rem; min-width:1.85rem; padding:.18rem .2rem; display:inline-flex; align-items:center; justify-content:center; }
      .fgx-box-actions .btn { background: #f3f4f6; }
      [data-bs-theme="dark"] .fgx-box-actions .btn { background: rgba(148, 163, 184, 0.2); }
    `;
    document.head.appendChild(style);
  }

  function getImageMetrics() {
    if (!state.main || !state.mainImg) return null;
    const mainRect = state.main.getBoundingClientRect();
    const imgRect = state.mainImg.getBoundingClientRect();
    const naturalWidth = state.mainImg.naturalWidth || 0;
    const naturalHeight = state.mainImg.naturalHeight || 0;
    if (!mainRect.width || !mainRect.height || !imgRect.width || !imgRect.height || !naturalWidth || !naturalHeight) {
      return null;
    }
    return { mainRect, imgRect, naturalWidth, naturalHeight };
  }

  function clientToPixel(clientX, clientY) {
    const m = getImageMetrics();
    if (!m) return null;
    const x = ((clientX - m.imgRect.left) / m.imgRect.width) * m.naturalWidth;
    const y = ((clientY - m.imgRect.top) / m.imgRect.height) * m.naturalHeight;
    return [clamp(x, 0, m.naturalWidth), clamp(y, 0, m.naturalHeight)];
  }

  function pixelToCanvas(point) {
    const m = getImageMetrics();
    if (!m || !point) return null;
    const x = (point[0] / m.naturalWidth) * m.imgRect.width + (m.imgRect.left - m.mainRect.left);
    const y = (point[1] / m.naturalHeight) * m.imgRect.height + (m.imgRect.top - m.mainRect.top);
    return [x, y];
  }

  function normPoint(point) {
    const m = getImageMetrics();
    if (!m) return [0, 0];
    return [
      clamp(point[0] / m.naturalWidth, 0, 1),
      clamp(point[1] / m.naturalHeight, 0, 1),
    ];
  }

  function isContextVisible(ctx) {
    if (!ctx || !ctx.sectionEl) return false;
    if (ctx.sectionEl.style.display === "none") return false;
    const panel = ctx.sectionEl.closest(".linked-grading-panel");
    if (!panel) return true;
    const item = panel.closest(".carousel-item");
    return !item || item.classList.contains("active");
  }

  function getSelectedFeatureIds(ctx) {
    if (!ctx || !ctx.featuresContainerEl) return [];
    const boxes = ctx.featuresContainerEl.querySelectorAll('input[type="checkbox"]:checked');
    const ids = [];
    boxes.forEach((b) => {
      const n = Number(b.value);
      if (!Number.isNaN(n)) ids.push(n);
    });
    return ids;
  }

  function getFeatureLabel(ctx, featureId) {
    if (!ctx || !ctx.featuresContainerEl) return `Feature ${featureId}`;
    const box = ctx.featuresContainerEl.querySelector(`input[type="checkbox"][value="${featureId}"]`);
    if (!box) return `Feature ${featureId}`;
    const label = ctx.featuresContainerEl.querySelector(`label[for="${box.id}"]`);
    return label ? label.textContent.trim() : `Feature ${featureId}`;
  }

  function createEmptyPayload(grid) {
    return {
      version: 1,
      grid: { rows: grid, cols: grid },
      items: [],
    };
  }

  function sanitizeGrid(value) {
    const parsed = toInt(value, DEFAULT_GRID);
    return clamp(parsed, GRID_MIN, GRID_MAX);
  }

  function sanitizePayload(raw, fallbackGrid) {
    const grid = sanitizeGrid(raw?.grid?.rows ?? raw?.grid?.cols ?? fallbackGrid ?? DEFAULT_GRID);
    const payload = createEmptyPayload(grid);

    if (!raw || typeof raw !== "object" || !Array.isArray(raw.items)) return payload;

    raw.items.forEach((item) => {
      if (!item || typeof item !== "object") return;
      const featureId = Number(item.feature_id);
      if (Number.isNaN(featureId)) return;

      const roiPixel = Array.isArray(item?.roi?.pixel) ? item.roi.pixel : null;
      const polygonPixel = Array.isArray(item?.polygon?.pixel) ? item.polygon.pixel : null;
      const maskRows = sanitizeGrid(item?.mask?.rows ?? grid);
      const maskCols = sanitizeGrid(item?.mask?.cols ?? grid);
      const cellsRaw = Array.isArray(item?.mask?.cells) ? item.mask.cells : [];

      const clean = {
        feature_id: featureId,
        feature_label: typeof item.feature_label === "string" ? item.feature_label : null,
        roi: normalizeRoi(roiPixel),
        polygon: normalizePolygon(polygonPixel),
        mask: {
          rows: maskRows,
          cols: maskCols,
          cells: normalizeCells(cellsRaw, maskRows, maskCols),
        },
      };

      payload.items.push(clean);
    });

    return payload;
  }

  function normalizeRoi(roiPixel) {
    if (!Array.isArray(roiPixel) || roiPixel.length !== 2) return null;
    const p1 = asPoint(roiPixel[0]);
    const p2 = asPoint(roiPixel[1]);
    if (!p1 || !p2) return null;
    return reorderRoi([p1, p2]);
  }

  function normalizePolygon(points) {
    if (!Array.isArray(points)) return [];
    const out = [];
    points.forEach((p) => {
      const pt = asPoint(p);
      if (pt) out.push(pt);
    });
    return out;
  }

  function normalizeCells(cells, rows, cols) {
    const set = new Set();
    const out = [];
    cells.forEach((c) => {
      if (!Array.isArray(c) || c.length !== 2) return;
      const r = toInt(c[0], -1);
      const cl = toInt(c[1], -1);
      if (r < 0 || cl < 0 || r >= rows || cl >= cols) return;
      const k = `${r}:${cl}`;
      if (set.has(k)) return;
      set.add(k);
      out.push([r, cl]);
    });
    return out;
  }

  function asPoint(v) {
    if (!Array.isArray(v) || v.length !== 2) return null;
    const x = Number(v[0]);
    const y = Number(v[1]);
    if (Number.isNaN(x) || Number.isNaN(y)) return null;
    return [x, y];
  }

  function reorderRoi(roi) {
    const x1 = Math.min(roi[0][0], roi[1][0]);
    const x2 = Math.max(roi[0][0], roi[1][0]);
    const y1 = Math.min(roi[0][1], roi[1][1]);
    const y2 = Math.max(roi[0][1], roi[1][1]);
    return [[x1, y1], [x2, y2]];
  }

  function isCompleteItem(item) {
    if (!item || !item.roi) return false;
    return true;
  }

  function buildSerializablePayload(ctx) {
    const selectedIds = new Set(getSelectedFeatureIds(ctx));
    const grid = sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID);

    const items = (ctx.payload.items || [])
      .filter((it) => selectedIds.has(it.feature_id) && isCompleteItem(it))
      .map((item) => {
        const roi = reorderRoi(item.roi);
        const polygonRaw = Array.isArray(item.polygon) && item.polygon.length >= 3
          ? item.polygon
          : [
              [roi[0][0], roi[0][1]],
              [roi[1][0], roi[0][1]],
              [roi[1][0], roi[1][1]],
              [roi[0][0], roi[1][1]],
            ];
        const polygon = polygonRaw.map((p) => [Number(p[0]), Number(p[1])]);
        const rows = sanitizeGrid(item.mask.rows ?? grid);
        const cols = sanitizeGrid(item.mask.cols ?? grid);
        const cells = normalizeCells(item.mask.cells || [], rows, cols);
        return {
          feature_id: item.feature_id,
          feature_label: item.feature_label || getFeatureLabel(ctx, item.feature_id),
          roi: {
            type: "box",
            pixel: roi,
            norm: [normPoint(roi[0]), normPoint(roi[1])],
          },
          polygon: {
            pixel: polygon,
            norm: polygon.map(normPoint),
          },
          mask: {
            rows,
            cols,
            cells,
          },
          dicom: {
            tracking_id: `feature-${item.feature_id}`,
          },
        };
      });

    if (!items.length) {
      return "";
    }

    return JSON.stringify({
      version: 1,
      grid: { rows: grid, cols: grid },
      items,
    });
  }

  function ensureItemIdentity(ctx, item) {
    if (!item) return;
    if (typeof item._annId !== "number") {
      item._annId = ctx.nextAnnotationId;
      ctx.nextAnnotationId += 1;
      return;
    }
    if (item._annId >= ctx.nextAnnotationId) {
      ctx.nextAnnotationId = item._annId + 1;
    }
  }

  function getItemsForFeature(ctx, featureId) {
    const out = (ctx.payload.items || []).filter((it) => it.feature_id === featureId);
    out.forEach((it) => ensureItemIdentity(ctx, it));
    return out.sort((a, b) => (a._annId || 0) - (b._annId || 0));
  }

  function createAnnotationItem(ctx, featureId) {
    const item = {
      _annId: ctx.nextAnnotationId,
      feature_id: featureId,
      feature_label: getFeatureLabel(ctx, featureId),
      _geometryType: "box",
      roi: null,
      polygon: [],
      mask: {
        rows: sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID),
        cols: sanitizeGrid(ctx.payload?.grid?.cols ?? DEFAULT_GRID),
        cells: [],
      },
    };
    ctx.nextAnnotationId += 1;
    ctx.payload.items.push(item);
    ctx.activeAnnotationByFeature[featureId] = item._annId;
    return item;
  }

  function getActiveAnnotationItem(ctx, createIfMissing = false) {
    const featureId = state.activeFeatureId;
    if (featureId == null) return null;
    const items = getItemsForFeature(ctx, featureId);
    if (!items.length) {
      return createIfMissing ? createAnnotationItem(ctx, featureId) : null;
    }
    const selectedAnnId = ctx.activeAnnotationByFeature[featureId];
    const selected = items.find((it) => it._annId === selectedAnnId);
    if (selected) {
      selected.feature_label = getFeatureLabel(ctx, featureId);
      return selected;
    }
    ctx.activeAnnotationByFeature[featureId] = items[0]._annId;
    items[0].feature_label = getFeatureLabel(ctx, featureId);
    return items[0];
  }

  function removeAnnotationItem(ctx, item) {
    if (!item) return;
    if (isSelectedBox(ctx, item)) {
      clearSelectedBox();
    }
    const featureId = item.feature_id;
    ctx.payload.items = (ctx.payload.items || []).filter((it) => it !== item);
    const remaining = getItemsForFeature(ctx, featureId);
    if (!remaining.length) {
      delete ctx.activeAnnotationByFeature[featureId];
      return;
    }
    ctx.activeAnnotationByFeature[featureId] = remaining[0]._annId;
  }

  function setStatus(ctx, text) {
    return;
  }

  function clearSelectedBox() {
    state.selectedBoxRef = null;
  }

  function setSelectedBox(ctx, annOrItem) {
    if (!ctx || annOrItem == null) {
      clearSelectedBox();
      return;
    }
    const annId = typeof annOrItem === "number" ? annOrItem : Number(annOrItem?._annId);
    if (Number.isNaN(annId)) {
      clearSelectedBox();
      return;
    }
    state.selectedBoxRef = { ctxKey: ctx.key, annId };
  }

  function isSelectedBox(ctx, item) {
    if (!ctx || !item || !state.selectedBoxRef) return false;
    return state.selectedBoxRef.ctxKey === ctx.key && state.selectedBoxRef.annId === item._annId;
  }

  function activeContext() {
    if (!state.activeContextKey) return null;
    return state.contexts.get(state.activeContextKey) || null;
  }

  function effectiveMode() {
    return state.tempPan ? MODES.PAN : state.mode;
  }

  function setCanvasPointerMode() {
    if (!state.canvas) return;
    const mode = effectiveMode();
    state.canvas.style.pointerEvents = mode === MODES.PAN ? "none" : "auto";
    state.canvas.style.cursor = mode === MODES.MOVE ? "move" : (mode === MODES.PAN ? "default" : "crosshair");
  }

  function ensureBoxActions() {
    if (state.boxActionsEl || !state.main) return;
    const wrap = document.createElement("div");
    wrap.className = "fgx-box-actions position-absolute gap-1";
    wrap.style.zIndex = "30";
    wrap.style.display = "none";
    wrap.innerHTML = `
      <button type="button" class="btn btn-outline-success btn-sm" data-fgx-box-done title="Done" aria-label="Done">
        <i class="fa-solid fa-check"></i>
      </button>
      <button type="button" class="btn btn-outline-primary btn-sm" data-fgx-box-dup title="Duplicate" aria-label="Duplicate">
        <i class="fa-solid fa-copy"></i>
      </button>
      <button type="button" class="btn btn-outline-danger btn-sm" data-fgx-box-del title="Delete" aria-label="Delete">
        <i class="fa-solid fa-trash"></i>
      </button>
    `;
    state.main.appendChild(wrap);
    state.boxActionsEl = wrap;

    wrap.querySelector("[data-fgx-box-done]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? getActiveAnnotationItem(ctx, false) : null;
      if (!ctx || !item || !item.roi) return;
      setSelectedBox(ctx, item);
      syncField(ctx);
      state.mode = MODES.PAN;
      setCanvasPointerMode();
      refreshToolbarStates();
      redraw();
    });

    wrap.querySelector("[data-fgx-box-dup]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? getActiveAnnotationItem(ctx, false) : null;
      if (!ctx || !item || !item.roi || state.activeFeatureId == null) return;
      const src = reorderRoi(item.roi);
      const dx = Math.max(10, (src[1][0] - src[0][0]) * 0.08);
      const dy = Math.max(10, (src[1][1] - src[0][1]) * 0.08);
      const dup = createAnnotationItem(ctx, state.activeFeatureId);
      dup.roi = [
        [src[0][0] + dx, src[0][1] + dy],
        [src[1][0] + dx, src[1][1] + dy],
      ];
      dup._geometryType = "box";
      setSelectedBox(ctx, dup);
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-del]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? getActiveAnnotationItem(ctx, false) : null;
      if (!ctx || !item) return;
      if (!window.confirm("Delete selected box?")) return;
      removeAnnotationItem(ctx, item);
      clearSelectedBox();
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      syncField(ctx);
      redraw();
    });
  }

  function positionBoxActions() {
    if (!state.boxActionsEl || !state.main) return;
    const ctx = activeContext();
    const item = ctx ? getActiveAnnotationItem(ctx, false) : null;
    const selectedFeatures = ctx ? getSelectedFeatureIds(ctx) : [];
    if (
      !ctx ||
      !item ||
      !item.roi ||
      !isSelectedBox(ctx, item) ||
      item._hidden ||
      !state.overlayVisible ||
      !selectedFeatures.includes(item.feature_id)
    ) {
      state.boxActionsEl.style.display = "none";
      return;
    }
    if (state.drawing && state.drawing.kind === "roi") {
      state.boxActionsEl.style.display = "none";
      return;
    }
    const roi = reorderRoi(item.roi);
    const boxW = Math.abs(roi[1][0] - roi[0][0]);
    const boxH = Math.abs(roi[1][1] - roi[0][1]);
    if (boxW < 4 || boxH < 4) {
      state.boxActionsEl.style.display = "none";
      return;
    }
    const p1 = pixelToCanvas(roi[0]);
    const p2 = pixelToCanvas(roi[1]);
    if (!p1 || !p2) {
      state.boxActionsEl.style.display = "none";
      return;
    }
    const x = (Math.min(p1[0], p2[0]) + Math.max(p1[0], p2[0])) / 2;
    const y = Math.max(p1[1], p2[1]) + 8;
    state.boxActionsEl.style.left = `${x}px`;
    state.boxActionsEl.style.top = `${y}px`;
    state.boxActionsEl.style.transform = "translateX(-50%)";
    state.boxActionsEl.style.display = "flex";
  }

  function hideBoxActions() {
    if (state.boxActionsEl) {
      state.boxActionsEl.style.display = "none";
    }
  }

  function setPanLock(flag) {
    if (!state.viewerRoot) return;
    state.viewerRoot.dataset.imggrPanLocked = flag ? "true" : "false";
    try {
      state.viewerRoot.__imggrState?.refreshLockState?.();
    } catch (_) {}
    updateQuickLockUi();
  }

  function updateQuickLockUi() {
    const quickLockBtn = document.querySelector("[data-fgx-quick-lock]");
    const locked = state.viewerRoot?.dataset?.imggrPanLocked === "true";
    if (quickLockBtn) {
      quickLockBtn.classList.toggle("active", !!locked);
      quickLockBtn.title = locked ? "Unlock image position" : "Lock image position";
      quickLockBtn.setAttribute("aria-label", locked ? "Unlock image position" : "Lock image position");
      quickLockBtn.innerHTML = locked
        ? '<i class="fa-solid fa-lock"></i><span class="visually-hidden">Unlock</span>'
        : '<i class="fa-solid fa-lock-open"></i><span class="visually-hidden">Lock</span>';
    }
  }

  function pickActiveContext() {
    let chosen = null;
    state.contexts.forEach((ctx) => {
      if (!chosen && isContextVisible(ctx)) {
        chosen = ctx.key;
      }
    });
    state.activeContextKey = chosen;
    if (!chosen || (state.selectedBoxRef && state.selectedBoxRef.ctxKey !== chosen)) {
      clearSelectedBox();
    }
    return chosen;
  }

  function syncFeatureSelection(ctx) {
    if (!ctx) return;
    const selected = getSelectedFeatureIds(ctx);
    if (!selected.length) return;
    if (!selected.includes(state.activeFeatureId)) {
      state.activeFeatureId = selected[0];
    }
  }

  function updatePanelFeatureOptions(ctx) {
    if (!ctx || !ctx.featureSelectEl || !ctx.annotationSelectEl) return;
    const selected = getSelectedFeatureIds(ctx);
    const previous = state.activeFeatureId;
    const selectedSet = new Set(selected.map((id) => String(id)));
    const existingOptions = Array.from(ctx.featureSelectEl.options);

    existingOptions.forEach((opt) => {
      if (!selectedSet.has(opt.value)) {
        opt.remove();
      }
    });
    selected.forEach((featureId) => {
      const value = String(featureId);
      const existing = ctx.featureSelectEl.querySelector(`option[value="${value}"]`);
      if (!existing) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = getFeatureLabel(ctx, featureId);
        ctx.featureSelectEl.appendChild(option);
      } else {
        existing.textContent = getFeatureLabel(ctx, featureId);
      }
    });

    if (!selected.length) {
      ctx.featureSelectEl.disabled = true;
      ctx.annotationSelectEl.disabled = true;
      if (ctx.addAnnotationBtn) ctx.addAnnotationBtn.disabled = true;
      if (ctx.removeAnnotationBtn) ctx.removeAnnotationBtn.disabled = true;
      return;
    }

    ctx.featureSelectEl.disabled = false;
    if (ctx.addAnnotationBtn) ctx.addAnnotationBtn.disabled = false;
    const next = selected.includes(previous) ? previous : selected[0];
    state.activeFeatureId = next;
    ctx.featureSelectEl.value = String(next);
    updateFeatureColorChip(ctx, next);
    updateAnnotationOptions(ctx);
  }

  function updateAnnotationOptions(ctx) {
    if (!ctx || !ctx.annotationSelectEl || state.activeFeatureId == null) return;
    const featureId = state.activeFeatureId;
    const items = getItemsForFeature(ctx, featureId);
    ctx.annotationSelectEl.innerHTML = "";

    items.forEach((item, idx) => {
      const option = document.createElement("option");
      option.value = String(item._annId);
      option.textContent = `${item._hidden ? "○" : "●"} Ann ${idx + 1}`;
      ctx.annotationSelectEl.appendChild(option);
    });

    if (!items.length) {
      ctx.annotationSelectEl.disabled = true;
      if (ctx.removeAnnotationBtn) ctx.removeAnnotationBtn.disabled = true;
      clearSelectedBox();
      return;
    }

    ctx.annotationSelectEl.disabled = false;
    if (ctx.removeAnnotationBtn) ctx.removeAnnotationBtn.disabled = false;
    const currentAnnId = ctx.activeAnnotationByFeature[featureId];
    const current = items.find((it) => it._annId === currentAnnId) || items[0];
    ctx.activeAnnotationByFeature[featureId] = current._annId;
    ctx.annotationSelectEl.value = String(current._annId);
    refreshAnnotationButtons(ctx);
  }

  function refreshAnnotationButtons(ctx) {
    const item = getActiveAnnotationItem(ctx, false);
    if (!item) {
      if (ctx.viewAnnotationBtn) ctx.viewAnnotationBtn.disabled = true;
      if (ctx.editAnnotationBtn) ctx.editAnnotationBtn.disabled = true;
      if (ctx.removeAnnotationBtn) ctx.removeAnnotationBtn.disabled = true;
      return;
    }
    if (ctx.viewAnnotationBtn) {
      ctx.viewAnnotationBtn.disabled = false;
      if (item._hidden) {
        ctx.viewAnnotationBtn.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
        ctx.viewAnnotationBtn.title = "Show annotation";
        ctx.viewAnnotationBtn.setAttribute("aria-label", "Show annotation");
      } else {
        ctx.viewAnnotationBtn.innerHTML = '<i class="fa-solid fa-eye"></i>';
        ctx.viewAnnotationBtn.title = "Hide annotation";
        ctx.viewAnnotationBtn.setAttribute("aria-label", "Hide annotation");
      }
    }
    if (ctx.editAnnotationBtn) {
      ctx.editAnnotationBtn.disabled = false;
      ctx.editAnnotationBtn.classList.add("active");
    }
    if (ctx.removeAnnotationBtn) {
      ctx.removeAnnotationBtn.disabled = false;
    }
  }

  function updateFeatureColorChip(ctx, featureId) {
    if (!ctx || !ctx.colorChipEl) return;
    if (!window.FeatureGeometryColors || typeof window.FeatureGeometryColors.colorForFeature !== "function") return;
    ctx.colorChipEl.style.backgroundColor = window.FeatureGeometryColors.colorForFeature(featureId);
  }

  function ensurePanel(ctx) {
    if (ctx.panelTopEl && ctx.panelBottomEl) return;
    const sidebarHost = document.querySelector("[data-geometry-sidebar-host]");
    if (!sidebarHost) return;

    const panel = document.createElement("div");
    panel.className = "fgx-panel";
    panel.dataset.geometryContextKey = ctx.key;
    panel.innerHTML = `
      <div class="fgx-block-label">Feature</div>
      <div class="fgx-group fgx-feature-row">
        <span class="fgx-color-dot" data-fgx-color></span>
        <select class="form-select form-select-sm" data-fgx-feature></select>
      </div>

      <div class="fgx-block-label">Annotation</div>
      <div class="fgx-group fgx-feature-row">
        <select class="form-select form-select-sm" data-fgx-annotation></select>
      </div>
      <div class="fgx-group fgx-ann-actions" aria-label="Annotation actions">
        <button type="button" class="btn btn-success btn-sm" data-fgx-ann-add title="Add annotation" aria-label="Add annotation">
          <i class="fa-solid fa-plus"></i>
        </button>
        <button type="button" class="btn btn-primary btn-sm" data-fgx-ann-view title="Hide annotation" aria-label="Hide annotation">
          <i class="fa-solid fa-eye"></i>
        </button>
        <button type="button" class="btn btn-warning btn-sm" data-fgx-ann-edit title="Edit selected annotation" aria-label="Edit selected annotation">
          <i class="fa-solid fa-pencil"></i>
        </button>
        <button type="button" class="btn btn-danger btn-sm" data-fgx-ann-remove title="Delete selected annotation" aria-label="Delete selected annotation">
          <i class="fa-solid fa-eraser"></i>
        </button>
      </div>

      <div class="fgx-block-label">Box</div>
      <div class="fgx-group">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-add-box>+ Add Box</button>
      </div>
    `;
    sidebarHost.appendChild(panel);

    ctx.panelTopEl = panel;
    ctx.panelBottomEl = panel;
    ctx.featureSelectEl = panel.querySelector("[data-fgx-feature]");
    ctx.annotationSelectEl = panel.querySelector("[data-fgx-annotation]");
    ctx.addAnnotationBtn = panel.querySelector("[data-fgx-ann-add]");
    ctx.viewAnnotationBtn = panel.querySelector("[data-fgx-ann-view]");
    ctx.editAnnotationBtn = panel.querySelector("[data-fgx-ann-edit]");
    ctx.removeAnnotationBtn = panel.querySelector("[data-fgx-ann-remove]");
    ctx.lockBtn = null;
    ctx.colorChipEl = panel.querySelector("[data-fgx-color]");
    ctx.gridInputEl = null;
    ctx.gridLabelEl = null;
    ctx.statusEl = null;
    ctx.toggleOverlayBtn = null;
    ctx.saveBtn = null;
    ctx.saveAddBtn = null;
    ctx.addPointBtn = null;
    ctx.subPointBtn = null;
    ctx.clearBtn = null;

    if (!state.quickBindingsDone) {
      const quickPanBtn = document.querySelector("[data-fgx-quick-pan]");
      const quickLockBtn = document.querySelector("[data-fgx-quick-lock]");
      if (quickPanBtn) {
        quickPanBtn.addEventListener("click", () => {
          state.mode = MODES.PAN;
          setCanvasPointerMode();
          refreshToolbarStates();
        });
      }
      if (quickLockBtn) {
        quickLockBtn.addEventListener("click", () => {
          const nowLocked = state.viewerRoot?.dataset?.imggrPanLocked === "true";
          setPanLock(!nowLocked);
          updateQuickLockUi();
        });
      }
      state.quickBindingsDone = true;
    }

    ctx.featureSelectEl.addEventListener("change", () => {
      const id = Number(ctx.featureSelectEl.value);
      if (Number.isNaN(id)) return;
      state.activeFeatureId = id;
      clearSelectedBox();
      updateFeatureColorChip(ctx, id);
      updateAnnotationOptions(ctx);
      redraw();
    });

    ctx.annotationSelectEl.addEventListener("change", () => {
      if (state.activeFeatureId == null) return;
      const annId = Number(ctx.annotationSelectEl.value);
      if (Number.isNaN(annId)) return;
      ctx.activeAnnotationByFeature[state.activeFeatureId] = annId;
      setSelectedBox(ctx, annId);
      refreshAnnotationButtons(ctx);
      redraw();
    });

    ctx.addAnnotationBtn.addEventListener("click", () => {
      if (state.activeFeatureId == null) return;
      createAnnotationItem(ctx, state.activeFeatureId);
      clearSelectedBox();
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      syncField(ctx);
      redraw();
    });

    ctx.viewAnnotationBtn.addEventListener("click", () => {
      const item = getActiveAnnotationItem(ctx, false);
      if (!item) return;
      item._hidden = !item._hidden;
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      redraw();
    });

    ctx.editAnnotationBtn.addEventListener("click", () => {
      const item = getActiveAnnotationItem(ctx, false);
      if (!item) return;
      ctx.activeAnnotationByFeature[item.feature_id] = item._annId;
      refreshAnnotationButtons(ctx);
      redraw();
    });

    ctx.removeAnnotationBtn.addEventListener("click", () => {
      const item = getActiveAnnotationItem(ctx, false);
      if (!item) return;
      if (!window.confirm("Delete selected annotation?")) return;
      removeAnnotationItem(ctx, item);
      clearSelectedBox();
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      syncField(ctx);
      redraw();
    });

    panel.querySelector("[data-fgx-add-box]")?.addEventListener("click", () => {
      if (state.activeFeatureId == null) return;
      const item = createAnnotationItem(ctx, state.activeFeatureId);
      item._geometryType = "box";
      setSelectedBox(ctx, item);
      setPanLock(true);
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      state.mode = MODES.ROI;
      setCanvasPointerMode();
      refreshToolbarStates();
      syncField(ctx);
      redraw();
    });

    refreshAnnotationButtons(ctx);
  }

  function refreshToolbarStates() {
    const ctx = activeContext();
    if (!ctx || !ctx.panelBottomEl) return;
    ctx.panelBottomEl.querySelectorAll("[data-fgx-mode]").forEach((btn) => {
      const active = btn.dataset.fgxMode === state.mode;
      btn.classList.toggle("active", active);
      btn.classList.toggle("btn-primary", active);
      btn.classList.toggle("btn-outline-secondary", !active);
    });
    const quickPanBtn = document.querySelector("[data-fgx-quick-pan]");
    if (quickPanBtn) {
      quickPanBtn.classList.toggle("active", state.mode === MODES.PAN);
    }
    const quickLockBtn = document.querySelector("[data-fgx-quick-lock]");
    if (quickLockBtn) updateQuickLockUi();
  }

  function updateGridLabel(ctx) {
    if (!ctx || !ctx.gridInputEl) return;
    const s = sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID);
    if (ctx.gridInputEl) ctx.gridInputEl.value = String(s);
  }

  function applyGridSize(ctx, size) {
    const grid = sanitizeGrid(size);
    if (!ctx.payload.grid) {
      ctx.payload.grid = { rows: grid, cols: grid };
    }
    const oldRows = sanitizeGrid(ctx.payload.grid.rows || grid);
    const oldCols = sanitizeGrid(ctx.payload.grid.cols || grid);
    ctx.payload.grid.rows = grid;
    ctx.payload.grid.cols = grid;

    (ctx.payload.items || []).forEach((item) => {
      const currentRows = sanitizeGrid(item.mask?.rows ?? oldRows);
      const currentCols = sanitizeGrid(item.mask?.cols ?? oldCols);
      item.mask = item.mask || { rows: grid, cols: grid, cells: [] };
      item.mask.cells = remapCells(item.mask.cells || [], currentRows, currentCols, grid, grid);
      item.mask.rows = grid;
      item.mask.cols = grid;
    });
  }

  function remapCells(cells, fromRows, fromCols, toRows, toCols) {
    const seen = new Set();
    const out = [];
    cells.forEach((c) => {
      if (!Array.isArray(c) || c.length !== 2) return;
      const r = toInt(c[0], -1);
      const cl = toInt(c[1], -1);
      if (r < 0 || cl < 0 || r >= fromRows || cl >= fromCols) return;
      const y = (r + 0.5) / fromRows;
      const x = (cl + 0.5) / fromCols;
      const nr = clamp(Math.floor(y * toRows), 0, toRows - 1);
      const nc = clamp(Math.floor(x * toCols), 0, toCols - 1);
      const key = `${nr}:${nc}`;
      if (seen.has(key)) return;
      seen.add(key);
      out.push([nr, nc]);
    });
    return out;
  }

  function syncField(ctx) {
    if (!ctx || !ctx.hiddenField) return;
    ctx.hiddenField.value = buildSerializablePayload(ctx);
    try {
      ctx.hiddenField.dispatchEvent(new Event("change", { bubbles: true }));
      ctx.hiddenField.dispatchEvent(new Event("input", { bubbles: true }));
    } catch (_) {}
  }

  function ensureMask(item, grid) {
    if (!item.mask) {
      item.mask = { rows: grid, cols: grid, cells: [] };
    }
    item.mask.rows = sanitizeGrid(item.mask.rows ?? grid);
    item.mask.cols = sanitizeGrid(item.mask.cols ?? grid);
    if (!Array.isArray(item.mask.cells)) item.mask.cells = [];
  }

  function findNearestPolygonPoint(item, point) {
    if (!item || !Array.isArray(item.polygon) || !item.polygon.length) return -1;
    const pCanvas = pixelToCanvas(point);
    if (!pCanvas) return -1;
    let nearest = -1;
    let best = Number.POSITIVE_INFINITY;
    item.polygon.forEach((p, idx) => {
      const c = pixelToCanvas(p);
      if (!c) return;
      const dx = c[0] - pCanvas[0];
      const dy = c[1] - pCanvas[1];
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < best) {
        best = d;
        nearest = idx;
      }
    });
    return best <= POLYGON_CLOSE_RADIUS_PX ? nearest : -1;
  }

  function pointInRoi(point, roi) {
    if (!point || !roi) return false;
    const box = reorderRoi(roi);
    return point[0] >= box[0][0] && point[0] <= box[1][0] && point[1] >= box[0][1] && point[1] <= box[1][1];
  }

  function getRoiResizeHandle(point, roi) {
    if (!point || !roi) return -1;
    const box = reorderRoi(roi);
    const corners = [
      [box[0][0], box[0][1]], // top-left
      [box[1][0], box[0][1]], // top-right
      [box[1][0], box[1][1]], // bottom-right
      [box[0][0], box[1][1]], // bottom-left
    ];
    const pCanvas = pixelToCanvas(point);
    if (!pCanvas) return -1;
    for (let i = 0; i < corners.length; i += 1) {
      const c = pixelToCanvas(corners[i]);
      if (!c) continue;
      const dx = c[0] - pCanvas[0];
      const dy = c[1] - pCanvas[1];
      if (Math.sqrt(dx * dx + dy * dy) <= BOX_HANDLE_RADIUS_PX) {
        return i;
      }
    }
    return -1;
  }

  function resizeRoiByHandle(roi, handle, point) {
    if (!roi || !point || handle < 0 || handle > 3) return roi;
    const m = getImageMetrics();
    if (!m) return roi;
    const box = reorderRoi(roi);
    const px = clamp(point[0], 0, m.naturalWidth);
    const py = clamp(point[1], 0, m.naturalHeight);
    let anchor = [box[1][0], box[1][1]];
    if (handle === 1) anchor = [box[0][0], box[1][1]];
    if (handle === 2) anchor = [box[0][0], box[0][1]];
    if (handle === 3) anchor = [box[1][0], box[0][1]];
    return reorderRoi([[px, py], anchor]);
  }

  function findBoxHit(ctx, point) {
    if (!ctx || !point) return null;
    const selectedIds = new Set(getSelectedFeatureIds(ctx));
    const items = (ctx.payload.items || []).filter((it) => (
      it && it.roi && !it._hidden && selectedIds.has(it.feature_id)
    ));
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const item = items[i];
      const handle = getRoiResizeHandle(point, item.roi);
      if (handle >= 0) return { item, handle };
      if (pointInRoi(point, item.roi)) return { item, handle: -1 };
    }
    return null;
  }

  function selectItemInUi(ctx, item) {
    if (!ctx || !item) return;
    state.activeFeatureId = item.feature_id;
    ctx.activeAnnotationByFeature[item.feature_id] = item._annId;
    if (ctx.featureSelectEl) {
      ctx.featureSelectEl.value = String(item.feature_id);
    }
    updateFeatureColorChip(ctx, item.feature_id);
    updateAnnotationOptions(ctx);
    setSelectedBox(ctx, item);
  }

  function cellForPoint(item, point) {
    if (!item || !item.roi || !pointInRoi(point, item.roi)) return null;
    const roi = reorderRoi(item.roi);
    const rows = sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(item.mask?.cols ?? DEFAULT_GRID);
    const roiW = Math.max(1e-6, roi[1][0] - roi[0][0]);
    const roiH = Math.max(1e-6, roi[1][1] - roi[0][1]);
    const relX = (point[0] - roi[0][0]) / roiW;
    const relY = (point[1] - roi[0][1]) / roiH;
    const c = clamp(Math.floor(relX * cols), 0, cols - 1);
    const r = clamp(Math.floor(relY * rows), 0, rows - 1);
    return [r, c];
  }

  function setCell(item, cell, add) {
    if (!item || !cell) return;
    ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
    const key = `${cell[0]}:${cell[1]}`;
    const found = item.mask.cells.findIndex((c) => `${c[0]}:${c[1]}` === key);
    if (add && found < 0) item.mask.cells.push([cell[0], cell[1]]);
    if (!add && found >= 0) item.mask.cells.splice(found, 1);
  }

  function polygonFromEllipse(roi) {
    const box = reorderRoi(roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const rx = Math.max(1, (box[1][0] - box[0][0]) / 2);
    const ry = Math.max(1, (box[1][1] - box[0][1]) / 2);
    const pts = [];
    for (let i = 0; i < ELLIPSE_SEGMENTS; i += 1) {
      const t = (Math.PI * 2 * i) / ELLIPSE_SEGMENTS;
      pts.push([cx + rx * Math.cos(t), cy + ry * Math.sin(t)]);
    }
    return pts;
  }

  function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i][0];
      const yi = polygon[i][1];
      const xj = polygon[j][0];
      const yj = polygon[j][1];
      const intersect = ((yi > point[1]) !== (yj > point[1]))
        && (point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi + 1e-12) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function refillMaskFromPolygon(item) {
    if (!item || !item.roi || !Array.isArray(item.polygon) || item.polygon.length < 3) return;
    ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
    const rows = item.mask.rows;
    const cols = item.mask.cols;
    const roi = reorderRoi(item.roi);
    const cells = [];
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const x = roi[0][0] + ((c + 0.5) / cols) * (roi[1][0] - roi[0][0]);
        const y = roi[0][1] + ((r + 0.5) / rows) * (roi[1][1] - roi[0][1]);
        if (pointInPolygon([x, y], item.polygon)) {
          cells.push([r, c]);
        }
      }
    }
    item.mask.cells = cells;
  }

  function enforceGeometryType(item, nextType) {
    if (!item) return;
    const current = item._geometryType || null;
    if (current === nextType) return;
    item._geometryType = nextType;
    if (nextType === "region") {
      item.polygon = [];
    } else if (nextType === "polygon" || nextType === "ellipse") {
      item.mask = item.mask || { rows: DEFAULT_GRID, cols: DEFAULT_GRID, cells: [] };
      item.mask.cells = [];
    }
  }

  function itemBounds(item) {
    const pts = [];
    if (item?.roi) {
      pts.push(item.roi[0], item.roi[1]);
    }
    if (Array.isArray(item?.polygon)) {
      item.polygon.forEach((p) => pts.push(p));
    }
    if (!pts.length) return null;
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;
    pts.forEach((p) => {
      minX = Math.min(minX, p[0]);
      minY = Math.min(minY, p[1]);
      maxX = Math.max(maxX, p[0]);
      maxY = Math.max(maxY, p[1]);
    });
    return { minX, minY, maxX, maxY };
  }

  function moveItemByDelta(item, dx, dy) {
    const m = getImageMetrics();
    if (!m || !item) return;
    const b = itemBounds(item);
    if (!b) return;
    const adjustedDx = clamp(dx, -b.minX, m.naturalWidth - b.maxX);
    const adjustedDy = clamp(dy, -b.minY, m.naturalHeight - b.maxY);
    if (item.roi) {
      item.roi = [
        [item.roi[0][0] + adjustedDx, item.roi[0][1] + adjustedDy],
        [item.roi[1][0] + adjustedDx, item.roi[1][1] + adjustedDy],
      ];
    }
    if (Array.isArray(item.polygon) && item.polygon.length) {
      item.polygon = item.polygon.map((p) => [p[0] + adjustedDx, p[1] + adjustedDy]);
    }
  }

  function handlePointerDown(event) {
    const ctx = activeContext();
    if (!ctx || state.activeFeatureId == null) return;
    const mode = effectiveMode();

    const point = clientToPixel(event.clientX, event.clientY);
    if (!point) return;

    let item = getActiveAnnotationItem(ctx, mode !== MODES.MOVE);
    const grid = sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID);
    if (item) ensureMask(item, grid);

    const hit = findBoxHit(ctx, point);
    if (hit) {
      item = hit.item;
      selectItemInUi(ctx, item);
      setPanLock(true);
      if (hit.handle >= 0) {
        state.drawing = { kind: "resize", handle: hit.handle, itemAnnId: item._annId };
      } else {
        state.drawing = { kind: "move", start: point, last: point, itemAnnId: item._annId };
      }
      event.preventDefault();
      event.stopPropagation();
      redraw();
      return;
    }

    if (mode === MODES.PAN) return;

    if (mode === MODES.MOVE) {
      clearSelectedBox();
      redraw();
      return;
    }

    if (mode === MODES.ROI) {
      setSelectedBox(ctx, item);
      setPanLock(true);
      state.drawing = { kind: "roi", start: point, current: point };
      item.roi = [point, point];
      item.mask.rows = grid;
      item.mask.cols = grid;
      item.mask.cells = [];
      item.polygon = [];
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (mode === MODES.ELLIPSE) {
      enforceGeometryType(item, "ellipse");
      state.drawing = { kind: "ellipse", start: point, current: point };
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (mode === MODES.POLYGON) {
      enforceGeometryType(item, "polygon");
      if (item.polygon.length) {
        const nearest = findNearestPolygonPoint(item, point);
        if (nearest >= 0) {
          state.pointDrag = { index: nearest };
          event.preventDefault();
          event.stopPropagation();
          return;
        }
      }

      if (item.roi && !pointInRoi(point, item.roi)) {
        setStatus(ctx, "Polygon points must stay inside ROI.");
        return;
      }

      if (!item.roi) {
        setStatus(ctx, "Draw ROI first (U), or use Ellipse (J).");
        return;
      }

      if (item.polygon.length >= 3) {
        const first = item.polygon[0];
        const p1 = pixelToCanvas(first);
        const p2 = pixelToCanvas(point);
        if (p1 && p2) {
          const dx = p1[0] - p2[0];
          const dy = p1[1] - p2[1];
          if (Math.sqrt(dx * dx + dy * dy) <= POLYGON_CLOSE_RADIUS_PX) {
            refillMaskFromPolygon(item);
            syncField(ctx);
            redraw();
            setStatus(ctx, "Polygon complete.");
            event.preventDefault();
            event.stopPropagation();
            return;
          }
        }
      }

      item.polygon.push(point);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (mode === MODES.ADD || mode === MODES.SUBTRACT) {
      enforceGeometryType(item, "region");
      if (!item.roi) {
        setStatus(ctx, "Draw ROI first.");
        return;
      }
      const add = mode === MODES.ADD;
      const cell = cellForPoint(item, point);
      if (!cell) return;
      setCell(item, cell, add);
      state.painting = { add, last: `${cell[0]}:${cell[1]}` };
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function handlePointerMove(event) {
    const ctx = activeContext();
    if (!ctx || state.activeFeatureId == null) return;
    const drawingItem = state.drawing?.itemAnnId != null
      ? (ctx.payload.items || []).find((it) => it._annId === state.drawing.itemAnnId) || null
      : null;
    const item = drawingItem || getActiveAnnotationItem(ctx, false);
    if (!item) return;
    const point = clientToPixel(event.clientX, event.clientY);
    if (!point) return;

    if (state.drawing && state.drawing.kind === "roi") {
      state.drawing.current = point;
      item.roi = reorderRoi([state.drawing.start, point]);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "move") {
      const dx = point[0] - state.drawing.last[0];
      const dy = point[1] - state.drawing.last[1];
      state.drawing.last = point;
      moveItemByDelta(item, dx, dy);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "resize") {
      item.roi = resizeRoiByHandle(item.roi, state.drawing.handle, point);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "ellipse") {
      state.drawing.current = point;
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.pointDrag) {
      if (item.roi && !pointInRoi(point, item.roi)) return;
      item.polygon[state.pointDrag.index] = point;
      refillMaskFromPolygon(item);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.painting) {
      const cell = cellForPoint(item, point);
      if (!cell) return;
      const key = `${cell[0]}:${cell[1]}`;
      if (key === state.painting.last) return;
      state.painting.last = key;
      setCell(item, cell, state.painting.add);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function handlePointerUp(event) {
    const ctx = activeContext();
    if (!ctx || state.activeFeatureId == null) return;
    const drawingItem = state.drawing?.itemAnnId != null
      ? (ctx.payload.items || []).find((it) => it._annId === state.drawing.itemAnnId) || null
      : null;
    const item = drawingItem || getActiveAnnotationItem(ctx, false);
    if (!item) return;

    if (state.drawing && state.drawing.kind === "roi") {
      state.drawing = null;
      state.mode = MODES.MOVE;
      setCanvasPointerMode();
      refreshToolbarStates();
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "move") {
      state.drawing = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "resize") {
      state.drawing = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "ellipse") {
      const p = clientToPixel(event.clientX, event.clientY);
      const end = p || state.drawing.current;
      const roi = reorderRoi([state.drawing.start, end]);
      item.roi = roi;
      item.polygon = polygonFromEllipse(roi);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
      state.drawing = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.pointDrag) {
      state.pointDrag = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.painting) {
      state.painting = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function handleKeyDown(event) {
    const ctx = activeContext();
    if (!ctx) return;
    const tag = event.target?.tagName?.toLowerCase();
    if (["input", "textarea", "select"].includes(tag)) return;

    const key = (event.key || "").toLowerCase();
    if (!key) return;

    if (key === "q") {
      state.tempPan = true;
      setCanvasPointerMode();
      setStatus(ctx, "Temporary pan mode.");
      return;
    }

    if (key === "u") { state.mode = MODES.ROI; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "i") { state.mode = MODES.POLYGON; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "j") { state.mode = MODES.ELLIPSE; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "o") { state.mode = MODES.ADD; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "p") { state.mode = MODES.SUBTRACT; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }

    if (key === "escape") {
      state.drawing = null;
      state.pointDrag = null;
      state.painting = null;
      setStatus(ctx, "Current action cancelled.");
      redraw();
      event.preventDefault();
      return;
    }

    if (key === "enter" && state.activeFeatureId != null) {
      const item = getActiveAnnotationItem(ctx, false);
      if (item && item.polygon.length >= 3) {
        refillMaskFromPolygon(item);
        syncField(ctx);
        redraw();
        setStatus(ctx, "Polygon complete.");
        event.preventDefault();
      }
    }
  }

  function handleKeyUp(event) {
    const key = (event.key || "").toLowerCase();
    if (key === "q") {
      state.tempPan = false;
      setCanvasPointerMode();
    }
  }

  function autoFocusToItem(item) {
    const metrics = getImageMetrics();
    if (!metrics || !item) return;
    const target = item.roi ? reorderRoi(item.roi) : bboxFromPolygon(item.polygon || []);
    if (!target) return;

    const w = metrics.naturalWidth;
    const h = metrics.naturalHeight;

    let x1 = target[0][0];
    let y1 = target[0][1];
    let x2 = target[1][0];
    let y2 = target[1][1];

    const marginX = (x2 - x1) * AUTO_FOCUS_MARGIN;
    const marginY = (y2 - y1) * AUTO_FOCUS_MARGIN;

    x1 = clamp(x1 - marginX, 0, w);
    y1 = clamp(y1 - marginY, 0, h);
    x2 = clamp(x2 + marginX, 0, w);
    y2 = clamp(y2 + marginY, 0, h);

    const boxW = Math.max(1, x2 - x1);
    const boxH = Math.max(1, y2 - y1);

    const baseScale = Math.min(metrics.mainRect.width / w, metrics.mainRect.height / h);
    const neededScale = Math.min(metrics.mainRect.width / boxW, metrics.mainRect.height / boxH);
    const zoomPercent = clamp((neededScale / Math.max(baseScale, 1e-6)) * 100, 40, 500);

    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    const panX = ((w / 2 - cx) / w) * 100;
    const panY = ((h / 2 - cy) / h) * 100;

    const viewerState = state.viewerRoot?.__imggrState;
    if (viewerState && typeof viewerState.setZoomLevel === "function") {
      viewerState.setZoomLevel(zoomPercent);
      if (typeof viewerState.setPanPercent === "function") {
        viewerState.setPanPercent(panX, panY);
      }
    }

    redraw();
  }

  function bboxFromPolygon(points) {
    if (!Array.isArray(points) || !points.length) return null;
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;
    points.forEach((p) => {
      minX = Math.min(minX, p[0]);
      minY = Math.min(minY, p[1]);
      maxX = Math.max(maxX, p[0]);
      maxY = Math.max(maxY, p[1]);
    });
    return [[minX, minY], [maxX, maxY]];
  }

  function ensureCanvasSize() {
    if (!state.canvas || !state.main) return;
    const rect = state.main.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(rect.width * dpr));
    const h = Math.max(1, Math.round(rect.height * dpr));
    if (state.canvas.width !== w || state.canvas.height !== h) {
      state.canvas.width = w;
      state.canvas.height = h;
    }
    state.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function redraw() {
    if (state.rafId) return;
    state.rafId = window.requestAnimationFrame(() => {
      state.rafId = null;
      drawNow();
    });
  }

  function queueRefresh() {
    if (state.refreshQueued) return;
    state.refreshQueued = true;
    window.requestAnimationFrame(() => {
      state.refreshQueued = false;
      refreshContextsAndUi();
    });
  }

  function drawNow() {
    if (!state.ctx || !state.canvas) return;
    ensureCanvasSize();
    const rect = state.main.getBoundingClientRect();
    state.ctx.clearRect(0, 0, rect.width, rect.height);
    hideBoxActions();

    if (!state.overlayVisible) return;

    const activeCtx = activeContext();
    if (!activeCtx) return;

    const selectedIds = new Set(getSelectedFeatureIds(activeCtx));
    if (!selectedIds.size) return;
    const activeItem = getActiveAnnotationItem(activeCtx, false);
    const activeAnnId = activeItem ? activeItem._annId : null;

    (activeCtx.payload.items || []).forEach((item) => {
      if (!selectedIds.has(item.feature_id)) return;
      if (item._hidden) return;
      drawItem(
        item,
        activeAnnId != null && item._annId === activeAnnId,
        isSelectedBox(activeCtx, item),
      );
    });

    if (state.drawing && (state.drawing.kind === "roi" || state.drawing.kind === "ellipse")) {
      const roi = reorderRoi([state.drawing.start, state.drawing.current]);
      drawRoiOutline(roi, "#ffffff", true);
    }
    positionBoxActions();
  }

  function drawItem(item, active, selected) {
    const color = (window.FeatureGeometryColors && window.FeatureGeometryColors.colorForFeature)
      ? window.FeatureGeometryColors.colorForFeature(item.feature_id)
      : "#ff6b6b";

    if (item.roi) {
      drawRoiOutline(item.roi, color, active, selected);
      drawGrid(item.roi, item.mask?.rows ?? DEFAULT_GRID, item.mask?.cols ?? DEFAULT_GRID, color, active ? 0.28 : 0.16);
      drawCells(item.roi, item.mask, color, active ? 0.35 : 0.2);
    }

    if (Array.isArray(item.polygon) && item.polygon.length > 0) {
      drawPolygon(item.polygon, color, active);
    }
  }

  function drawRoiOutline(roi, color, active, selected = false) {
    const p1 = pixelToCanvas(roi[0]);
    const p2 = pixelToCanvas(roi[1]);
    if (!p1 || !p2) return;
    const x = Math.min(p1[0], p2[0]);
    const y = Math.min(p1[1], p2[1]);
    const w = Math.abs(p2[0] - p1[0]);
    const h = Math.abs(p2[1] - p1[1]);
    state.ctx.save();
    state.ctx.strokeStyle = color;
    state.ctx.lineWidth = active ? 2.5 : 1.5;
    state.ctx.setLineDash(active ? [] : [4, 3]);
    state.ctx.strokeRect(x, y, w, h);
    if (selected) {
      const size = 8;
      const half = size / 2;
      const corners = [
        [x, y],
        [x + w, y],
        [x + w, y + h],
        [x, y + h],
      ];
      state.ctx.setLineDash([]);
      state.ctx.lineWidth = 1.5;
      corners.forEach((c) => {
        state.ctx.fillStyle = "#f8fafc";
        state.ctx.strokeStyle = color;
        state.ctx.fillRect(c[0] - half, c[1] - half, size, size);
        state.ctx.strokeRect(c[0] - half, c[1] - half, size, size);
      });
    }
    state.ctx.restore();
  }

  function drawGrid(roi, rows, cols, color, alpha) {
    const box = reorderRoi(roi);
    const p1 = pixelToCanvas(box[0]);
    const p2 = pixelToCanvas(box[1]);
    if (!p1 || !p2) return;
    const x1 = Math.min(p1[0], p2[0]);
    const y1 = Math.min(p1[1], p2[1]);
    const x2 = Math.max(p1[0], p2[0]);
    const y2 = Math.max(p1[1], p2[1]);

    state.ctx.save();
    state.ctx.strokeStyle = color;
    state.ctx.globalAlpha = alpha;
    state.ctx.lineWidth = 1;

    for (let r = 1; r < rows; r += 1) {
      const y = y1 + (r / rows) * (y2 - y1);
      state.ctx.beginPath();
      state.ctx.moveTo(x1, y);
      state.ctx.lineTo(x2, y);
      state.ctx.stroke();
    }

    for (let c = 1; c < cols; c += 1) {
      const x = x1 + (c / cols) * (x2 - x1);
      state.ctx.beginPath();
      state.ctx.moveTo(x, y1);
      state.ctx.lineTo(x, y2);
      state.ctx.stroke();
    }

    state.ctx.restore();
  }

  function drawCells(roi, mask, color, alpha) {
    if (!mask || !Array.isArray(mask.cells)) return;
    const rows = sanitizeGrid(mask.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(mask.cols ?? DEFAULT_GRID);
    const box = reorderRoi(roi);
    const p1 = pixelToCanvas(box[0]);
    const p2 = pixelToCanvas(box[1]);
    if (!p1 || !p2) return;
    const x1 = Math.min(p1[0], p2[0]);
    const y1 = Math.min(p1[1], p2[1]);
    const x2 = Math.max(p1[0], p2[0]);
    const y2 = Math.max(p1[1], p2[1]);
    const cellW = (x2 - x1) / cols;
    const cellH = (y2 - y1) / rows;

    state.ctx.save();
    state.ctx.fillStyle = color;
    state.ctx.globalAlpha = alpha;
    mask.cells.forEach((cell) => {
      const r = toInt(cell[0], -1);
      const c = toInt(cell[1], -1);
      if (r < 0 || c < 0 || r >= rows || c >= cols) return;
      state.ctx.fillRect(x1 + c * cellW, y1 + r * cellH, cellW, cellH);
    });
    state.ctx.restore();
  }

  function drawPolygon(points, color, active) {
    if (!Array.isArray(points) || !points.length) return;
    const first = pixelToCanvas(points[0]);
    if (!first) return;

    state.ctx.save();
    state.ctx.strokeStyle = color;
    state.ctx.fillStyle = color;
    state.ctx.globalAlpha = active ? 0.95 : 0.75;
    state.ctx.lineWidth = active ? 2 : 1.5;

    state.ctx.beginPath();
    state.ctx.moveTo(first[0], first[1]);
    for (let i = 1; i < points.length; i += 1) {
      const p = pixelToCanvas(points[i]);
      if (!p) continue;
      state.ctx.lineTo(p[0], p[1]);
    }
    if (points.length >= 3) {
      state.ctx.closePath();
    }
    state.ctx.stroke();

    if (active) {
      points.forEach((pt) => {
        const p = pixelToCanvas(pt);
        if (!p) return;
        state.ctx.beginPath();
        state.ctx.arc(p[0], p[1], 3, 0, Math.PI * 2);
        state.ctx.fill();
      });
    }

    state.ctx.restore();
  }

  function wireContext(sectionEl, featuresContainerEl, hiddenField, key, initialPayloadRaw) {
    const initial = sanitizePayload(initialPayloadRaw, DEFAULT_GRID);
    let nextAnnotationId = 1;
    (initial.items || []).forEach((item) => {
      item._annId = nextAnnotationId;
      nextAnnotationId += 1;
    });
    const ctx = {
      key,
      sectionEl,
      featuresContainerEl,
      hiddenField,
      payload: initial,
      panelTopEl: null,
      panelBottomEl: null,
      featureSelectEl: null,
      annotationSelectEl: null,
      addAnnotationBtn: null,
      removeAnnotationBtn: null,
      colorChipEl: null,
      gridInputEl: null,
      gridLabelEl: null,
      statusEl: null,
      toggleOverlayBtn: null,
      activeAnnotationByFeature: {},
      nextAnnotationId,
    };

    ensurePanel(ctx);
    updateGridLabel(ctx);
    state.contexts.set(key, ctx);

    if (!hiddenField.value) {
      syncField(ctx);
    }
  }

  function discoverContexts() {
    state.contexts.clear();

    const form = document.querySelector('form[data-grading-form="true"]');
    if (!form) return;

    const linkedFields = form.querySelectorAll('input[type="hidden"][data-feature-geometry-field]');
    if (linkedFields.length) {
      linkedFields.forEach((hiddenField) => {
        const taskUuid = hiddenField.getAttribute("data-feature-geometry-field");
        if (!taskUuid) return;

        const panel = document.querySelector(`.linked-grading-panel[data-task-uuid="${taskUuid}"]`);
        const sectionEl = panel ? panel.querySelector("[data-features-section]") : null;
        const containerEl = panel ? panel.querySelector("[data-features-container]") : null;
        if (!sectionEl || !containerEl) return;

        const fromField = safeParse(hiddenField.value);
        const fromWindow = window.linkedGradingData?.[taskUuid]?.existingFeatureGeometry || null;
        wireContext(sectionEl, containerEl, hiddenField, `linked:${taskUuid}`, fromField || fromWindow);
      });
      return;
    }

    const sectionEl = document.getElementById("features-section");
    const containerEl = document.getElementById("features-container");
    const hiddenField = form.querySelector('input[type="hidden"][name="feature_geometry_json"]');
    if (!sectionEl || !containerEl || !hiddenField) return;

    const fromField = safeParse(hiddenField.value);
    const fromWindow = window.existingFeatureGeometry || null;
    const taskUuid = form.querySelector('input[name="task_uuid"]')?.value || window.taskId || "task";
    wireContext(sectionEl, containerEl, hiddenField, `single:${taskUuid}`, fromField || fromWindow);
  }

  function refreshContextsAndUi() {
    if (!state.contexts.size) return;

    pickActiveContext();
    const ctx = activeContext();
    if (!ctx) {
      redraw();
      return;
    }

    syncFeatureSelection(ctx);
    updatePanelFeatureOptions(ctx);
    updateGridLabel(ctx);
    refreshToolbarStates();
    setCanvasPointerMode();

    state.contexts.forEach((c) => {
      if (c.panelTopEl) c.panelTopEl.style.display = c.key === ctx.key ? "flex" : "none";
      if (c.panelBottomEl) c.panelBottomEl.style.display = c.key === ctx.key ? "flex" : "none";
    });

    redraw();
  }

  function createCanvasOverlay() {
    const viewerRoot = document.querySelector(".imggr-viewer-root");
    const main = viewerRoot?.querySelector(".imggr-main");
    const img = main?.querySelector(".imggr-main-img");
    if (!viewerRoot || !main || !img) return false;

    state.viewerRoot = viewerRoot;
    state.main = main;
    state.mainImg = img;

    const canvas = document.createElement("canvas");
    canvas.className = "fgx-overlay-canvas";
    canvas.setAttribute("aria-hidden", "true");
    main.appendChild(canvas);
    state.canvas = canvas;
    state.ctx = canvas.getContext("2d");
    ensureBoxActions();

    canvas.addEventListener("pointerdown", handlePointerDown);
    canvas.addEventListener("pointermove", handlePointerMove);
    canvas.addEventListener("pointerup", handlePointerUp);
    canvas.addEventListener("pointercancel", handlePointerUp);
    canvas.addEventListener("pointerleave", handlePointerUp);

    window.addEventListener("keydown", handleKeyDown, { capture: true });
    window.addEventListener("keyup", handleKeyUp, { capture: true });
    window.addEventListener("resize", redraw);

    try {
      state.imageMutationObserver = new MutationObserver((records) => {
        if (Array.isArray(records) && records.some((r) => r.attributeName === "src")) {
          clearSelectedBox();
          state.drawing = null;
          state.pointDrag = null;
          state.painting = null;
          hideBoxActions();
        }
        redraw();
      });
      state.imageMutationObserver.observe(img, {
        attributes: true,
        attributeFilter: ["style", "class", "src"],
      });
    } catch (_) {}

    if (typeof ResizeObserver !== "undefined") {
      try {
        state.imageResizeObserver = new ResizeObserver(() => {
          redraw();
        });
        state.imageResizeObserver.observe(main);
        state.imageResizeObserver.observe(img);
      } catch (_) {}
    }

    return true;
  }

  function setupObservers() {
    if (state.observersReady) return;

    document.addEventListener("change", (event) => {
      const t = event.target;
      if (!t) return;
      if (t.matches('input[type="checkbox"][name^="selected_features"]')) {
        const ctx = activeContext();
        if (ctx) {
          const selected = new Set(getSelectedFeatureIds(ctx));
          ctx.payload.items = (ctx.payload.items || []).filter((it) => selected.has(it.feature_id));
          syncField(ctx);
        }
        queueRefresh();
        return;
      }
      if (t.matches('input[type="radio"][name="label_id"], input[type="radio"][name^="label_id_"]')) {
        window.setTimeout(queueRefresh, 0);
      }
    });

    document.addEventListener("click", (event) => {
      if (event.target?.matches("[data-clear-selection], #clear-impression")) {
        const ctx = activeContext();
        if (ctx) {
          ctx.payload.items = [];
          syncField(ctx);
        }
        window.setTimeout(queueRefresh, 0);
      }
    });

    const carousel = document.getElementById("linked-grading-carousel");
    if (carousel) {
      carousel.addEventListener("slid.bs.carousel", () => {
        queueRefresh();
      });
    }

    state.featuresObservers.forEach((obs) => {
      try { obs.disconnect(); } catch (_) {}
    });
    state.featuresObservers = [];
    state.contexts.forEach((ctx) => {
      if (!ctx.featuresContainerEl && !ctx.sectionEl) return;
      try {
        const obs = new MutationObserver(() => {
          queueRefresh();
        });
        if (ctx.featuresContainerEl) {
          obs.observe(ctx.featuresContainerEl, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["checked", "value", "disabled", "style", "class"],
          });
        }
        if (ctx.sectionEl) {
          obs.observe(ctx.sectionEl, {
            attributes: true,
            attributeFilter: ["style", "class"],
          });
        }
        state.featuresObservers.push(obs);
      } catch (_) {}
    });

    state.observersReady = true;
  }

  function init() {
    ensureStyle();
    if (!createCanvasOverlay()) return;
    discoverContexts();
    if (!state.contexts.size) return;
    setupObservers();
    queueRefresh();
    redraw();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
