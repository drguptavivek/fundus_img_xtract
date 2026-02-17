(function () {
  const MODES = {
    ROI: "roi",
    PYRAMID: "pyramid",
    POLYGON: "polygon",
    ELLIPSE: "ellipse",
    ADD: "add",
    SUBTRACT: "subtract",
    MOVE: "move",
    PAN: "pan",
  };

  const GRID_MIN = 3;
  const GRID_MAX = 256;
  const DEFAULT_GRID = 8;
  const AUTO_FOCUS_MARGIN = 0.15;
  const POLYGON_CLOSE_RADIUS_PX = 12;
  const ELLIPSE_SEGMENTS = 24;
  const BOX_HANDLE_RADIUS_PX = 10;
  const SHOW_GRID = false;
  const BRUSH_MASK_GRID = 192;
  const BRUSH_DIAMETER_MIN = 6;
  const BRUSH_DIAMETER_MAX = 200;
  const FILL_ALPHA_MIN_PCT = 5;
  const FILL_ALPHA_MAX_PCT = 100;

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
    mainPointerDown: false,
    hoverInfo: null,
    brushDiameterPx: 24,
    fillOpacity: 0.35,
    brushCursorPoint: null,
    pendingCreateType: null,
  };

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function toInt(v, fallback) {
    const n = Number(v);
    if (Number.isNaN(n)) return fallback;
    return Math.trunc(n);
  }

  function sanitizeBrushDiameter(value) {
    const n = toInt(value, 24);
    return clamp(n, BRUSH_DIAMETER_MIN, BRUSH_DIAMETER_MAX);
  }

  function setBrushDiameterPx(value) {
    state.brushDiameterPx = sanitizeBrushDiameter(value);
    state.contexts.forEach((c) => {
      if (c.brushDiameterEl) c.brushDiameterEl.value = String(state.brushDiameterPx);
      if (c.brushDiameterValueEl) c.brushDiameterValueEl.textContent = `${state.brushDiameterPx}px`;
    });
  }

  function sanitizeFillOpacityPct(value) {
    const n = toInt(value, 35);
    return clamp(n, FILL_ALPHA_MIN_PCT, FILL_ALPHA_MAX_PCT);
  }

  function setFillOpacityPct(value) {
    const pct = sanitizeFillOpacityPct(value);
    state.fillOpacity = pct / 100;
    state.contexts.forEach((c) => {
      if (c.fillOpacityEl) c.fillOpacityEl.value = String(pct);
      if (c.fillOpacityValueEl) c.fillOpacityValueEl.textContent = `${pct}%`;
    });
    redraw();
  }

  function clonePayload(payload) {
    return safeParse(JSON.stringify(payload || createEmptyPayload(DEFAULT_GRID))) || createEmptyPayload(DEFAULT_GRID);
  }

  function payloadSignature(payload) {
    try {
      return JSON.stringify(payload || {});
    } catch (_) {
      return "";
    }
  }

  function applyHistorySnapshot(ctx, snapshot) {
    if (!ctx || !snapshot) return;
    ctx._suspendHistory = true;
    ctx.payload = clonePayload(snapshot);
    const maxAnn = (ctx.payload.items || []).reduce((mx, it) => Math.max(mx, toInt(it?._annId, 0)), 0);
    ctx.nextAnnotationId = Math.max(1, maxAnn + 1);
    ctx._historyLastSnapshot = clonePayload(ctx.payload);
    ctx._historyLastSig = payloadSignature(ctx.payload);
    ctx._suspendHistory = false;
    clearSelectedBox();
    syncFeatureSelection(ctx);
    updatePanelFeatureOptions(ctx);
    updateAnnotationOptions(ctx);
    refreshAnnotationButtons(ctx);
    refreshFeatureDependentButtons(ctx);
    syncField(ctx);
    redraw();
  }

  function undoLastChange(ctx) {
    if (!ctx || !Array.isArray(ctx.undoStack) || !ctx.undoStack.length) return;
    const snapshot = ctx.undoStack.pop();
    applyHistorySnapshot(ctx, snapshot);
  }

  function armCreateMode(type, mode) {
    state.pendingCreateType = type;
    state.mode = mode;
    clearSelectedBox();
    setCanvasPointerMode();
    refreshToolbarStates();
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
      .fgx-overlay-canvas { position:absolute; left:0; top:0; z-index:15; cursor:crosshair; }
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
      .imggr-viewer-root.fgx-geometry-active .imggr-main-img { transition: none !important; }
      .imggr-loupe .fgx-loupe-overlay { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; border-radius:inherit; }
    `;
    document.head.appendChild(style);
  }

  function getImageMetrics() {
    if (!state.main || !state.mainImg) return null;
    const mainRect = state.main.getBoundingClientRect();
    const imgRect = state.mainImg.getBoundingClientRect();
    const canvasRect = state.canvas ? state.canvas.getBoundingClientRect() : imgRect;
    const naturalWidth = state.mainImg.naturalWidth || 0;
    const naturalHeight = state.mainImg.naturalHeight || 0;
    if (!mainRect.width || !mainRect.height || !imgRect.width || !imgRect.height || !naturalWidth || !naturalHeight) {
      return null;
    }
    // object-fit: contain can letterbox inside the <img> element box.
    // Use the real rendered image rect for all coordinate projections.
    const imgAspect = naturalWidth / naturalHeight;
    const boxAspect = imgRect.width / imgRect.height;
    let drawWidth = imgRect.width;
    let drawHeight = imgRect.height;
    let drawLeft = imgRect.left;
    let drawTop = imgRect.top;
    if (boxAspect > imgAspect) {
      drawHeight = imgRect.height;
      drawWidth = drawHeight * imgAspect;
      drawLeft = imgRect.left + ((imgRect.width - drawWidth) / 2);
    } else if (boxAspect < imgAspect) {
      drawWidth = imgRect.width;
      drawHeight = drawWidth / imgAspect;
      drawTop = imgRect.top + ((imgRect.height - drawHeight) / 2);
    }
    const drawRect = {
      left: drawLeft,
      top: drawTop,
      width: drawWidth,
      height: drawHeight,
    };
    return { mainRect, canvasRect, imgRect, drawRect, naturalWidth, naturalHeight };
  }

  function clientToPixel(clientX, clientY) {
    const m = getImageMetrics();
    if (!m) return null;
    const x = ((clientX - m.drawRect.left) / m.drawRect.width) * m.naturalWidth;
    const y = ((clientY - m.drawRect.top) / m.drawRect.height) * m.naturalHeight;
    return [clamp(x, 0, m.naturalWidth), clamp(y, 0, m.naturalHeight)];
  }

  function pixelToCanvas(point) {
    const m = getImageMetrics();
    if (!m || !point) return null;
    const x = (point[0] / m.naturalWidth) * m.drawRect.width;
    const y = (point[1] / m.naturalHeight) * m.drawRect.height;
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
        _geometryType: (() => {
          const gt = typeof item.geometry_type === "string" ? item.geometry_type.toLowerCase() : "";
          if (["box", "ellipse", "polygon", "pyramid", "region"].includes(gt)) return gt;
          return "box";
        })(),
        _locked: true,
        _ellipseRotation: (() => {
          const deg = Number(item?.ellipse?.rotation_deg);
          if (Number.isFinite(deg)) return (deg * Math.PI) / 180;
          return 0;
        })(),
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

  function isBoxItem(item) {
    return !item?._geometryType || item._geometryType === "box";
  }

  function isEllipseItem(item) {
    return item?._geometryType === "ellipse";
  }

  function clearBoxResidualGeometry(item) {
    if (!item || !isBoxItem(item)) return;
    item.polygon = [];
    if (item.mask && Array.isArray(item.mask.cells)) {
      item.mask.cells = [];
    }
  }

  function clampPointToImage(point) {
    const m = getImageMetrics();
    if (!m || !point) return point;
    return [
      clamp(point[0], 0, m.naturalWidth),
      clamp(point[1], 0, m.naturalHeight),
    ];
  }

  function clampRoiToImage(roi) {
    if (!roi) return roi;
    const p1 = clampPointToImage(roi[0]);
    const p2 = clampPointToImage(roi[1]);
    return reorderRoi([p1, p2]);
  }

  function clampPolygonToImage(points) {
    if (!Array.isArray(points)) return [];
    return points.map((p) => clampPointToImage(p));
  }

  function isCompleteItem(item) {
    if (!item || !item.roi) return false;
    return true;
  }

  function ensureRoiContainsPolygon(roi, polygon) {
    if (!roi) return roi;
    if (!Array.isArray(polygon) || polygon.length < 3) return clampRoiToImage(roi);
    const base = reorderRoi(clampRoiToImage(roi));
    const b = bboxFromPolygon(polygon);
    if (!b) return base;
    return clampRoiToImage([
      [Math.min(base[0][0], b[0][0]), Math.min(base[0][1], b[0][1])],
      [Math.max(base[1][0], b[1][0]), Math.max(base[1][1], b[1][1])],
    ]);
  }

  function buildSerializablePayload(ctx) {
    const selectedIds = new Set(getSelectedFeatureIds(ctx));
    const grid = sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID);

    const items = (ctx.payload.items || [])
      .filter((it) => selectedIds.has(it.feature_id) && isCompleteItem(it))
      .map((item) => {
        let roi = clampRoiToImage(item.roi);
        const ellipseRotation = Number.isFinite(item._ellipseRotation) ? item._ellipseRotation : 0;
        const polygonRaw = isBoxItem(item)
          ? [
              [roi[0][0], roi[0][1]],
              [roi[1][0], roi[0][1]],
              [roi[1][0], roi[1][1]],
              [roi[0][0], roi[1][1]],
            ]
          : (Array.isArray(item.polygon) && item.polygon.length >= 3
            ? item.polygon
            : [
                [roi[0][0], roi[0][1]],
                [roi[1][0], roi[0][1]],
                [roi[1][0], roi[1][1]],
              [roi[0][0], roi[1][1]],
            ]);
        const polygon = polygonRaw.map((p) => [Number(p[0]), Number(p[1])]);
        roi = ensureRoiContainsPolygon(roi, polygon);
        const rows = sanitizeGrid(item.mask.rows ?? grid);
        const cols = sanitizeGrid(item.mask.cols ?? grid);
        const cells = normalizeCells(item.mask.cells || [], rows, cols);
        return {
          feature_id: item.feature_id,
          feature_label: item.feature_label || getFeatureLabel(ctx, item.feature_id),
          geometry_type: item._geometryType || "box",
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
          ellipse: isEllipseItem(item)
            ? {
                rotation_deg: Number(((ellipseRotation * 180) / Math.PI).toFixed(3)),
              }
            : undefined,
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
      _ellipseRotation: 0,
      _locked: false,
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

  function clearHoverInfo() {
    state.hoverInfo = null;
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

  function getSelectedBoxItem(ctx) {
    if (!ctx || !state.selectedBoxRef) return null;
    if (state.selectedBoxRef.ctxKey !== ctx.key) return null;
    const annId = state.selectedBoxRef.annId;
    return (ctx.payload.items || []).find((it) => it && it._annId === annId) || null;
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
      <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-box-lock title="Lock ROI" aria-label="Lock ROI">
        <i class="fa-solid fa-lock"></i>
      </button>
      <button type="button" class="btn btn-outline-primary btn-sm" data-fgx-box-dup title="Duplicate" aria-label="Duplicate">
        <i class="fa-solid fa-copy"></i>
      </button>
      <button type="button" class="btn btn-outline-warning btn-sm" data-fgx-box-convert-poly title="Convert to polygon" aria-label="Convert to polygon">
        <i class="fa-solid fa-draw-polygon"></i>
      </button>
      <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-box-flip-h title="Flip pyramid horizontally" aria-label="Flip pyramid horizontally">
        <i class="fa-solid fa-left-right"></i>
      </button>
      <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-box-flip-v title="Flip pyramid vertically" aria-label="Flip pyramid vertically">
        <i class="fa-solid fa-up-down"></i>
      </button>
      <button type="button" class="btn btn-outline-danger btn-sm" data-fgx-box-del title="Delete" aria-label="Delete">
        <i class="fa-solid fa-trash"></i>
      </button>
    `;
    state.main.appendChild(wrap);
    state.boxActionsEl = wrap;

    wrap.querySelector("[data-fgx-box-lock]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item || !item.roi) return;
      setPanLock(false);
      ctx.activeAnnotationByFeature[item.feature_id] = item._annId;
      setSelectedBox(ctx, item);
      item._locked = !item._locked;
      if (item._locked && state.drawing && state.drawing.itemAnnId === item._annId) {
        state.drawing = null;
      }
      if (item._locked) {
        state.mode = MODES.MOVE;
        setCanvasPointerMode();
        refreshToolbarStates();
      } else if (!item._locked) {
        // Unlock implies editable: polygon should return to point edit mode.
        state.mode = item?._geometryType === "polygon" ? MODES.POLYGON : MODES.MOVE;
        setCanvasPointerMode();
        refreshToolbarStates();
      }
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-dup]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item || !item.roi || state.activeFeatureId == null) return;
      const src = reorderRoi(item.roi);
      const dx = Math.max(10, (src[1][0] - src[0][0]) * 0.08);
      const dy = Math.max(10, (src[1][1] - src[0][1]) * 0.08);
      const dup = createAnnotationItem(ctx, state.activeFeatureId);
      dup.roi = [
        [src[0][0] + dx, src[0][1] + dy],
        [src[1][0] + dx, src[1][1] + dy],
      ];
      dup._geometryType = item._geometryType || "box";
      dup._ellipseRotation = Number(item._ellipseRotation) || 0;
      if (isEllipseItem(dup)) {
        dup.polygon = polygonFromEllipse(dup.roi, dup._ellipseRotation);
        ensureMask(dup, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
        refillMaskFromPolygon(dup);
      } else if (!isBoxItem(dup) && Array.isArray(item.polygon) && item.polygon.length) {
        dup.polygon = item.polygon.map((p) => [p[0] + dx, p[1] + dy]);
        ensureMask(dup, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
        refillMaskFromPolygon(dup);
      }
      dup._locked = false;
      setSelectedBox(ctx, dup);
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      state.mode = MODES.MOVE;
      setCanvasPointerMode();
      refreshToolbarStates();
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-del]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item) return;
      if (!window.confirm("Delete selected box?")) return;
      removeAnnotationItem(ctx, item);
      clearSelectedBox();
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-convert-poly]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item || !item.roi) return;
      const prevType = item._geometryType || "box";
      const canConvert = prevType === "ellipse" || prevType === "box" || prevType === "pyramid";
      if (!canConvert) return;
      item._geometryType = "polygon";
      if (prevType === "ellipse") {
        item.polygon = polygonFromEllipse(item.roi, Number(item._ellipseRotation) || 0, 48);
      } else if (prevType === "pyramid" && Array.isArray(item.polygon) && item.polygon.length >= 3) {
        item.polygon = item.polygon.map((p) => [p[0], p[1]]);
      } else if (prevType === "pyramid") {
        item.polygon = polygonFromPyramid(item.roi);
      } else {
        item.polygon = polygonFromBox(item.roi);
      }
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
      state.mode = MODES.POLYGON;
      setCanvasPointerMode();
      refreshToolbarStates();
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-flip-h]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item || item._geometryType !== "pyramid" || item._locked !== false) return;
      if (!flipPolygonInRoi(item, "h")) return;
      syncField(ctx);
      redraw();
    });

    wrap.querySelector("[data-fgx-box-flip-v]")?.addEventListener("click", () => {
      const ctx = activeContext();
      const item = ctx ? (getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false)) : null;
      if (!ctx || !item || item._geometryType !== "pyramid" || item._locked !== false) return;
      if (!flipPolygonInRoi(item, "v")) return;
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
    const lockBtn = state.boxActionsEl.querySelector("[data-fgx-box-lock]");
    if (lockBtn) {
      const locked = item._locked !== false;
      lockBtn.classList.toggle("btn-outline-secondary", !locked);
      lockBtn.classList.toggle("btn-outline-success", locked);
      lockBtn.title = locked ? "Unlock ROI" : "Lock ROI";
      lockBtn.setAttribute("aria-label", locked ? "Unlock ROI" : "Lock ROI");
      lockBtn.innerHTML = locked
        ? '<i class="fa-solid fa-lock"></i>'
        : '<i class="fa-solid fa-lock-open"></i>';
    }
    const convertBtn = state.boxActionsEl.querySelector("[data-fgx-box-convert-poly]");
    if (convertBtn) {
      const show = isEllipseItem(item) || isBoxItem(item) || item._geometryType === "pyramid";
      convertBtn.style.display = show ? "inline-flex" : "none";
      convertBtn.disabled = !show;
    }
    const flipHBtn = state.boxActionsEl.querySelector("[data-fgx-box-flip-h]");
    const flipVBtn = state.boxActionsEl.querySelector("[data-fgx-box-flip-v]");
    const showFlip = item._geometryType === "pyramid";
    if (flipHBtn) {
      flipHBtn.style.display = showFlip ? "inline-flex" : "none";
      flipHBtn.disabled = !showFlip || item._locked !== false;
    }
    if (flipVBtn) {
      flipVBtn.style.display = showFlip ? "inline-flex" : "none";
      flipVBtn.disabled = !showFlip || item._locked !== false;
    }
    const roi = clampRoiToImage(item.roi);
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
    const m = getImageMetrics();
    if (!m) {
      state.boxActionsEl.style.display = "none";
      return;
    }
    const offsetX = m.drawRect.left - m.mainRect.left;
    const offsetY = m.drawRect.top - m.mainRect.top;
    state.boxActionsEl.style.left = `${x + offsetX}px`;
    state.boxActionsEl.style.top = `${y + offsetY}px`;
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
      state.activeFeatureId = null;
      ctx.featureSelectEl.disabled = true;
      ctx.annotationSelectEl.disabled = true;
      if (ctx.removeAnnotationBtn) ctx.removeAnnotationBtn.disabled = true;
      refreshFeatureDependentButtons(ctx);
      return;
    }

    ctx.featureSelectEl.disabled = false;
    const next = selected.includes(previous) ? previous : selected[0];
    state.activeFeatureId = next;
    ctx.featureSelectEl.value = String(next);
    updateFeatureColorChip(ctx, next);
    updateAnnotationOptions(ctx);
    refreshFeatureDependentButtons(ctx);
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

  function refreshFeatureDependentButtons(ctx) {
    if (!ctx || !ctx.panelTopEl) return;
    const hasFeature = state.activeFeatureId != null;
    ctx.panelTopEl.querySelectorAll("[data-fgx-add-box], [data-fgx-add-ellipse], [data-fgx-add-pyramid], [data-fgx-mode=\"add\"], [data-fgx-mode=\"subtract\"]").forEach((btn) => {
      btn.disabled = !hasFeature;
    });
    if (ctx.brushDiameterEl) ctx.brushDiameterEl.disabled = !hasFeature;
    if (ctx.fillOpacityEl) ctx.fillOpacityEl.disabled = !hasFeature;
    const undoBtn = ctx.panelTopEl.querySelector("[data-fgx-undo]");
    if (undoBtn) undoBtn.disabled = !ctx.undoStack?.length;
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

      <div class="fgx-group">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-mode="move" title="Pointer / Select">
          <i class="fa-solid fa-arrow-pointer"></i>
        </button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-add-box>+ Add Box</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-add-ellipse>+ Add Ellipse</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-add-pyramid>+ Add Pyramid</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-undo title="Undo last change">
          <i class="fa-solid fa-rotate-left"></i>
        </button>
      </div>

      <div class="fgx-group">
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-mode="add" title="Brush add">
          <i class="fa-solid fa-paintbrush"></i>
          <span class="ms-1">+</span>
        </button>
        <button type="button" class="btn btn-outline-secondary btn-sm" data-fgx-mode="subtract" title="Brush subtract">
          <i class="fa-solid fa-eraser"></i>
          <span class="ms-1">-</span>
        </button>
        <label class="fgx-block-label mb-0 ms-1" for="fgx-brush-diam-${ctx.key.replace(/[^a-zA-Z0-9_-]/g, "_")}">Diameter</label>
        <input
          id="fgx-brush-diam-${ctx.key.replace(/[^a-zA-Z0-9_-]/g, "_")}"
          type="range"
          class="form-range"
          data-fgx-brush-diameter
          min="${BRUSH_DIAMETER_MIN}"
          max="${BRUSH_DIAMETER_MAX}"
          step="2"
          value="${state.brushDiameterPx}"
          style="width:8rem;"
        />
        <span class="fgx-block-label mb-0" data-fgx-brush-diameter-value>${state.brushDiameterPx}px</span>
      </div>

      <div class="fgx-group">
        <label class="fgx-block-label mb-0" for="fgx-fill-alpha-${ctx.key.replace(/[^a-zA-Z0-9_-]/g, "_")}">Fill</label>
        <input
          id="fgx-fill-alpha-${ctx.key.replace(/[^a-zA-Z0-9_-]/g, "_")}"
          type="range"
          class="form-range"
          data-fgx-fill-opacity
          min="${FILL_ALPHA_MIN_PCT}"
          max="${FILL_ALPHA_MAX_PCT}"
          step="5"
          value="${Math.round(state.fillOpacity * 100)}"
          style="width:8rem;"
        />
        <span class="fgx-block-label mb-0" data-fgx-fill-opacity-value>${Math.round(state.fillOpacity * 100)}%</span>
      </div>
    `;
    sidebarHost.appendChild(panel);

    ctx.panelTopEl = panel;
    ctx.panelBottomEl = panel;
    ctx.featureSelectEl = panel.querySelector("[data-fgx-feature]");
    ctx.annotationSelectEl = panel.querySelector("[data-fgx-annotation]");
    ctx.addAnnotationBtn = null;
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
    ctx.brushDiameterEl = panel.querySelector("[data-fgx-brush-diameter]");
    ctx.brushDiameterValueEl = panel.querySelector("[data-fgx-brush-diameter-value]");
    ctx.fillOpacityEl = panel.querySelector("[data-fgx-fill-opacity]");
    ctx.fillOpacityValueEl = panel.querySelector("[data-fgx-fill-opacity-value]");

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
      refreshFeatureDependentButtons(ctx);
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
      setSelectedBox(ctx, item);
      state.mode = MODES.MOVE;
      setCanvasPointerMode();
      refreshToolbarStates();
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
      setPanLock(true);
      armCreateMode("box", MODES.ROI);
      redraw();
    });

    panel.querySelector("[data-fgx-add-ellipse]")?.addEventListener("click", () => {
      if (state.activeFeatureId == null) return;
      setPanLock(true);
      armCreateMode("ellipse", MODES.ELLIPSE);
      redraw();
    });

    panel.querySelector("[data-fgx-add-pyramid]")?.addEventListener("click", () => {
      if (state.activeFeatureId == null) return;
      setPanLock(true);
      armCreateMode("pyramid", MODES.PYRAMID);
      redraw();
    });

    panel.querySelector('[data-fgx-mode="add"]')?.addEventListener("click", () => {
      state.mode = MODES.ADD;
      setCanvasPointerMode();
      refreshToolbarStates();
    });

    panel.querySelector('[data-fgx-mode="subtract"]')?.addEventListener("click", () => {
      state.mode = MODES.SUBTRACT;
      setCanvasPointerMode();
      refreshToolbarStates();
    });

    panel.querySelector('[data-fgx-mode="move"]')?.addEventListener("click", () => {
      state.pendingCreateType = null;
      state.mode = MODES.MOVE;
      setCanvasPointerMode();
      refreshToolbarStates();
      redraw();
    });

    panel.querySelector("[data-fgx-undo]")?.addEventListener("click", () => {
      undoLastChange(ctx);
    });

    if (ctx.brushDiameterEl) {
      ctx.brushDiameterEl.value = String(state.brushDiameterPx);
      const onBrushDiameterChange = () => {
        state.brushDiameterPx = sanitizeBrushDiameter(ctx.brushDiameterEl.value);
        ctx.brushDiameterEl.value = String(state.brushDiameterPx);
        if (ctx.brushDiameterValueEl) ctx.brushDiameterValueEl.textContent = `${state.brushDiameterPx}px`;
      };
      ctx.brushDiameterEl.addEventListener("input", onBrushDiameterChange);
      ctx.brushDiameterEl.addEventListener("change", onBrushDiameterChange);
      if (ctx.brushDiameterValueEl) ctx.brushDiameterValueEl.textContent = `${state.brushDiameterPx}px`;
    }
    if (ctx.fillOpacityEl) {
      const onFillOpacityChange = () => {
        setFillOpacityPct(ctx.fillOpacityEl.value);
      };
      ctx.fillOpacityEl.addEventListener("input", onFillOpacityChange);
      ctx.fillOpacityEl.addEventListener("change", onFillOpacityChange);
      const pct = Math.round(state.fillOpacity * 100);
      ctx.fillOpacityEl.value = String(pct);
      if (ctx.fillOpacityValueEl) ctx.fillOpacityValueEl.textContent = `${pct}%`;
    }

    refreshAnnotationButtons(ctx);
    refreshFeatureDependentButtons(ctx);
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
    if (!ctx._suspendHistory) {
      const sig = payloadSignature(ctx.payload);
      if (ctx._historyLastSig == null) {
        ctx._historyLastSig = sig;
        ctx._historyLastSnapshot = clonePayload(ctx.payload);
      } else if (sig !== ctx._historyLastSig) {
        ctx.undoStack = Array.isArray(ctx.undoStack) ? ctx.undoStack : [];
        if (ctx._historyLastSnapshot) {
          ctx.undoStack.push(clonePayload(ctx._historyLastSnapshot));
          if (ctx.undoStack.length > 100) ctx.undoStack.shift();
        }
        ctx._historyLastSig = sig;
        ctx._historyLastSnapshot = clonePayload(ctx.payload);
      }
      refreshFeatureDependentButtons(ctx);
    }
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

  function remapPolygonBetweenRois(polygon, fromRoi, toRoi) {
    if (!Array.isArray(polygon) || !polygon.length || !fromRoi || !toRoi) return polygon || [];
    const src = reorderRoi(fromRoi);
    const dst = reorderRoi(toRoi);
    const srcW = Math.max(1e-6, src[1][0] - src[0][0]);
    const srcH = Math.max(1e-6, src[1][1] - src[0][1]);
    const dstW = Math.max(1e-6, dst[1][0] - dst[0][0]);
    const dstH = Math.max(1e-6, dst[1][1] - dst[0][1]);
    return polygon.map((p) => {
      const nx = (p[0] - src[0][0]) / srcW;
      const ny = (p[1] - src[0][1]) / srcH;
      return clampPointToImage([
        dst[0][0] + nx * dstW,
        dst[0][1] + ny * dstH,
      ]);
    });
  }

  function remapPolygonBetweenRotatedRois(polygon, fromRoi, toRoi, rotationRad = 0) {
    if (!Array.isArray(polygon) || !polygon.length || !fromRoi || !toRoi) return polygon || [];
    const src = reorderRoi(fromRoi);
    const dst = reorderRoi(toRoi);
    const srcCx = (src[0][0] + src[1][0]) / 2;
    const srcCy = (src[0][1] + src[1][1]) / 2;
    const dstCx = (dst[0][0] + dst[1][0]) / 2;
    const dstCy = (dst[0][1] + dst[1][1]) / 2;
    const srcRx = Math.max(1e-6, (src[1][0] - src[0][0]) / 2);
    const srcRy = Math.max(1e-6, (src[1][1] - src[0][1]) / 2);
    const dstRx = Math.max(1e-6, (dst[1][0] - dst[0][0]) / 2);
    const dstRy = Math.max(1e-6, (dst[1][1] - dst[0][1]) / 2);
    return polygon.map((p) => {
      const dx = p[0] - srcCx;
      const dy = p[1] - srcCy;
      const local = rotateOffset(dx, dy, -rotationRad);
      const nx = local[0] / srcRx;
      const ny = local[1] / srcRy;
      const dstLocal = [nx * dstRx, ny * dstRy];
      const world = rotateOffset(dstLocal[0], dstLocal[1], rotationRad);
      return clampPointToImage([dstCx + world[0], dstCy + world[1]]);
    });
  }

  function pointInRotatedRoi(point, roi, rotationRad = 0) {
    if (!point || !roi) return false;
    const box = reorderRoi(roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const rx = Math.max(1e-6, (box[1][0] - box[0][0]) / 2);
    const ry = Math.max(1e-6, (box[1][1] - box[0][1]) / 2);
    const local = rotateOffset(point[0] - cx, point[1] - cy, -rotationRad);
    return Math.abs(local[0]) <= rx && Math.abs(local[1]) <= ry;
  }

  function findBoxHit(ctx, point, preferredAnnId = null) {
    if (!ctx || !point) return null;
    const selectedIds = new Set(getSelectedFeatureIds(ctx));
    const items = (ctx.payload.items || []).filter((it) => (
      it && it.roi && it._geometryType !== "region" && !it._hidden && selectedIds.has(it.feature_id)
    ));
    if (preferredAnnId != null) {
      const preferred = items.find((it) => it._annId === preferredAnnId);
      if (preferred) {
        if (preferred._geometryType === "pyramid") {
          const pCanvas = pixelToCanvas(point);
          const rot = pyramidRotateHandleCanvasPoints(preferred);
          if (pCanvas && rot) {
            const dx = rot.handle[0] - pCanvas[0];
            const dy = rot.handle[1] - pCanvas[1];
            if (Math.sqrt(dx * dx + dy * dy) <= 12) return { item: preferred, action: "rotate-pyramid" };
          }
        }
        if (isEllipseItem(preferred)) {
          const pCanvas = pixelToCanvas(point);
          const rotH = ellipseRotateHandleCanvasPoint(preferred.roi, Number(preferred._ellipseRotation) || 0);
          if (pCanvas && rotH) {
            const dx = rotH[0] - pCanvas[0];
            const dy = rotH[1] - pCanvas[1];
            if (Math.sqrt(dx * dx + dy * dy) <= 12) return { item: preferred, action: "rotate" };
          }
        }
        const handle = (isEllipseItem(preferred) || preferred._geometryType === "pyramid")
          ? getEllipseResizeHandle(point, preferred)
          : getRoiResizeHandle(point, preferred.roi);
        if (handle >= 0) return { item: preferred, action: "resize", handle };
        if (preferred._geometryType === "pyramid") {
          if (pointInRotatedRoi(point, preferred.roi, pyramidGridRotation(preferred))) return { item: preferred, action: "move" };
        } else if (pointInRoi(point, preferred.roi)) {
          return { item: preferred, action: "move" };
        }
      }
    }
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const item = items[i];
      if (preferredAnnId != null && item._annId === preferredAnnId) continue;
      if (item._geometryType === "pyramid") {
        const pCanvas = pixelToCanvas(point);
        const rot = pyramidRotateHandleCanvasPoints(item);
        if (pCanvas && rot) {
          const dx = rot.handle[0] - pCanvas[0];
          const dy = rot.handle[1] - pCanvas[1];
          if (Math.sqrt(dx * dx + dy * dy) <= 12) return { item, action: "rotate-pyramid" };
        }
      }
      if (isEllipseItem(item)) {
        const pCanvas = pixelToCanvas(point);
        const rotH = ellipseRotateHandleCanvasPoint(item.roi, Number(item._ellipseRotation) || 0);
        if (pCanvas && rotH) {
          const dx = rotH[0] - pCanvas[0];
          const dy = rotH[1] - pCanvas[1];
          if (Math.sqrt(dx * dx + dy * dy) <= 12) return { item, action: "rotate" };
        }
      }
      const handle = (isEllipseItem(item) || item._geometryType === "pyramid")
        ? getEllipseResizeHandle(point, item)
        : getRoiResizeHandle(point, item.roi);
      if (handle >= 0) return { item, action: "resize", handle };
      if (item._geometryType === "pyramid") {
        if (pointInRotatedRoi(point, item.roi, pyramidGridRotation(item))) return { item, action: "move" };
      } else if (pointInRoi(point, item.roi)) {
        return { item, action: "move" };
      }
    }
    return null;
  }

  function buildHoverInfo(ctx, item) {
    if (!ctx || !item) return null;
    const anns = getItemsForFeature(ctx, item.feature_id);
    const idx = anns.findIndex((it) => it._annId === item._annId);
    const annSr = idx >= 0 ? idx + 1 : item._annId;
    const featureName = item.feature_label || getFeatureLabel(ctx, item.feature_id) || `Feature ${item.feature_id}`;
    return {
      ctxKey: ctx.key,
      annId: item._annId,
      text: `${featureName} • Ann ${annSr}`,
      roi: item.roi,
    };
  }

  function updateHoverInfoFromPoint(ctx, point) {
    if (!ctx || !point) {
      clearHoverInfo();
      return;
    }
    const preferredAnnId = getSelectedBoxItem(ctx)?._annId ?? null;
    const hit = findBoxHit(ctx, point, preferredAnnId);
    if (!hit) {
      clearHoverInfo();
      return;
    }
    const selected = getSelectedBoxItem(ctx);
    if (selected && selected._annId === hit.item?._annId) {
      clearHoverInfo();
      return;
    }
    state.hoverInfo = buildHoverInfo(ctx, hit.item);
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
    const roi = clampRoiToImage(item.roi);
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

  function ensureBrushAnnotationItem(ctx, item) {
    if (!ctx) return null;
    const m = getImageMetrics();
    if (!m) return item || null;
    let target = item;
    if (!target || target.feature_id !== state.activeFeatureId || target._geometryType !== "region") {
      target = createAnnotationItem(ctx, state.activeFeatureId);
      setSelectedBox(ctx, target);
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
    }
    target._geometryType = "region";
    target._locked = false;
    target.roi = [[0, 0], [m.naturalWidth, m.naturalHeight]];
    target.polygon = [];
    const prevRows = sanitizeGrid(target.mask?.rows ?? ctx.payload?.grid?.rows ?? DEFAULT_GRID);
    const prevCols = sanitizeGrid(target.mask?.cols ?? ctx.payload?.grid?.cols ?? DEFAULT_GRID);
    const fineGrid = clamp(BRUSH_MASK_GRID, GRID_MIN, 256);
    ensureMask(target, fineGrid);
    target.mask.cells = remapCells(target.mask.cells || [], prevRows, prevCols, fineGrid, fineGrid);
    target.mask.rows = fineGrid;
    target.mask.cols = fineGrid;
    return target;
  }

  function applyBrushCells(item, centerCell, add, centerPoint = null) {
    if (!item || !centerCell || !item.roi) return;
    ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
    const rows = sanitizeGrid(item.mask.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(item.mask.cols ?? DEFAULT_GRID);
    const roi = clampRoiToImage(item.roi);
    const roiW = Math.max(1e-6, roi[1][0] - roi[0][0]);
    const roiH = Math.max(1e-6, roi[1][1] - roi[0][1]);
    const cellW = roiW / cols;
    const cellH = roiH / rows;
    const radiusPx = sanitizeBrushDiameter(state.brushDiameterPx) / 2;
    const cellRadR = Math.max(1, Math.ceil(radiusPx / cellH));
    const cellRadC = Math.max(1, Math.ceil(radiusPx / cellW));
    const cx = centerPoint ? centerPoint[0] : (roi[0][0] + (centerCell[1] + 0.5) * cellW);
    const cy = centerPoint ? centerPoint[1] : (roi[0][1] + (centerCell[0] + 0.5) * cellH);
    for (let dr = -cellRadR; dr <= cellRadR; dr += 1) {
      for (let dc = -cellRadC; dc <= cellRadC; dc += 1) {
        const rr = centerCell[0] + dr;
        const cc = centerCell[1] + dc;
        if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) continue;
        const px = roi[0][0] + (cc + 0.5) * cellW;
        const py = roi[0][1] + (rr + 0.5) * cellH;
        const dx = px - cx;
        const dy = py - cy;
        if ((dx * dx + dy * dy) <= (radiusPx * radiusPx)) {
          setCell(item, [rr, cc], add);
        }
      }
    }
  }

  function isPenEraserEvent(event) {
    if (!event || event.pointerType !== "pen") return false;
    const button = toInt(event.button, -1);
    const buttons = toInt(event.buttons, 0);
    return button === 5 || (buttons & 32) === 32;
  }

  function resolveBrushAddMode(mode, event) {
    const baseAdd = mode === MODES.ADD;
    if (!baseAdd) return false;
    if (event?.altKey) return false; // Option/Alt temporarily switches add brush to eraser.
    if (isPenEraserEvent(event)) return false;
    return true;
  }

  function polygonFromEllipse(roi, rotationRad = 0, segments = ELLIPSE_SEGMENTS) {
    const box = reorderRoi(roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const rx = Math.max(1, (box[1][0] - box[0][0]) / 2);
    const ry = Math.max(1, (box[1][1] - box[0][1]) / 2);
    const cosR = Math.cos(rotationRad);
    const sinR = Math.sin(rotationRad);
    const safeSegments = Math.max(8, toInt(segments, ELLIPSE_SEGMENTS));
    const pts = [];
    for (let i = 0; i < safeSegments; i += 1) {
      const t = (Math.PI * 2 * i) / safeSegments;
      const ex = rx * Math.cos(t);
      const ey = ry * Math.sin(t);
      const x = cx + (ex * cosR - ey * sinR);
      const y = cy + (ex * sinR + ey * cosR);
      pts.push([x, y]);
    }
    return pts;
  }

  function polygonFromBox(roi) {
    const box = reorderRoi(roi);
    return [
      [box[0][0], box[0][1]],
      [box[1][0], box[0][1]],
      [box[1][0], box[1][1]],
      [box[0][0], box[1][1]],
    ];
  }

  function polygonFromPyramid(roi) {
    const box = reorderRoi(roi);
    const midX = (box[0][0] + box[1][0]) / 2;
    return [
      [midX, box[0][1]],
      [box[1][0], box[1][1]],
      [box[0][0], box[1][1]],
    ];
  }

  function rotatePointAround(point, center, angleRad) {
    const dx = point[0] - center[0];
    const dy = point[1] - center[1];
    const cosA = Math.cos(angleRad);
    const sinA = Math.sin(angleRad);
    return [
      center[0] + (dx * cosA - dy * sinA),
      center[1] + (dx * sinA + dy * cosA),
    ];
  }

  function rotateOffset(dx, dy, angleRad) {
    const cosA = Math.cos(angleRad);
    const sinA = Math.sin(angleRad);
    return [
      (dx * cosA - dy * sinA),
      (dx * sinA + dy * cosA),
    ];
  }

  function rotatePolygonAround(polygon, center, angleRad) {
    if (!Array.isArray(polygon) || !polygon.length) return polygon || [];
    return polygon.map((p) => clampPointToImage(rotatePointAround(p, center, angleRad)));
  }

  function polygonCentroid(points) {
    if (!Array.isArray(points) || !points.length) return null;
    let sx = 0;
    let sy = 0;
    points.forEach((p) => {
      sx += p[0];
      sy += p[1];
    });
    return [sx / points.length, sy / points.length];
  }

  function pyramidApexIndex(points) {
    if (!Array.isArray(points) || points.length < 3) return -1;
    // Pyramid polygons are created as [apex, baseRight, baseLeft] and preserve point order.
    return 0;
  }

  function pyramidRotateHandleCanvasPoints(item) {
    if (!item || item._geometryType !== "pyramid" || !Array.isArray(item.polygon) || item.polygon.length < 3) return null;
    const apexIdx = pyramidApexIndex(item.polygon);
    if (apexIdx < 0) return null;
    const centroidPx = polygonCentroid(item.polygon);
    if (!centroidPx) return null;
    const apexPx = item.polygon[apexIdx];
    const apex = pixelToCanvas(apexPx);
    const center = pixelToCanvas(centroidPx);
    if (!apex || !center) return null;
    const vx = apex[0] - center[0];
    const vy = apex[1] - center[1];
    const len = Math.hypot(vx, vy) || 1;
    const ux = vx / len;
    const uy = vy / len;
    return {
      apex,
      handle: [apex[0] + ux * 18, apex[1] + uy * 18],
    };
  }

  function pyramidGridRotation(item) {
    if (!item || !item.roi || !Array.isArray(item.polygon) || item.polygon.length < 3) return 0;
    const explicit = Number(item._ellipseRotation);
    if (Number.isFinite(explicit)) return explicit;
    const apexIdx = pyramidApexIndex(item.polygon);
    if (apexIdx < 0) return 0;
    const box = reorderRoi(item.roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const apex = item.polygon[apexIdx];
    const angle = Math.atan2(apex[1] - cy, apex[0] - cx);
    return angle + (Math.PI / 2);
  }

  function flipPolygonInRoi(item, axis) {
    if (!item || !item.roi || !Array.isArray(item.polygon) || item.polygon.length < 3) return false;
    const box = reorderRoi(item.roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    item.polygon = item.polygon.map((p) => {
      const x = axis === "h" ? (2 * cx - p[0]) : p[0];
      const y = axis === "v" ? (2 * cy - p[1]) : p[1];
      return clampPointToImage([x, y]);
    });
    refillMaskFromPolygon(item);
    return true;
  }

  function ellipseResizeHandlePixelPoints(roi, rotationRad = 0) {
    const box = reorderRoi(roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const rx = Math.max(1, (box[1][0] - box[0][0]) / 2);
    const ry = Math.max(1, (box[1][1] - box[0][1]) / 2);
    const cosR = Math.cos(rotationRad);
    const sinR = Math.sin(rotationRad);
    const localCorners = [
      [-rx, -ry],
      [rx, -ry],
      [rx, ry],
      [-rx, ry],
    ];
    return localCorners.map(([lx, ly]) => ([
      cx + (lx * cosR - ly * sinR),
      cy + (lx * sinR + ly * cosR),
    ]));
  }

  function ellipseRotateHandleCanvasPoint(roi, rotationRad = 0) {
    const box = reorderRoi(roi);
    const cxPx = (box[0][0] + box[1][0]) / 2;
    const cyPx = (box[0][1] + box[1][1]) / 2;
    const ry = Math.max(1, (box[1][1] - box[0][1]) / 2);
    const center = pixelToCanvas([cxPx, cyPx]);
    if (!center) return null;
    const ux = Math.sin(rotationRad);
    const uy = -Math.cos(rotationRad);
    const edge = pixelToCanvas([cxPx + ux * ry, cyPx + uy * ry]);
    if (!edge) return null;
    const edgeDx = edge[0] - center[0];
    const edgeDy = edge[1] - center[1];
    const edgeLen = Math.hypot(edgeDx, edgeDy) || 1;
    const nx = edgeDx / edgeLen;
    const ny = edgeDy / edgeLen;
    return [edge[0] + nx * 18, edge[1] + ny * 18];
  }

  function getEllipseResizeHandle(point, item) {
    if (!point || !item?.roi) return -1;
    const pCanvas = pixelToCanvas(point);
    if (!pCanvas) return -1;
    const corners = ellipseResizeHandlePixelPoints(item.roi, Number(item._ellipseRotation) || 0);
    for (let i = 0; i < corners.length; i += 1) {
      const c = pixelToCanvas(corners[i]);
      if (!c) continue;
      const dx = c[0] - pCanvas[0];
      const dy = c[1] - pCanvas[1];
      if (Math.sqrt(dx * dx + dy * dy) <= BOX_HANDLE_RADIUS_PX) return i;
    }
    return -1;
  }

  function resizeEllipseByHandle(item, handle, point) {
    if (!item?.roi || !point || handle < 0 || handle > 3) return item?.roi || null;
    const m = getImageMetrics();
    if (!m) return item.roi;
    const box = reorderRoi(item.roi);
    const cx = (box[0][0] + box[1][0]) / 2;
    const cy = (box[0][1] + box[1][1]) / 2;
    const rx = Math.max(1, (box[1][0] - box[0][0]) / 2);
    const ry = Math.max(1, (box[1][1] - box[0][1]) / 2);
    const rotation = Number(item._ellipseRotation) || 0;
    const cosR = Math.cos(rotation);
    const sinR = Math.sin(rotation);
    const invRotate = (x, y) => {
      const dx = x - cx;
      const dy = y - cy;
      return [dx * cosR + dy * sinR, -dx * sinR + dy * cosR];
    };
    const rotate = (lx, ly) => [cx + (lx * cosR - ly * sinR), cy + (lx * sinR + ly * cosR)];
    const clamped = [clamp(point[0], 0, m.naturalWidth), clamp(point[1], 0, m.naturalHeight)];
    const localPoint = invRotate(clamped[0], clamped[1]);
    const localCorners = [[-rx, -ry], [rx, -ry], [rx, ry], [-rx, ry]];
    const anchor = localCorners[(handle + 2) % 4];
    const nextCenterLocal = [(localPoint[0] + anchor[0]) / 2, (localPoint[1] + anchor[1]) / 2];
    const nextRx = Math.max(1, Math.abs(localPoint[0] - anchor[0]) / 2);
    const nextRy = Math.max(1, Math.abs(localPoint[1] - anchor[1]) / 2);
    const centerWorld = rotate(nextCenterLocal[0], nextCenterLocal[1]);
    return reorderRoi([
      [centerWorld[0] - nextRx, centerWorld[1] - nextRy],
      [centerWorld[0] + nextRx, centerWorld[1] + nextRy],
    ]);
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
    if (isEllipseItem(item)) {
      ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
      const rows = item.mask.rows;
      const cols = item.mask.cols;
      const cells = [];
      for (let r = 0; r < rows; r += 1) {
        for (let c = 0; c < cols; c += 1) {
          const nx = ((c + 0.5) / cols) * 2 - 1;
          const ny = ((r + 0.5) / rows) * 2 - 1;
          if ((nx * nx) + (ny * ny) <= 1) cells.push([r, c]);
        }
      }
      item.mask.cells = cells;
      return;
    }
    if (item._geometryType === "pyramid") {
      ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
      const rows = item.mask.rows;
      const cols = item.mask.cols;
      const roi = clampRoiToImage(item.roi);
      const cx = (roi[0][0] + roi[1][0]) / 2;
      const cy = (roi[0][1] + roi[1][1]) / 2;
      const rx = Math.max(1e-6, (roi[1][0] - roi[0][0]) / 2);
      const ry = Math.max(1e-6, (roi[1][1] - roi[0][1]) / 2);
      const rot = pyramidGridRotation(item);
      const cells = [];
      for (let r = 0; r < rows; r += 1) {
        for (let c = 0; c < cols; c += 1) {
          const lx = -rx + ((c + 0.5) / cols) * (2 * rx);
          const ly = -ry + ((r + 0.5) / rows) * (2 * ry);
          const off = rotateOffset(lx, ly, rot);
          const wx = cx + off[0];
          const wy = cy + off[1];
          if (pointInPolygon([wx, wy], item.polygon)) cells.push([r, c]);
        }
      }
      item.mask.cells = cells;
      return;
    }
    if (item._geometryType === "polygon") {
      const b = bboxFromPolygon(item.polygon);
      if (b) {
        item.roi = clampRoiToImage(b);
      }
    }
    ensureMask(item, sanitizeGrid(item.mask?.rows ?? DEFAULT_GRID));
    const rows = item.mask.rows;
    const cols = item.mask.cols;
    const roi = clampRoiToImage(item.roi);
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
    if (isBoxItem(item)) {
      clearBoxResidualGeometry(item);
      return;
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
    state.brushCursorPoint = (mode === MODES.ADD || mode === MODES.SUBTRACT) ? point : null;

    let item = getSelectedBoxItem(ctx) || getActiveAnnotationItem(ctx, false);
    const grid = sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID);
    if (item) ensureMask(item, grid);
    const pendingByMode = (
      (mode === MODES.ROI && state.pendingCreateType === "box")
      || (mode === MODES.ELLIPSE && state.pendingCreateType === "ellipse")
      || (mode === MODES.PYRAMID && state.pendingCreateType === "pyramid")
    );
    if (pendingByMode && state.activeFeatureId != null) {
      item = createAnnotationItem(ctx, state.activeFeatureId);
      item._geometryType = state.pendingCreateType;
      item._ellipseRotation = 0;
      ensureMask(item, grid);
      setSelectedBox(ctx, item);
      updateAnnotationOptions(ctx);
      refreshAnnotationButtons(ctx);
      state.pendingCreateType = null;
    }

    const hit = (mode === MODES.POLYGON || mode === MODES.ADD || mode === MODES.SUBTRACT)
      ? null
      : findBoxHit(ctx, point);
    if (hit) {
      item = hit.item;
      selectItemInUi(ctx, item);
      const locked = item._locked !== false;
      if (locked) {
        state.drawing = null;
        event.preventDefault();
        event.stopPropagation();
        redraw();
        return;
      }
      setPanLock(true);
      if (hit.action === "rotate-pyramid") {
        const box = reorderRoi(item.roi);
        const cx = (box[0][0] + box[1][0]) / 2;
        const cy = (box[0][1] + box[1][1]) / 2;
        const startAngle = Math.atan2(point[1] - cy, point[0] - cx);
        const initialRotation = pyramidGridRotation(item);
        state.drawing = {
          kind: "rotate-pyramid",
          itemAnnId: item._annId,
          center: [cx, cy],
          startAngle,
          initialRotation,
          initialPolygon: (item.polygon || []).map((p) => [p[0], p[1]]),
        };
      } else if (hit.action === "rotate") {
        const box = reorderRoi(item.roi);
        const cx = (box[0][0] + box[1][0]) / 2;
        const cy = (box[0][1] + box[1][1]) / 2;
        const startAngle = Math.atan2(point[1] - cy, point[0] - cx);
        state.drawing = {
          kind: "rotate",
          itemAnnId: item._annId,
          center: [cx, cy],
          startAngle,
          initialRotation: Number(item._ellipseRotation) || 0,
        };
      } else if (hit.action === "resize" && hit.handle >= 0) {
        state.drawing = { kind: "resize", handle: hit.handle, itemAnnId: item._annId };
      } else {
        state.drawing = { kind: "move", start: point, last: point, itemAnnId: item._annId };
      }
      event.preventDefault();
      event.stopPropagation();
      redraw();
      return;
    }

    if (mode === MODES.PAN) {
      state.pendingCreateType = null;
      clearSelectedBox();
      redraw();
      return;
    }

    if (mode === MODES.MOVE) {
      state.pendingCreateType = null;
      clearSelectedBox();
      redraw();
      return;
    }

    if (mode === MODES.ROI) {
      setSelectedBox(ctx, item);
      setPanLock(true);
      state.drawing = { kind: "roi", start: point, current: point };
      item.roi = [point, point];
      clearBoxResidualGeometry(item);
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

    if (mode === MODES.PYRAMID) {
      enforceGeometryType(item, "pyramid");
      setSelectedBox(ctx, item);
      setPanLock(true);
      state.drawing = { kind: "pyramid", start: point, current: point, itemAnnId: item._annId };
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

    if (mode === MODES.POLYGON) {
      enforceGeometryType(item, "polygon");
      if (item._locked !== false) {
        setSelectedBox(ctx, item);
        event.preventDefault();
        event.stopPropagation();
        redraw();
        return;
      }
      if (item.polygon.length) {
        const nearest = findNearestPolygonPoint(item, point);
        if (nearest >= 0) {
          state.pointDrag = { index: nearest };
          event.preventDefault();
          event.stopPropagation();
          return;
        }
      }

      if (item.polygon.length >= 3 && pointInPolygon(point, item.polygon)) {
        setSelectedBox(ctx, item);
        setPanLock(true);
        state.drawing = { kind: "move", start: point, last: point, itemAnnId: item._annId };
        event.preventDefault();
        event.stopPropagation();
        redraw();
        return;
      }

      if (item._geometryType !== "polygon" && item.roi && !pointInRoi(point, item.roi)) {
        setStatus(ctx, "Polygon points must stay inside ROI.");
        return;
      }

      if (item._geometryType !== "polygon" && !item.roi) {
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
      item = ensureBrushAnnotationItem(ctx, item);
      if (!item) return;
      const add = resolveBrushAddMode(mode, event);
      const cell = cellForPoint(item, point);
      if (!cell) return;
      applyBrushCells(item, cell, add, point);
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
    const mode = effectiveMode();
    const drawingItem = state.drawing?.itemAnnId != null
      ? (ctx.payload.items || []).find((it) => it._annId === state.drawing.itemAnnId) || null
      : null;
    const item = drawingItem || getActiveAnnotationItem(ctx, false);
    if (!item) return;
    const point = clientToPixel(event.clientX, event.clientY);
    if (!point) return;
    state.brushCursorPoint = (mode === MODES.ADD || mode === MODES.SUBTRACT) ? point : null;
    updateHoverInfoFromPoint(ctx, point);

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
      if (isEllipseItem(item)) {
        item.roi = resizeEllipseByHandle(item, state.drawing.handle, point);
        item.polygon = polygonFromEllipse(item.roi, Number(item._ellipseRotation) || 0);
        ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
        refillMaskFromPolygon(item);
      } else if (item._geometryType === "pyramid") {
        const prevRoi = item.roi ? reorderRoi(item.roi) : null;
        const rot = pyramidGridRotation(item);
        item._ellipseRotation = rot;
        const nextRoi = resizeEllipseByHandle(item, state.drawing.handle, point);
        item.roi = nextRoi;
        if (Array.isArray(item.polygon) && item.polygon.length >= 3 && prevRoi) {
          item.polygon = remapPolygonBetweenRotatedRois(item.polygon, prevRoi, nextRoi, rot);
          ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
          refillMaskFromPolygon(item);
        }
      } else {
        const prevRoi = item.roi ? reorderRoi(item.roi) : null;
        const nextRoi = resizeRoiByHandle(item.roi, state.drawing.handle, point);
        item.roi = nextRoi;
        if (item._geometryType === "pyramid" && Array.isArray(item.polygon) && item.polygon.length >= 3 && prevRoi) {
          item.polygon = remapPolygonBetweenRois(item.polygon, prevRoi, nextRoi);
          ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
          refillMaskFromPolygon(item);
        } else {
          clearBoxResidualGeometry(item);
        }
      }
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "rotate") {
      const cx = state.drawing.center[0];
      const cy = state.drawing.center[1];
      const angleNow = Math.atan2(point[1] - cy, point[0] - cx);
      const delta = angleNow - state.drawing.startAngle;
      item._ellipseRotation = state.drawing.initialRotation + delta;
      item.polygon = polygonFromEllipse(item.roi, item._ellipseRotation);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "rotate-pyramid") {
      const cx = state.drawing.center[0];
      const cy = state.drawing.center[1];
      const angleNow = Math.atan2(point[1] - cy, point[0] - cx);
      const delta = angleNow - state.drawing.startAngle;
      const base = Array.isArray(state.drawing.initialPolygon) ? state.drawing.initialPolygon : item.polygon;
      item._ellipseRotation = (Number(state.drawing.initialRotation) || 0) + delta;
      item.polygon = rotatePolygonAround(base, [cx, cy], delta);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
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

    if (state.drawing && state.drawing.kind === "pyramid") {
      state.drawing.current = point;
      item.roi = reorderRoi([state.drawing.start, point]);
      item.polygon = polygonFromPyramid(item.roi);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.pointDrag) {
      item.polygon[state.pointDrag.index] = clampPointToImage(point);
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
      applyBrushCells(item, cell, state.painting.add, point);
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
    }
  }

  function handlePointerUp(event) {
    const ctx = activeContext();
    if (!ctx || state.activeFeatureId == null) return;
    const mode = effectiveMode();
    const upPoint = clientToPixel(event.clientX, event.clientY);
    state.brushCursorPoint = (mode === MODES.ADD || mode === MODES.SUBTRACT) ? upPoint : null;
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

    if (state.drawing && state.drawing.kind === "rotate") {
      state.drawing = null;
      syncField(ctx);
      redraw();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (state.drawing && state.drawing.kind === "rotate-pyramid") {
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
      item._ellipseRotation = Number(item._ellipseRotation) || 0;
      item.polygon = polygonFromEllipse(roi, item._ellipseRotation);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
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

    if (state.drawing && state.drawing.kind === "pyramid") {
      const p = clientToPixel(event.clientX, event.clientY);
      const end = p || state.drawing.current;
      const roi = reorderRoi([state.drawing.start, end]);
      item.roi = roi;
      item.polygon = polygonFromPyramid(roi);
      ensureMask(item, sanitizeGrid(ctx.payload?.grid?.rows ?? DEFAULT_GRID));
      refillMaskFromPolygon(item);
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

  function handleMainClickForSelection(event) {
    if (effectiveMode() !== MODES.PAN) return;
    const ctx = activeContext();
    if (!ctx || state.activeFeatureId == null) return;
    const point = clientToPixel(event.clientX, event.clientY);
    if (!point) return;
    const hit = findBoxHit(ctx, point);
    if (!hit) {
      clearSelectedBox();
      redraw();
      return;
    }
    selectItemInUi(ctx, hit.item);
    setSelectedBox(ctx, hit.item);
    redraw();
    event.preventDefault();
    event.stopPropagation();
  }

  function handleMainPointerDown() {
    state.mainPointerDown = true;
  }

  function handleMainPointerUp() {
    state.mainPointerDown = false;
  }

  function handleMainPointerMoveForPanSync(event) {
    const ctx = activeContext();
    const point = clientToPixel(event.clientX, event.clientY);
    updateHoverInfoFromPoint(ctx, point);
    if (effectiveMode() !== MODES.PAN) {
      redraw();
      return;
    }
    if (!state.mainPointerDown) {
      redraw();
      return;
    }
    redraw();
  }

  function handleMainWheelForPanSync() {
    redraw();
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

    if ((key === "[" || key === "]") && (effectiveMode() === MODES.ADD || effectiveMode() === MODES.SUBTRACT)) {
      const step = event.shiftKey ? 8 : 4;
      const next = key === "]"
        ? (state.brushDiameterPx + step)
        : (state.brushDiameterPx - step);
      setBrushDiameterPx(next);
      setStatus(ctx, `Brush diameter: ${state.brushDiameterPx}px`);
      redraw();
      event.preventDefault();
      return;
    }

    if (key === "u") { state.mode = MODES.ROI; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "y") { state.mode = MODES.PYRAMID; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "i") { state.mode = MODES.POLYGON; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "j") { state.mode = MODES.ELLIPSE; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "o") { state.mode = MODES.ADD; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }
    if (key === "p") { state.mode = MODES.SUBTRACT; refreshToolbarStates(); setCanvasPointerMode(); event.preventDefault(); return; }

    if (key === "escape") {
      state.drawing = null;
      state.pointDrag = null;
      state.painting = null;
      state.pendingCreateType = null;
      setStatus(ctx, "Current action cancelled.");
      redraw();
      event.preventDefault();
      return;
    }

    if ((event.metaKey || event.ctrlKey) && !event.shiftKey && key === "z") {
      undoLastChange(ctx);
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
    if (!state.canvas || !state.main || !state.mainImg) return;
    const m = getImageMetrics();
    if (!m) return;
    const left = m.drawRect.left - m.mainRect.left;
    const top = m.drawRect.top - m.mainRect.top;
    const cssW = Math.max(1, m.drawRect.width);
    const cssH = Math.max(1, m.drawRect.height);
    state.canvas.style.left = `${left}px`;
    state.canvas.style.top = `${top}px`;
    state.canvas.style.width = `${cssW}px`;
    state.canvas.style.height = `${cssH}px`;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(cssW * dpr));
    const h = Math.max(1, Math.round(cssH * dpr));
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
    const canvasRect = state.canvas.getBoundingClientRect();
    state.ctx.clearRect(0, 0, canvasRect.width, canvasRect.height);
    hideBoxActions();
    clearLoupeOverlay();

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

    if (state.drawing && state.drawing.kind === "roi") {
      const roi = reorderRoi([state.drawing.start, state.drawing.current]);
      drawRoiOutline(roi, "#ffffff", true);
    }
    if (state.drawing && state.drawing.kind === "pyramid") {
      const roi = reorderRoi([state.drawing.start, state.drawing.current]);
      drawPolygon(polygonFromPyramid(roi), "#ffffff", true);
    }
    if (state.drawing && state.drawing.kind === "ellipse") {
      const roi = reorderRoi([state.drawing.start, state.drawing.current]);
      drawEllipseOutline(roi, "#ffffff", true, false, 0);
    }
    drawBrushCursor();
    drawHoverInfo(activeCtx);
    drawLoupeOverlay(activeCtx);
    positionBoxActions();
  }

  function drawBrushCursor() {
    const mode = effectiveMode();
    if (mode !== MODES.ADD && mode !== MODES.SUBTRACT) return;
    if (!state.brushCursorPoint) return;
    const c = pixelToCanvas(state.brushCursorPoint);
    if (!c) return;
    const m = getImageMetrics();
    if (!m || !m.naturalWidth) return;
    const radiusPx = sanitizeBrushDiameter(state.brushDiameterPx) / 2;
    const radiusCanvas = Math.max(2, radiusPx * (m.drawRect.width / m.naturalWidth));
    state.ctx.save();
    state.ctx.setLineDash([5, 5]);
    state.ctx.lineWidth = 1.5;
    state.ctx.strokeStyle = "rgba(248,250,252,0.95)";
    state.ctx.beginPath();
    state.ctx.arc(c[0], c[1], radiusCanvas, 0, Math.PI * 2);
    state.ctx.stroke();
    state.ctx.restore();
  }

  function getLoupeOverlayCanvas() {
    const loupe = state.viewerRoot?.querySelector(".imggr-loupe");
    if (!loupe) return null;
    let canvas = loupe.querySelector("canvas.fgx-loupe-overlay");
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.className = "fgx-loupe-overlay";
      loupe.appendChild(canvas);
    }
    return canvas;
  }

  function clearLoupeOverlay() {
    const canvas = getLoupeOverlayCanvas();
    if (!canvas) return;
    const ctx2 = canvas.getContext("2d");
    if (!ctx2) return;
    ctx2.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
  }

  function parsePxPair(raw) {
    if (!raw || typeof raw !== "string") return null;
    const parts = raw.trim().split(/\s+/);
    if (parts.length < 2) return null;
    const x = Number.parseFloat(parts[0]);
    const y = Number.parseFloat(parts[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x, y];
  }

  function parsePercentPair(raw) {
    if (!raw || typeof raw !== "string") return null;
    const parts = raw.trim().split(/\s+/);
    if (parts.length < 2) return null;
    const x = Number.parseFloat(parts[0].replace("%", ""));
    const y = Number.parseFloat(parts[1].replace("%", ""));
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x, y];
  }

  function parseNumericPair(raw) {
    if (!raw || typeof raw !== "string") return null;
    const parts = raw.trim().split(/\s+/);
    if (parts.length < 2) return null;
    const x = Number.parseFloat(parts[0]);
    const y = Number.parseFloat(parts[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x, y];
  }

  function drawLoupeOverlay(activeCtx) {
    const loupe = state.viewerRoot?.querySelector(".imggr-loupe");
    if (!loupe) return;
    const canvas = getLoupeOverlayCanvas();
    if (!canvas) return;
    const ctx2 = canvas.getContext("2d");
    if (!ctx2) return;

    const lw = Math.max(1, loupe.clientWidth);
    const lh = Math.max(1, loupe.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.max(1, Math.round(lw * dpr));
    const ch = Math.max(1, Math.round(lh * dpr));
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw;
      canvas.height = ch;
    }
    ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx2.clearRect(0, 0, lw, lh);

    if (!loupe.classList.contains("is-active")) return;
    if (!activeCtx) return;

    const m = getImageMetrics();
    if (!m || !m.drawRect.width || !m.drawRect.height) return;

    const selectedIds = new Set(getSelectedFeatureIds(activeCtx));
    if (!selectedIds.size) return;
    const activeItem = getActiveAnnotationItem(activeCtx, false);
    const activeAnnId = activeItem ? activeItem._annId : null;

    const dsZoom = Number.parseFloat(loupe.dataset.imgZoom || "");
    const dsX = Number.parseFloat(loupe.dataset.imgX || "");
    const dsY = Number.parseFloat(loupe.dataset.imgY || "");
    const dsW = Number.parseFloat(loupe.dataset.imgW || "");
    const dsH = Number.parseFloat(loupe.dataset.imgH || "");

    let zoom = Number.isFinite(dsZoom) ? dsZoom : 1;
    let centerX = Number.isFinite(dsX) ? dsX : (m.drawRect.width / 2);
    let centerY = Number.isFinite(dsY) ? dsY : (m.drawRect.height / 2);

    // Fallback when loupe mapping dataset is not available yet.
    if (!Number.isFinite(dsZoom) || !Number.isFinite(dsX) || !Number.isFinite(dsY)) {
      const bgSizeRaw = loupe.style.backgroundSize || window.getComputedStyle(loupe).backgroundSize;
      const bgPosRaw = loupe.style.backgroundPosition || window.getComputedStyle(loupe).backgroundPosition;
      const bgSize = parsePxPair(bgSizeRaw);
      const bgPosPct = parsePercentPair(bgPosRaw);
      const bgPosPx = parseNumericPair(bgPosRaw);
      if (bgSize && bgSize[0] > 0) zoom = bgSize[0] / m.drawRect.width;
      if (bgPosPct) {
        centerX = (bgPosPct[0] / 100) * (Number.isFinite(dsW) ? dsW : m.drawRect.width);
        centerY = (bgPosPct[1] / 100) * (Number.isFinite(dsH) ? dsH : m.drawRect.height);
      } else if (bgPosPx) {
        centerX = ((lw / 2) - bgPosPx[0]) / Math.max(zoom, 1e-6);
        centerY = ((lh / 2) - bgPosPx[1]) / Math.max(zoom, 1e-6);
      }
    }
    function project(point) {
      const c = pixelToCanvas(point);
      if (!c) return null;
      return [
        (lw / 2) + ((c[0] - centerX) * zoom),
        (lh / 2) + ((c[1] - centerY) * zoom),
      ];
    }

    (activeCtx.payload.items || []).forEach((item) => {
      if (!item || !item.roi || item._hidden) return;
      if (!selectedIds.has(item.feature_id)) return;
      const roi = clampRoiToImage(item.roi);
      const p1 = project(roi[0]);
      const p2 = project(roi[1]);
      if (!p1 || !p2) return;
      const x = Math.min(p1[0], p2[0]);
      const y = Math.min(p1[1], p2[1]);
      const w = Math.abs(p2[0] - p1[0]);
      const h = Math.abs(p2[1] - p1[1]);
      if (w < 1 || h < 1) return;
      const color = (window.FeatureGeometryColors && window.FeatureGeometryColors.colorForFeature)
        ? window.FeatureGeometryColors.colorForFeature(item.feature_id)
        : "#ff6b6b";
      const active = activeAnnId != null && activeAnnId === item._annId;
      ctx2.save();
      ctx2.strokeStyle = color;
      ctx2.lineWidth = active ? 2 : 1.5;
      ctx2.setLineDash(active ? [] : [4, 3]);
      ctx2.strokeRect(x, y, w, h);
      ctx2.restore();
    });
  }

  function drawHoverInfo(ctx) {
    if (!ctx || !state.hoverInfo) return;
    if (state.hoverInfo.ctxKey !== ctx.key) return;
    if (state.drawing) return;
    const selected = getSelectedBoxItem(ctx);
    if (selected && selected._annId === state.hoverInfo.annId) return;
    const roi = state.hoverInfo.roi ? clampRoiToImage(state.hoverInfo.roi) : null;
    if (!roi) return;
    const p1 = pixelToCanvas(roi[0]);
    const p2 = pixelToCanvas(roi[1]);
    if (!p1 || !p2) return;

    const text = state.hoverInfo.text || "";
    if (!text) return;
    const x = (Math.min(p1[0], p2[0]) + Math.max(p1[0], p2[0])) / 2;
    const y = Math.min(p1[1], p2[1]) - 10;

    state.ctx.save();
    state.ctx.font = "600 12px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
    const padX = 8;
    const textW = Math.ceil(state.ctx.measureText(text).width);
    const w = textW + padX * 2;
    const h = 22;
    const bx = x - w / 2;
    const by = y - h;

    state.ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
    state.ctx.strokeStyle = "rgba(148, 163, 184, 0.8)";
    state.ctx.lineWidth = 1;
    if (typeof state.ctx.roundRect === "function") {
      state.ctx.beginPath();
      state.ctx.roundRect(bx, by, w, h, 7);
      state.ctx.fill();
      state.ctx.stroke();
    } else {
      state.ctx.fillRect(bx, by, w, h);
      state.ctx.strokeRect(bx, by, w, h);
    }

    state.ctx.fillStyle = "#f8fafc";
    state.ctx.textBaseline = "middle";
    state.ctx.fillText(text, bx + padX, by + h / 2 + 0.5);
    state.ctx.restore();
  }

  function drawItem(item, active, selected) {
    const color = (window.FeatureGeometryColors && window.FeatureGeometryColors.colorForFeature)
      ? window.FeatureGeometryColors.colorForFeature(item.feature_id)
      : "#ff6b6b";
    const brushMode = effectiveMode() === MODES.ADD || effectiveMode() === MODES.SUBTRACT;
    const fillActiveAlpha = clamp(Number(state.fillOpacity) || 0.35, 0.05, 1);
    const fillInactiveAlpha = clamp(fillActiveAlpha * 0.57, 0.03, fillActiveAlpha);

    if (item.roi && isEllipseItem(item)) {
      const roi = clampRoiToImage(item.roi);
      const rotation = Number(item._ellipseRotation) || 0;
      drawEllipseGridAndCells(
        roi, item.mask, color, active ? 0.28 : 0.16, active ? fillActiveAlpha : fillInactiveAlpha, rotation, SHOW_GRID && !brushMode,
      );
      drawEllipseOutline(roi, color, active, selected, rotation);
      return;
    }

    if (item.roi) {
      const roi = clampRoiToImage(item.roi);
      const showRoiOutline = (isBoxItem(item) || selected) && item._geometryType !== "region";
      if (showRoiOutline) {
        if (item._geometryType === "pyramid") {
          drawRotatedRoiOutline(roi, color, active, selected, pyramidGridRotation(item));
        } else {
          drawRoiOutline(roi, color, active, selected);
        }
      }
      if (item._geometryType === "pyramid" && Array.isArray(item.polygon) && item.polygon.length >= 3) {
        drawPyramidGridAndCells(
          roi,
          clampPolygonToImage(item.polygon),
          item.mask,
          color,
          active ? 0.28 : 0.16,
          active ? fillActiveAlpha : fillInactiveAlpha,
          pyramidGridRotation(item),
          SHOW_GRID && !brushMode,
        );
      } else if (!isBoxItem(item) && Array.isArray(item.polygon) && item.polygon.length >= 3) {
        drawPolygonGridAndCells(
          roi,
          clampPolygonToImage(item.polygon),
          item.mask,
          color,
          active ? 0.28 : 0.16,
          active ? fillActiveAlpha : fillInactiveAlpha,
          SHOW_GRID && !brushMode,
        );
      } else {
        if (SHOW_GRID && !brushMode) {
          drawGrid(roi, item.mask?.rows ?? DEFAULT_GRID, item.mask?.cols ?? DEFAULT_GRID, color, active ? 0.28 : 0.16);
        }
        drawCells(roi, item.mask, color, active ? fillActiveAlpha : fillInactiveAlpha);
      }
    }

    if (!isBoxItem(item) && Array.isArray(item.polygon) && item.polygon.length > 0) {
      drawPolygon(clampPolygonToImage(item.polygon), color, active);
      if (selected && item._geometryType === "pyramid") {
        drawPyramidRotateHandle(item, color);
      }
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

  function drawRotatedRoiOutline(roi, color, active, selected = false, rotation = 0) {
    const corners = ellipseResizeHandlePixelPoints(roi, rotation);
    if (!corners.length) return;
    const first = pixelToCanvas(corners[0]);
    if (!first) return;

    state.ctx.save();
    state.ctx.strokeStyle = color;
    state.ctx.lineWidth = active ? 2.5 : 1.5;
    state.ctx.setLineDash(active ? [] : [4, 3]);
    state.ctx.beginPath();
    state.ctx.moveTo(first[0], first[1]);
    for (let i = 1; i < corners.length; i += 1) {
      const c = pixelToCanvas(corners[i]);
      if (!c) continue;
      state.ctx.lineTo(c[0], c[1]);
    }
    state.ctx.closePath();
    state.ctx.stroke();

    if (selected) {
      const size = 8;
      const half = size / 2;
      state.ctx.setLineDash([]);
      state.ctx.lineWidth = 1.5;
      corners.forEach((corner) => {
        const c = pixelToCanvas(corner);
        if (!c) return;
        state.ctx.fillStyle = "#f8fafc";
        state.ctx.strokeStyle = color;
        state.ctx.fillRect(c[0] - half, c[1] - half, size, size);
        state.ctx.strokeRect(c[0] - half, c[1] - half, size, size);
      });
    }
    state.ctx.restore();
  }

  function drawEllipseOutline(roi, color, active, selected = false, rotation = 0) {
    const p1 = pixelToCanvas(roi[0]);
    const p2 = pixelToCanvas(roi[1]);
    if (!p1 || !p2) return;
    const x = Math.min(p1[0], p2[0]);
    const y = Math.min(p1[1], p2[1]);
    const w = Math.abs(p2[0] - p1[0]);
    const h = Math.abs(p2[1] - p1[1]);
    const cx = x + w / 2;
    const cy = y + h / 2;
    const rx = Math.max(1, w / 2);
    const ry = Math.max(1, h / 2);

    state.ctx.save();
    state.ctx.strokeStyle = color;
    state.ctx.lineWidth = active ? 2.5 : 1.5;
    state.ctx.setLineDash(active ? [] : [4, 3]);
    state.ctx.beginPath();
    state.ctx.ellipse(cx, cy, rx, ry, rotation, 0, Math.PI * 2);
    state.ctx.stroke();

    if (selected) {
      const size = 8;
      const half = size / 2;
      const corners = ellipseResizeHandlePixelPoints(roi, rotation);
      state.ctx.setLineDash([]);
      state.ctx.lineWidth = 1.5;
      corners.forEach((corner) => {
        const c = pixelToCanvas(corner);
        if (!c) return;
        state.ctx.fillStyle = "#f8fafc";
        state.ctx.strokeStyle = color;
        state.ctx.fillRect(c[0] - half, c[1] - half, size, size);
        state.ctx.strokeRect(c[0] - half, c[1] - half, size, size);
      });

      const handle = ellipseRotateHandleCanvasPoint(roi, rotation);
      if (handle) {
        const topUx = Math.sin(rotation);
        const topUy = -Math.cos(rotation);
        const topPointPx = [
          ((roi[0][0] + roi[1][0]) / 2) + topUx * (Math.max(1, (Math.abs(roi[1][1] - roi[0][1]) / 2))),
          ((roi[0][1] + roi[1][1]) / 2) + topUy * (Math.max(1, (Math.abs(roi[1][1] - roi[0][1]) / 2))),
        ];
        const topPoint = pixelToCanvas(topPointPx);
        if (topPoint) {
          state.ctx.beginPath();
          state.ctx.moveTo(topPoint[0], topPoint[1]);
          state.ctx.lineTo(handle[0], handle[1]);
          state.ctx.stroke();
        }
        state.ctx.beginPath();
        state.ctx.fillStyle = "#f8fafc";
        state.ctx.arc(handle[0], handle[1], 5, 0, Math.PI * 2);
        state.ctx.fill();
        state.ctx.stroke();
      }
    }
    state.ctx.restore();
  }

  function drawPyramidRotateHandle(item, color) {
    const rot = pyramidRotateHandleCanvasPoints(item);
    if (!rot) return;
    state.ctx.save();
    state.ctx.setLineDash([]);
    state.ctx.lineWidth = 1.5;
    state.ctx.strokeStyle = color;
    state.ctx.beginPath();
    state.ctx.moveTo(rot.apex[0], rot.apex[1]);
    state.ctx.lineTo(rot.handle[0], rot.handle[1]);
    state.ctx.stroke();
    state.ctx.beginPath();
    state.ctx.fillStyle = "#f8fafc";
    state.ctx.arc(rot.handle[0], rot.handle[1], 5, 0, Math.PI * 2);
    state.ctx.fill();
    state.ctx.stroke();
    state.ctx.restore();
  }

  function drawEllipseGridAndCells(roi, mask, color, gridAlpha, cellAlpha, rotation = 0, showGrid = true) {
    const p1 = pixelToCanvas(roi[0]);
    const p2 = pixelToCanvas(roi[1]);
    if (!p1 || !p2) return;
    const x = Math.min(p1[0], p2[0]);
    const y = Math.min(p1[1], p2[1]);
    const w = Math.abs(p2[0] - p1[0]);
    const h = Math.abs(p2[1] - p1[1]);
    const rx = Math.max(1, w / 2);
    const ry = Math.max(1, h / 2);
    const cx = x + rx;
    const cy = y + ry;
    const rows = sanitizeGrid(mask?.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(mask?.cols ?? DEFAULT_GRID);

    state.ctx.save();
    state.ctx.translate(cx, cy);
    state.ctx.rotate(rotation);
    state.ctx.beginPath();
    state.ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
    state.ctx.clip();

    if (showGrid) {
      state.ctx.strokeStyle = color;
      state.ctx.globalAlpha = gridAlpha;
      state.ctx.lineWidth = 1;
      for (let r = 1; r < rows; r += 1) {
        const gy = -ry + (r / rows) * (2 * ry);
        state.ctx.beginPath();
        state.ctx.moveTo(-rx, gy);
        state.ctx.lineTo(rx, gy);
        state.ctx.stroke();
      }
      for (let c = 1; c < cols; c += 1) {
        const gx = -rx + (c / cols) * (2 * rx);
        state.ctx.beginPath();
        state.ctx.moveTo(gx, -ry);
        state.ctx.lineTo(gx, ry);
        state.ctx.stroke();
      }
    }

    if (mask && Array.isArray(mask.cells)) {
      const cellW = (2 * rx) / cols;
      const cellH = (2 * ry) / rows;
      state.ctx.fillStyle = color;
      state.ctx.globalAlpha = cellAlpha;
      mask.cells.forEach((cell) => {
        const rr = toInt(cell[0], -1);
        const cc = toInt(cell[1], -1);
        if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) return;
        state.ctx.fillRect(
          -rx + cc * cellW,
          -ry + rr * cellH,
          cellW,
          cellH,
        );
      });
    }

    state.ctx.restore();
  }

  function drawPolygonGridAndCells(roi, polygon, mask, color, gridAlpha, cellAlpha, showGrid = true) {
    if (!Array.isArray(polygon) || polygon.length < 3) {
      drawGrid(roi, mask?.rows ?? DEFAULT_GRID, mask?.cols ?? DEFAULT_GRID, color, gridAlpha);
      drawCells(roi, mask, color, cellAlpha);
      return;
    }
    const box = reorderRoi(roi);
    const p1 = pixelToCanvas(box[0]);
    const p2 = pixelToCanvas(box[1]);
    if (!p1 || !p2) return;
    const x1 = Math.min(p1[0], p2[0]);
    const y1 = Math.min(p1[1], p2[1]);
    const x2 = Math.max(p1[0], p2[0]);
    const y2 = Math.max(p1[1], p2[1]);
    const rows = sanitizeGrid(mask?.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(mask?.cols ?? DEFAULT_GRID);

    const first = pixelToCanvas(polygon[0]);
    if (!first) return;

    state.ctx.save();
    state.ctx.beginPath();
    state.ctx.moveTo(first[0], first[1]);
    for (let i = 1; i < polygon.length; i += 1) {
      const p = pixelToCanvas(polygon[i]);
      if (!p) continue;
      state.ctx.lineTo(p[0], p[1]);
    }
    state.ctx.closePath();
    state.ctx.clip();

    if (showGrid) {
      state.ctx.strokeStyle = color;
      state.ctx.globalAlpha = gridAlpha;
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
    }

    if (mask && Array.isArray(mask.cells)) {
      const cellW = (x2 - x1) / cols;
      const cellH = (y2 - y1) / rows;
      state.ctx.fillStyle = color;
      state.ctx.globalAlpha = cellAlpha;
      mask.cells.forEach((cell) => {
        const rr = toInt(cell[0], -1);
        const cc = toInt(cell[1], -1);
        if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) return;
        state.ctx.fillRect(x1 + cc * cellW, y1 + rr * cellH, cellW, cellH);
      });
    }

    state.ctx.restore();
  }

  function drawPyramidGridAndCells(roi, polygon, mask, color, gridAlpha, cellAlpha, rotation = 0, showGrid = true) {
    if (!Array.isArray(polygon) || polygon.length < 3) {
      drawGrid(roi, mask?.rows ?? DEFAULT_GRID, mask?.cols ?? DEFAULT_GRID, color, gridAlpha);
      drawCells(roi, mask, color, cellAlpha);
      return;
    }
    const box = reorderRoi(roi);
    const c1 = pixelToCanvas(box[0]);
    const c2 = pixelToCanvas(box[1]);
    if (!c1 || !c2) return;
    const cx = (c1[0] + c2[0]) / 2;
    const cy = (c1[1] + c2[1]) / 2;
    const rx = Math.max(1, Math.abs(c2[0] - c1[0]) / 2);
    const ry = Math.max(1, Math.abs(c2[1] - c1[1]) / 2);
    const rows = sanitizeGrid(mask?.rows ?? DEFAULT_GRID);
    const cols = sanitizeGrid(mask?.cols ?? DEFAULT_GRID);

    state.ctx.save();
    state.ctx.translate(cx, cy);
    state.ctx.rotate(rotation);

    // Clip by pyramid polygon expressed in local (unrotated) coordinates.
    const firstCanvas = pixelToCanvas(polygon[0]);
    if (!firstCanvas) {
      state.ctx.restore();
      return;
    }
    const dx0 = firstCanvas[0] - cx;
    const dy0 = firstCanvas[1] - cy;
    const local0 = rotateOffset(dx0, dy0, -rotation);
    state.ctx.beginPath();
    state.ctx.moveTo(local0[0], local0[1]);
    for (let i = 1; i < polygon.length; i += 1) {
      const p = pixelToCanvas(polygon[i]);
      if (!p) continue;
      const dx = p[0] - cx;
      const dy = p[1] - cy;
      const local = rotateOffset(dx, dy, -rotation);
      state.ctx.lineTo(local[0], local[1]);
    }
    state.ctx.closePath();
    state.ctx.clip();

    if (showGrid) {
      state.ctx.strokeStyle = color;
      state.ctx.globalAlpha = gridAlpha;
      state.ctx.lineWidth = 1;
      for (let r = 1; r < rows; r += 1) {
        const y = -ry + (r / rows) * (2 * ry);
        state.ctx.beginPath();
        state.ctx.moveTo(-rx, y);
        state.ctx.lineTo(rx, y);
        state.ctx.stroke();
      }
      for (let c = 1; c < cols; c += 1) {
        const x = -rx + (c / cols) * (2 * rx);
        state.ctx.beginPath();
        state.ctx.moveTo(x, -ry);
        state.ctx.lineTo(x, ry);
        state.ctx.stroke();
      }
    }

    if (mask && Array.isArray(mask.cells)) {
      const cellW = (2 * rx) / cols;
      const cellH = (2 * ry) / rows;
      state.ctx.fillStyle = color;
      state.ctx.globalAlpha = cellAlpha;
      mask.cells.forEach((cell) => {
        const rr = toInt(cell[0], -1);
        const cc = toInt(cell[1], -1);
        if (rr < 0 || cc < 0 || rr >= rows || cc >= cols) return;
        state.ctx.fillRect(
          -rx + cc * cellW,
          -ry + rr * cellH,
          cellW,
          cellH,
        );
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
    // Clip grid lines to ROI bounds so they never bleed outside when viewport resizes.
    state.ctx.beginPath();
    state.ctx.rect(x1, y1, Math.max(0, x2 - x1), Math.max(0, y2 - y1));
    state.ctx.clip();
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
    // Clip cell fills to ROI bounds to avoid spill outside image during responsive resizes.
    state.ctx.beginPath();
    state.ctx.rect(x1, y1, Math.max(0, x2 - x1), Math.max(0, y2 - y1));
    state.ctx.clip();
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
      brushDiameterEl: null,
      brushDiameterValueEl: null,
      fillOpacityEl: null,
      fillOpacityValueEl: null,
      statusEl: null,
      toggleOverlayBtn: null,
      activeAnnotationByFeature: {},
      nextAnnotationId,
      undoStack: [],
      _historyLastSig: null,
      _historyLastSnapshot: clonePayload(initial),
      _suspendHistory: false,
    };

    ensurePanel(ctx);
    updateGridLabel(ctx);
    state.contexts.set(key, ctx);

    if (!hiddenField.value) {
      syncField(ctx);
    } else {
      ctx._historyLastSig = payloadSignature(ctx.payload);
      ctx._historyLastSnapshot = clonePayload(ctx.payload);
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
    if (ctx.brushDiameterEl) {
      ctx.brushDiameterEl.value = String(sanitizeBrushDiameter(state.brushDiameterPx));
    }
    if (ctx.brushDiameterValueEl) {
      ctx.brushDiameterValueEl.textContent = `${sanitizeBrushDiameter(state.brushDiameterPx)}px`;
    }
    if (ctx.fillOpacityEl) {
      ctx.fillOpacityEl.value = String(sanitizeFillOpacityPct(Math.round(state.fillOpacity * 100)));
    }
    if (ctx.fillOpacityValueEl) {
      ctx.fillOpacityValueEl.textContent = `${sanitizeFillOpacityPct(Math.round(state.fillOpacity * 100))}%`;
    }
    refreshFeatureDependentButtons(ctx);
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
    state.viewerRoot.classList.add("fgx-geometry-active");

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
    main.addEventListener("click", handleMainClickForSelection);
    main.addEventListener("pointerdown", handleMainPointerDown);
    main.addEventListener("pointerup", handleMainPointerUp);
    main.addEventListener("pointercancel", handleMainPointerUp);
    main.addEventListener("pointerleave", handleMainPointerUp);
    main.addEventListener("pointermove", handleMainPointerMoveForPanSync);
    main.addEventListener("wheel", handleMainWheelForPanSync, { passive: true });

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
          if (t.checked) {
            const nextId = Number(t.value);
            if (!Number.isNaN(nextId)) {
              state.activeFeatureId = nextId;
              clearSelectedBox();
            }
          }
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
