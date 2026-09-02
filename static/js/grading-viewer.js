(function(){
  if (window.__imggrViewerBootstrapped) {
    try { window.__imggrViewerLoaded = true; } catch(_) {}
    return;
  }
  window.__imggrViewerBootstrapped = true;

  // TODO: add UI + JS support for new filters:
  // greenchannel, blueonly, redgreenfree, greenfree
  // NOTE: DB/model ranges are wider than UI/JS controls:
  // loupe_size 50-1000, loupe_zoom 0.5-8.0, zoom 10-800,
  // pan_x/pan_y -1200-1200, brightness 0-10, contrast 0-10.
  // Active root for global key handling (Safari-friendly)
  let activeRoot = null;
  let defaultRoot = null;

  function selectFilter(root, value){
    try {
      const card = root.closest('.card');
      if (!card) return;
      const input = card.querySelector(`.imggr-filters input[value="${value}"]`);
      if (input) {
        input.checked = true;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
    } catch(_) {}
  }

  // Ordered list of filter values for cycling
  const FILTER_ORDER = ['none','redfree','greenboost','bluemono','gray','contrast','enhance'];
  const viewerStates = new WeakMap();
  const viewerMetadataCache = new Map();
  const DEFAULT_LOUPE_SIZE = 200;
  const LOUPE_SIZE_STEP = 20;
  const LOUPE_SIZE_MIN = 100;
  const LOUPE_SIZE_MAX = 500;
  const DEFAULT_LOUPE_ZOOM = 2;
  const LOUPE_ZOOM_STEP = 0.25;
  const LOUPE_ZOOM_MIN = 1;
  const LOUPE_ZOOM_MAX = 4;
  const LOUPE_STORAGE_KEY = 'imggrLoupePrefs';
  const VIEWER_SETTINGS_KEY = 'imggrViewerSettings';
  const VIEWER_PRESETS_KEY = 'imggrViewerPresets';
  const VIEWER_ZOOM_KEY = 'imggrViewerZoom';
  const IMG_PAN_STEP = 28;
  const ZOOM_MIN = 40;
  const ZOOM_MAX = 500;
  const ZOOM_STEP = 20;
  const KEYBOARD_ZOOM_STEP = 5;
  let viewerPresetsCache = null;
  let viewerPresetsPromise = null;

  function clamp(value, min, max){
    return Math.min(max, Math.max(min, value));
  }

  const ENHANCE_FILTER_ID = 'pswp-enhance';
  let lastEnhanceBrightness = null;

  function applyMaskedBrightnessFilter(brightness){
    const rounded = Math.round((Number(brightness) || 1) * 100) / 100;
    if (lastEnhanceBrightness === rounded) return;
    lastEnhanceBrightness = rounded;
    const filter = document.getElementById(ENHANCE_FILTER_ID);
    if (!filter) return;
    const funcs = filter.querySelectorAll('feComponentTransfer[in="SourceGraphic"] feFuncR, feComponentTransfer[in="SourceGraphic"] feFuncG, feComponentTransfer[in="SourceGraphic"] feFuncB');
    funcs.forEach(fn => fn.setAttribute('slope', String(rounded)));
  }

  // Helper function to get CSRF token from the save button
  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
      || document.querySelector('#imggr-preset-save-button input[name="csrf_token"]')?.value
      || document.querySelector('input[name="csrf_token"]')?.value
      || null;
  }

  // API functions for viewer presets only

  async function fetchViewerPresets() {
    try {
      if (viewerPresetsCache) return viewerPresetsCache;
      if (viewerPresetsPromise) return await viewerPresetsPromise;
      viewerPresetsPromise = fetch('/api/viewer/presets')
        .then(async (response) => response.ok ? await response.json() : {})
        .catch(() => ({}))
        .finally(() => {
          viewerPresetsPromise = null;
        });
      viewerPresetsCache = await viewerPresetsPromise;
      return viewerPresetsCache || {};
    } catch(_) { return {}; }
  }

  function rememberViewerPreset(slotNumber, preset) {
    viewerPresetsCache = { ...(viewerPresetsCache || {}) };
    viewerPresetsCache[String(slotNumber)] = preset;
  }

  function forgetViewerPreset(slotNumber) {
    if (!viewerPresetsCache) return;
    viewerPresetsCache = { ...viewerPresetsCache };
    delete viewerPresetsCache[String(slotNumber)];
  }

  function readViewerZoomState(imageUuid) {
    if (!imageUuid) return null;
    try {
      const raw = window.sessionStorage?.getItem(`${VIEWER_ZOOM_KEY}:${imageUuid}`);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      return {
        zoom: clamp(Number(parsed.zoom) || 100, ZOOM_MIN, ZOOM_MAX),
        panX: Number(parsed.panX) || 0,
        panY: Number(parsed.panY) || 0,
      };
    } catch(_) {
      return null;
    }
  }

  function writeViewerZoomState(imageUuid, state) {
    if (!imageUuid || !state) return;
    try {
      window.sessionStorage?.setItem(`${VIEWER_ZOOM_KEY}:${imageUuid}`, JSON.stringify({
        zoom: clamp(Number(state.zoom) || 100, ZOOM_MIN, ZOOM_MAX),
        panX: Number(state.panX) || 0,
        panY: Number(state.panY) || 0,
      }));
    } catch(_) {}
  }

  async function saveViewerPreset(slotNumber, preset) {
    try {
      // Get CSRF token using the helper function
      const csrfToken = getCsrfToken();
      // console.log('saveViewerPreset called with:', { slotNumber, preset, csrfToken: csrfToken ? 'found' : 'not found' });
      
      const headers = {
        'Content-Type': 'application/json',
      };
      
      // Add CSRF token if available
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }
      
      const response = await fetch(`/api/viewer/presets/${slotNumber}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(preset)
      });
      
     //  console.log('saveViewerPreset response:', { status: response.status,        statusText: response.statusText,        ok: response.ok,        headers: Object.fromEntries(response.headers.entries())      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('saveViewerPreset error response:', errorText);
      }
      if (response.ok) {
        rememberViewerPreset(slotNumber, preset);
      }
      
      return response.ok;
    } catch(error) {
      console.error('saveViewerPreset exception:', error);
      return false;
    }
  }

  async function deleteViewerPreset(slotNumber) {
    try {
      // Get CSRF token from the page
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
      const headers = {};
      
      // Add CSRF token if available
      if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
      }
      
      const response = await fetch(`/api/viewer/presets/${slotNumber}`, {
        method: 'DELETE',
        headers
      });
      if (response.ok) {
        forgetViewerPreset(slotNumber);
      }
      return response.ok;
    } catch(_) { return false; }
  }

  // Legacy localStorage functions for backward compatibility
  function readLoupePrefs(){
    try {
      const raw = window.localStorage?.getItem(LOUPE_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      const size = clamp(Number(parsed.size) || DEFAULT_LOUPE_SIZE, LOUPE_SIZE_MIN, LOUPE_SIZE_MAX);
      const zoom = clamp(Number(parsed.zoom) || DEFAULT_LOUPE_ZOOM, LOUPE_ZOOM_MIN, LOUPE_ZOOM_MAX);
      return { size, zoom };
    } catch(_) { return null; }
  }

  function writeLoupePrefs(prefs){
    if (!prefs) return;
    try {
      window.localStorage?.setItem(LOUPE_STORAGE_KEY, JSON.stringify({
        size: clamp(prefs.size ?? DEFAULT_LOUPE_SIZE, LOUPE_SIZE_MIN, LOUPE_SIZE_MAX),
        zoom: clamp(prefs.zoom ?? DEFAULT_LOUPE_ZOOM, LOUPE_ZOOM_MIN, LOUPE_ZOOM_MAX),
      }));
    } catch(_) {}
  }

  function currentFilter(root){
    try {
      const card = root.closest('.card');
      if (!card) return 'none';
      const checked = card.querySelector('.imggr-filters input[type="radio"]:checked');
      return (checked && checked.value) ? checked.value : 'none';
    } catch(_) { return 'none'; }
  }

  function cycleFilter(root, delta){
    const cur = currentFilter(root);
    const idx = Math.max(0, FILTER_ORDER.indexOf(cur));
    const next = FILTER_ORDER[(idx + delta + FILTER_ORDER.length) % FILTER_ORDER.length];
    selectFilter(root, next);
  }

  function requestFullscreen(el){
    try { (el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen)?.call(el); } catch(_) {}
  }
  function exitFullscreen(){
    try {
      const hasFullscreen = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
      if (!hasFullscreen) return;
      (document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen)?.call(document);
    } catch(_) {}
  }
  function isFullscreenFor(el){
    return document.fullscreenElement === el || document.webkitFullscreenElement === el;
  }

  function adjustRangeInput(input, direction){
    if (!input || !direction) return;
    const stepStr = (input.step && input.step !== '') ? input.step : '0.05';
    const step = parseFloat(stepStr) || 0.05;
    const min = (input.min && input.min !== '') ? parseFloat(input.min) : -Infinity;
    const max = (input.max && input.max !== '') ? parseFloat(input.max) : Infinity;
    const current = parseFloat(input.value) || 0;
    let next = current + (direction * step);
    if (!Number.isFinite(next)) return;
    next = Math.min(max, Math.max(min, next));
    if (Math.abs(next - current) < 1e-6) return;
    const precision = stepStr.includes('.') ? (stepStr.split('.')[1]?.length || 0) : 0;
    const adjusted = precision > 0 ? parseFloat(next.toFixed(precision)) : next;
    input.value = `${adjusted}`;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function hardResetAllLoupes() {
    document.querySelectorAll('.imggr-viewer-root').forEach((root) => {
      const st = viewerStates.get(root) || root.__imggrState;
      st?.turnLoupeOff?.();
    });
    // Defensive DOM cleanup in case a viewer state is stale/missing.
    document.querySelectorAll('.imggr-loupe').forEach((el) => el.classList.remove('is-active'));
    document.querySelectorAll('.imggr-loupe-toggle').forEach((btn) => {
      btn.classList.remove('active');
      btn.setAttribute('aria-pressed', 'false');
    });
  }

  // Bind once: global keyboard shortcuts routed to the active viewer
  if (!window.__imggrKeysBound) {
    window.__imggrKeysBound = true;
    window.addEventListener('keydown', (e) => {
      try {
        const t = e.target;
        const targetRoot = (t && t.closest)
          ? (t.closest('.imggr-viewer-root') || t.closest('.card')?.querySelector('.imggr-viewer-root'))
          : null;
        if (targetRoot) {
          activeRoot = targetRoot;
        }
      } catch(_) {}
      if (!activeRoot) {
        activeRoot = defaultRoot || document.querySelector('.imggr-viewer-root');
        if (!activeRoot) return;
      }
    let state = viewerStates.get(activeRoot);
    if (!state && defaultRoot) {
      activeRoot = defaultRoot;
      state = viewerStates.get(activeRoot);
    }
    if (!state) return;
    if (state && typeof state.isCdrActive === 'function' && state.isCdrActive()) return;
      const rawKey = e.key || '';
      const k = rawKey.toLowerCase();
      const code = e.code || '';
      if (!k) return;
      const card = activeRoot.closest('.card');

      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      const isFormField = ['input','textarea','select'].includes(tag);

      const main = activeRoot.querySelector('.imggr-main');
      if (!main) return;

      const bright = card ? card.querySelector('.imggr-bright') : null;
      const contr = card ? card.querySelector('.imggr-contrast') : null;
      const resetBtn = card ? card.querySelector('.imggr-reset') : null;

      // Always allow global hard reset, even while typing in form fields.
      if (rawKey === '/' || rawKey === '?') {
        e.preventDefault();
        state?.turnLoupeOff?.();
        resetBtn?.click();
        hardResetAllLoupes();
        return;
      }

      if (isFormField) return;

      if (k === 'l') {
        e.preventDefault();
        state?.toggleLoupe?.();
        const loupeBtn = activeRoot?.closest('.card')?.querySelector('.imggr-loupe-toggle');
        if (loupeBtn && document.activeElement === loupeBtn) {
          loupeBtn.blur();
        }
        return;
      }
      if (rawKey === '[' || rawKey === '{' || code === 'BracketLeft') { e.preventDefault(); state?.adjustLoupeSize?.(-1); return; }
      if (rawKey === ']' || rawKey === '}' || code === 'BracketRight') { e.preventDefault(); state?.adjustLoupeSize?.(+1); return; }
      if (rawKey === '-' || rawKey === '_' || code === 'Minus' || code === 'NumpadSubtract') { e.preventDefault(); state?.adjustLoupeZoom?.(-1); return; }
      if (rawKey === '=' || rawKey === '+' || code === 'Equal' || code === 'NumpadAdd') { e.preventDefault(); state?.adjustLoupeZoom?.(+1); return; }
      if (k === 'w') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.adjustImagePan?.(0, -1); return; }
      if (k === 's') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.adjustImagePan?.(0, +1); return; }
      if (k === 'a') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.adjustImagePan?.(-1, 0); return; }
      if (k === 'd') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.adjustImagePan?.(+1, 0); return; }
      // Use Z and X keys for image zoom to avoid conflict with loupe zoom
      if (k === 'z') {
        if (state?.isPanLocked?.()) return;
        e.preventDefault();
        const baseZoom = state?.getCurrentZoom?.() ?? 100;
        state?.setZoomLevel?.(baseZoom + KEYBOARD_ZOOM_STEP);
        return;
      }
      if (k === 'x') {
        if (state?.isPanLocked?.()) return;
        e.preventDefault();
        const baseZoom = state?.getCurrentZoom?.() ?? 100;
        state?.setZoomLevel?.(baseZoom - KEYBOARD_ZOOM_STEP);
        return;
      }
      if (k === '0') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.setZoomLevel?.(100); return; }
      if (k === 'home') { if (state?.isPanLocked?.()) return; e.preventDefault(); state?.fitToContainer?.(); return; }

      if (rawKey === '<' || rawKey === ',') { e.preventDefault(); adjustRangeInput(bright, -1); return; }
      if (rawKey === '>' || rawKey === '.') { e.preventDefault(); adjustRangeInput(bright, +1); return; }
      if (rawKey === ';' || rawKey === ':') { e.preventDefault(); adjustRangeInput(contr, -1); return; }
      if (rawKey === '\'' || rawKey === '"') { e.preventDefault(); adjustRangeInput(contr, +1); return; }
      if (k === 'f') { e.preventDefault(); isFullscreenFor(main) ? exitFullscreen() : requestFullscreen(main); return; }
      if (k === 'escape') { e.preventDefault(); exitFullscreen(); return; }
      if (k === 'arrowleft') { e.preventDefault(); cycleFilter(activeRoot, -1); return; }
      if (k === 'arrowright') { e.preventDefault(); cycleFilter(activeRoot, +1); return; }
      // Preset shortcuts (number keys 1-5)
      if (['1','2','3','4','5'].includes(k)) {
        e.preventDefault();
        const presetNum = parseInt(k);
        const state = viewerStates.get(activeRoot);
        if (state && state.applyPreset) {
          state.applyPreset(presetNum);
        }
        return;
      }
      if (['r','g','b','y','h','e','c','n'].includes(k)) {
        e.preventDefault();
        if (k === 'r') selectFilter(activeRoot, 'redfree');
        else if (k === 'g') selectFilter(activeRoot, 'greenboost');
        else if (k === 'b') selectFilter(activeRoot, 'bluemono');
        else if (k === 'y') selectFilter(activeRoot, 'gray');
        else if (k === 'h') selectFilter(activeRoot, 'contrast');
        else if (k === 'e') selectFilter(activeRoot, 'enhance');
        else selectFilter(activeRoot, 'none');
      }
    }, { capture: true });
  }

  function initGradingViewer(root){
    if (!root) return;
    if (root.__imggrInitialized) {
      const existingState = viewerStates.get(root) || root.__imggrState;
      if (existingState) {
        root.__imggrState = existingState;
      }
      return;
    }
    root.__imggrInitialized = true;

    const main = root.querySelector('.imggr-main');
    const mainImg = root.querySelector('.imggr-main-img');
    const fullBtn = root.querySelector('.imggr-full');
    if (!main || !mainImg) return;
    if (!defaultRoot) defaultRoot = root;
    if (!activeRoot) activeRoot = root;
    const isLiteMode = root.dataset.imggrLiteMode === 'true';

    // Prevent document-level extension hover scanners from repeatedly
    // processing viewer image/canvas elements. Keep scope to this viewer only.
    if (!root.__imggrHoverShieldBound) {
      root.addEventListener('mouseover', (e) => {
        const t = e.target;
        if (t && t.closest && t.closest('img,svg,canvas,a')) {
          e.stopPropagation();
        }
      }, true);
      root.__imggrHoverShieldBound = true;
    }
    
    // Get UUID from root element's data-enc-id attribute
    let uuid = root.dataset.encId;
    const presetModalId = root.dataset.presetModalId || `imggr-preset-modal-${uuid}`;

    // Single image; just wire up fullscreen and activation
    fullBtn?.addEventListener('click', () => { isFullscreenFor(main) ? exitFullscreen() : requestFullscreen(main); });

    // Compose and apply filter (SVG + brightness/contrast)
    const card = root.closest('.card');
    const rad = card ? card.querySelectorAll('.imggr-filters input[type="radio"]') : [];
    const bright = card ? card.querySelector('.imggr-bright') : null;
    const contr = card ? card.querySelector('.imggr-contrast') : null;
    const resetBtn = card ? card.querySelector('.imggr-reset') : null;

    const loupeToggle = card ? card.querySelector('.imggr-loupe-toggle') : null;
    const loupe = root.querySelector('.imggr-loupe');
    const cdrToggle = card ? card.querySelector('.imggr-cdr-toggle') : null;
    const cdrClear = card ? card.querySelector('.imggr-cdr-clear') : null;
    const cdrPanel = card ? card.querySelector('.imggr-cdr-panel') : null;
    const cdrStatus = cdrPanel ? cdrPanel.querySelector('.imggr-cdr-status') : null;
    const cdrValue = cdrPanel ? cdrPanel.querySelector('.imggr-cdr-value') : null;
    const rdrValue = cdrPanel ? cdrPanel.querySelector('.imggr-rdr-value') : null;
    const cdrDone = cdrPanel ? cdrPanel.querySelector('.imggr-cdr-done') : null;
    let loupeEnabled = false;
    const storedLoupe = readLoupePrefs();
    let loupeSize = storedLoupe?.size ?? DEFAULT_LOUPE_SIZE;
    let loupeZoom = storedLoupe?.zoom ?? DEFAULT_LOUPE_ZOOM;
    let lastPointerPos = null;

    let imgPanX = 0;
    let imgPanY = 0;
    let currentZoom = 100; // Store current zoom level as percentage
    let cdrActive = false;
    let cdrStep = 0;
    let cdrDiscPoints = [];
    let cdrCupPoints = [];
    let cdrOverlay = null;
    let cdrDragging = false;
    let cdrDragTarget = null;
    let lastCommentTarget = null;
    let cdrDrawPending = false;
    let cdrLastSize = { width: 0, height: 0 };
    let cdrRedrawTimer = null;
    let cdrBubble = null;
    let cdrBubbleTimer = null;

    const savedZoomState = readViewerZoomState(uuid);
    if (savedZoomState) {
      currentZoom = savedZoomState.zoom;
      imgPanX = savedZoomState.panX;
      imgPanY = savedZoomState.panY;
    }

    function isPanLocked() {
      return root?.dataset?.imggrPanLocked === 'true';
    }

    function applyMetadataToCard(meta) {
      const imageUuidEl = card ? card.querySelector('.imggr-meta-image-uuid') : null;
      const variantEl = card ? card.querySelector('.imggr-meta-variant') : null;
      const formatEl = card ? card.querySelector('.imggr-meta-format') : null;
      const modeEl = card ? card.querySelector('.imggr-meta-mode') : null;
      const bitDepthEl = card ? card.querySelector('.imggr-meta-bitdepth') : null;
      const grayscaleEl = card ? card.querySelector('.imggr-meta-grayscale') : null;
      const alphaEl = card ? card.querySelector('.imggr-meta-alpha') : null;
      const lumEl = card ? card.querySelector('.imggr-meta-luminance') : null;
      const lumStdEl = card ? card.querySelector('.imggr-meta-luminance-std') : null;
      const lumMedianEl = card ? card.querySelector('.imggr-meta-luminance-median') : null;
      const lumPeakEl = card ? card.querySelector('.imggr-meta-luminance-peak') : null;
      const meanRgbEl = card ? card.querySelector('.imggr-meta-mean-rgb') : null;
      const medianRgbEl = card ? card.querySelector('.imggr-meta-median-rgb') : null;
      const dimEl = card ? card.querySelector('.imggr-meta-dimensions') : null;
      const dpiEl = card ? card.querySelector('.imggr-meta-dpi') : null;
      const fileSizeEl = card ? card.querySelector('.imggr-meta-filesize') : null;
      const sizeOkEl = card ? card.querySelector('.imggr-meta-size-ok') : null;
      const createdAtEl = card ? card.querySelector('.imggr-meta-created-at') : null;
      const updatedAtEl = card ? card.querySelector('.imggr-meta-updated-at') : null;
      const pendingEl = card ? card.querySelector('.imggr-meta-pending') : null;
      if (!card || !meta) return;

      const showMeta = (el, text, visible) => {
        if (!el) return;
        if (visible) {
          el.textContent = text;
          el.classList.remove('d-none');
        } else {
          el.classList.add('d-none');
        }
      };
      const formatBytes = (bytes) => {
        const b = Number(bytes);
        if (!Number.isFinite(b) || b <= 0) return null;
        return `${(b / (1024 * 1024)).toFixed(2)} MB`;
      };

      showMeta(imageUuidEl, `Image UUID: ${meta.image_uuid || uuid}`, Boolean((meta.image_uuid || uuid)));
      showMeta(variantEl, `Variant: ${meta.image_variant}`, Boolean(meta.image_variant && String(meta.image_variant).trim()));
      showMeta(formatEl, `Format: ${meta.format}`, Boolean(meta.format && String(meta.format).trim()));
      showMeta(
        bitDepthEl,
        `Bit Depth: ${meta.bit_depth}`,
        meta.bit_depth !== null && meta.bit_depth !== undefined && Number.isFinite(Number(meta.bit_depth))
      );
      showMeta(
        grayscaleEl,
        `Grayscale: ${meta.is_grayscale ? 'Yes' : 'No'}`,
        meta.is_grayscale !== null && meta.is_grayscale !== undefined
      );
      showMeta(
        alphaEl,
        `Alpha: ${meta.has_alpha ? 'Yes' : 'No'}`,
        meta.has_alpha !== null && meta.has_alpha !== undefined
      );
      if (modeEl) {
        if (meta.mode) {
          modeEl.textContent = `Color: ${meta.mode}`;
          modeEl.classList.remove('d-none');
        } else {
          modeEl.classList.add('d-none');
        }
      }
      if (lumEl) {
        if (meta.avg_luminance !== null && meta.avg_luminance !== undefined && Number.isFinite(Number(meta.avg_luminance))) {
          lumEl.textContent = `Luminance: ${Number(meta.avg_luminance).toFixed(1)}`;
          lumEl.classList.remove('d-none');
        } else {
          lumEl.classList.add('d-none');
        }
      }
      showMeta(
        lumStdEl,
        `Lum Std: ${Number(meta.luminance_std).toFixed(1)}`,
        meta.luminance_std !== null && meta.luminance_std !== undefined && Number.isFinite(Number(meta.luminance_std))
      );
      const hasMedianChannels = (
        meta.median_r !== null && meta.median_r !== undefined &&
        meta.median_g !== null && meta.median_g !== undefined &&
        meta.median_b !== null && meta.median_b !== undefined &&
        Number.isFinite(Number(meta.median_r)) &&
        Number.isFinite(Number(meta.median_g)) &&
        Number.isFinite(Number(meta.median_b))
      );
      showMeta(
        lumMedianEl,
        `Median Lum: ${(
          (0.2126 * Number(meta.median_r)) +
          (0.7152 * Number(meta.median_g)) +
          (0.0722 * Number(meta.median_b))
        ).toFixed(1)}`,
        hasMedianChannels
      );
      showMeta(
        lumPeakEl,
        `Peak Lum: ${Number(meta.max_luminance).toFixed(1)}`,
        meta.max_luminance !== null && meta.max_luminance !== undefined && Number.isFinite(Number(meta.max_luminance))
      );
      const hasMeanChannels = (
        meta.mean_r !== null && meta.mean_r !== undefined &&
        meta.mean_g !== null && meta.mean_g !== undefined &&
        meta.mean_b !== null && meta.mean_b !== undefined &&
        Number.isFinite(Number(meta.mean_r)) &&
        Number.isFinite(Number(meta.mean_g)) &&
        Number.isFinite(Number(meta.mean_b))
      );
      showMeta(
        meanRgbEl,
        `Mean RGB: ${Number(meta.mean_r).toFixed(1)},${Number(meta.mean_g).toFixed(1)},${Number(meta.mean_b).toFixed(1)}`,
        hasMeanChannels
      );
      showMeta(
        medianRgbEl,
        `Median RGB: ${Number(meta.median_r).toFixed(1)},${Number(meta.median_g).toFixed(1)},${Number(meta.median_b).toFixed(1)}`,
        hasMedianChannels
      );
      if (dimEl) {
        if (meta.width && meta.height) {
          dimEl.textContent = `Dimensions: ${meta.width}x${meta.height}`;
          dimEl.classList.remove('d-none');
        } else {
          dimEl.classList.add('d-none');
        }
      }
      showMeta(
        dpiEl,
        `DPI: ${meta.dpi_x}x${meta.dpi_y}`,
        Number.isFinite(Number(meta.dpi_x)) && Number.isFinite(Number(meta.dpi_y)) && Number(meta.dpi_x) > 0 && Number(meta.dpi_y) > 0
      );
      const sizeText = formatBytes(meta.file_size_bytes);
      showMeta(fileSizeEl, `Size: ${sizeText}`, Boolean(sizeText));
      showMeta(
        sizeOkEl,
        `Size OK: ${meta.size_ok ? 'Yes' : 'No'}`,
        meta.size_ok !== null && meta.size_ok !== undefined
      );
      showMeta(
        createdAtEl,
        `Meta Created: ${meta.created_at}`,
        Boolean(meta.created_at && String(meta.created_at).trim())
      );
      showMeta(
        updatedAtEl,
        `Meta Updated: ${meta.updated_at}`,
        Boolean(meta.updated_at && String(meta.updated_at).trim())
      );
      if (pendingEl) {
        const hasAny = Boolean(
          (meta.image_uuid && String(meta.image_uuid).trim()) ||
          (meta.image_variant && String(meta.image_variant).trim()) ||
          (meta.format && String(meta.format).trim()) ||
          (meta.mode && String(meta.mode).trim()) ||
          (meta.bit_depth !== null && meta.bit_depth !== undefined) ||
          (meta.is_grayscale !== null && meta.is_grayscale !== undefined) ||
          (meta.has_alpha !== null && meta.has_alpha !== undefined) ||
          (meta.avg_luminance !== null && meta.avg_luminance !== undefined) ||
          (meta.luminance_std !== null && meta.luminance_std !== undefined) ||
          hasMeanChannels ||
          hasMedianChannels ||
          (meta.max_luminance !== null && meta.max_luminance !== undefined) ||
          (meta.width && meta.height) ||
          (Number.isFinite(Number(meta.dpi_x)) && Number.isFinite(Number(meta.dpi_y)) && Number(meta.dpi_x) > 0 && Number(meta.dpi_y) > 0) ||
          Boolean(sizeText) ||
          (meta.size_ok !== null && meta.size_ok !== undefined) ||
          (meta.created_at && String(meta.created_at).trim()) ||
          (meta.updated_at && String(meta.updated_at).trim())
        );
        pendingEl.classList.toggle('d-none', hasAny);
      }
    }

    async function fetchAndHydrateMetadata() {
      if (!uuid || !card) return;
      const hasServerMetadata = root.dataset.imggrMetadataPresent === 'true';
      if (hasServerMetadata) return;

      if (viewerMetadataCache.has(uuid)) {
        applyMetadataToCard(viewerMetadataCache.get(uuid));
        return;
      }

      try {
        const resp = await fetch(`/api/image-metadata/${encodeURIComponent(uuid)}`, { credentials: 'same-origin' });
        if (!resp.ok) return;
        const payload = await resp.json();
        if (!payload || payload.success !== true || !payload.data) return;
        viewerMetadataCache.set(uuid, payload.data);
        applyMetadataToCard(payload.data);
      } catch (_) {}
    }
    
    // Load saved viewer settings from localStorage for rapid loading
    function loadViewerSettingsFromStorage() {
      try {
        const raw = window.localStorage?.getItem(VIEWER_SETTINGS_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return parsed || {};
      } catch(e) {
        console.error('Error loading viewer settings from localStorage:', e);
        return {};
      }
    }
    
    // Load saved settings at the beginning
    const savedSettings = loadViewerSettingsFromStorage();
    
    // Apply saved loupe state
    if (savedSettings.loupeEnabled !== undefined) {
      loupeEnabled = savedSettings.loupeEnabled;
      if (loupeToggle) {
        loupeToggle.setAttribute('aria-pressed', loupeEnabled ? 'true' : 'false');
        loupeToggle.classList.toggle('active', loupeEnabled);
      }
    }

    if (root.dataset.imggrDeferred !== 'true') {
      fetchAndHydrateMetadata();
    }
    
    // Do not restore brightness/contrast/filters across images
    
    // Preset management functions
    async function loadViewerPresets() {
      try {
        const presets = await fetchViewerPresets();
        return presets || {};
      } catch(e) {
        console.error('Error loading viewer presets:', e);
        return {};
      }
    }
    
    async function saveViewerPresets(presets) {
      try {
        // Save each preset individually
        for (const [slotNumber, preset] of Object.entries(presets)) {
          await saveViewerPreset(parseInt(slotNumber), preset);
        }
      } catch(e) {
        console.error('Error saving viewer presets:', e);
      }
    }
    
    function getCurrentSettings() {
      return {
        filter: currentRadio(),
        brightness: bright ? parseFloat(bright.value) : 1,
        contrast: contr ? parseFloat(contr.value) : 1,
        zoom: currentZoom,
        pan_x: Math.round(imgPanX),
        pan_y: Math.round(imgPanY),
        loupe_enabled: loupeEnabled,
        loupe_size: loupeSize,
        loupe_zoom: loupeZoom
      };
    }
    
    function applyPreset(preset) {
      if (!preset) return;
      
      isApplyingSavedSettings = true;
      
      // Apply filter
      if (preset.filter) {
        const filterInput = card.querySelector(`.imggr-filters input[value="${preset.filter}"]`);
        if (filterInput) {
          filterInput.checked = true;
        }
      }
      
      // Apply brightness and contrast
      if (preset.brightness !== undefined && bright) {
        bright.value = clamp(preset.brightness, 0.5, 5);
      }
      if (preset.contrast !== undefined && contr) {
        contr.value = clamp(preset.contrast, 0.5, 5);
      }
      
      // Apply loupe state
      if (preset.zoom !== undefined) {
        currentZoom = clamp(Number(preset.zoom) || 100, ZOOM_MIN, ZOOM_MAX);
      }
      if (preset.pan_x !== undefined) {
        imgPanX = Number(preset.pan_x) || 0;
      }
      if (preset.pan_y !== undefined) {
        imgPanY = Number(preset.pan_y) || 0;
      }
      if (preset.loupe_size !== undefined) {
        loupeSize = clamp(Number(preset.loupe_size) || DEFAULT_LOUPE_SIZE, LOUPE_SIZE_MIN, LOUPE_SIZE_MAX);
        applyLoupeDimensions();
      }
      if (preset.loupe_zoom !== undefined) {
        loupeZoom = clamp(Number(preset.loupe_zoom) || DEFAULT_LOUPE_ZOOM, LOUPE_ZOOM_MIN, LOUPE_ZOOM_MAX);
      }
      if (preset.loupe_enabled !== undefined) {
        setLoupeEnabled(preset.loupe_enabled);
      }
      
      // Apply all changes
      applyFilter();
      clampPanToBounds();
      applyImagePan();
      updateZoomDisplay();
      
      isApplyingSavedSettings = false;
    }
    
    async function updatePresetModal() {
      const modal = document.getElementById(presetModalId);
      if (!modal) return;
      
      const presets = await loadViewerPresets();
      const currentSettings = getCurrentSettings();
      
      // Update current settings display
      const filterDisplay = modal.querySelector('[data-current-filter], #current-filter-display');
      const brightnessDisplay = modal.querySelector('[data-current-brightness], #current-brightness-display');
      const contrastDisplay = modal.querySelector('[data-current-contrast], #current-contrast-display');
      const zoomDisplay = modal.querySelector('[data-current-zoom]');
      const panDisplay = modal.querySelector('[data-current-pan]');
      const loupeDisplay = modal.querySelector('[data-current-loupe]');
      
      if (filterDisplay) filterDisplay.textContent = currentSettings.filter || 'None';
      if (brightnessDisplay) brightnessDisplay.textContent = (currentSettings.brightness || 1).toFixed(2);
      if (contrastDisplay) contrastDisplay.textContent = (currentSettings.contrast || 1).toFixed(2);
      if (zoomDisplay) zoomDisplay.textContent = `${currentSettings.zoom}%`;
      if (panDisplay) panDisplay.textContent = `${currentSettings.pan_x}, ${currentSettings.pan_y} px`;
      if (loupeDisplay) {
        loupeDisplay.textContent = currentSettings.loupe_enabled
          ? `On · ${currentSettings.loupe_size}px · ${Number(currentSettings.loupe_zoom).toFixed(1)}x`
          : 'Off';
      }
      
      // Update preset slots
      const slotsContainer = modal.querySelector('[data-preset-slots], #preset-slots');
      if (slotsContainer) {
        // Clear the slots container first
        slotsContainer.innerHTML = '';
        
        for (let i = 1; i <= 5; i++) {
          const preset = presets[i];
          const slotDiv = document.createElement('div');
          slotDiv.className = 'card';
          
          let presetInfo = '<span class="text-muted">Empty slot</span>';
          if (preset) {
            presetInfo = `
              <span><strong>Filter:</strong> ${preset.filter || 'none'}</span>
              <span><strong>Brightness:</strong> ${Number(preset.brightness || 1).toFixed(2)}</span>
              <span><strong>Contrast:</strong> ${Number(preset.contrast || 1).toFixed(2)}</span>
              <span><strong>Zoom:</strong> ${Number(preset.zoom || 100)}%</span>
              <span><strong>Pan:</strong> ${Number(preset.pan_x || 0)}, ${Number(preset.pan_y || 0)} px</span>
              <span><strong>Loupe:</strong> ${preset.loupe_enabled ? `On · ${Number(preset.loupe_size || 200)}px · ${Number(preset.loupe_zoom || 2).toFixed(1)}x` : 'Off'}</span>
            `;
          }
          
          slotDiv.innerHTML = `
            <div class="card-body p-3">
              <div class="d-flex flex-wrap justify-content-between align-items-center gap-3">
                <div class="flex-grow-1">
                  <strong>Preset ${i}</strong>
                  <div class="small d-flex flex-wrap gap-3 mt-1">${presetInfo}</div>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="button" class="btn btn-sm btn-primary save-preset-slot" data-preset="${i}">
                    Save current to ${i}
                  </button>
                  ${preset ? `
                    <button type="button" class="btn btn-sm btn-outline-success apply-preset-btn" data-preset="${i}">Apply</button>
                    <button type="button" class="btn btn-sm btn-outline-danger delete-preset-btn" data-preset="${i}">Delete</button>
                  ` : ''}
                </div>
              </div>
            </div>
          `;
          
          slotsContainer.appendChild(slotDiv);
        }
        
        // Add click handlers for preset buttons
        slotsContainer.querySelectorAll('.save-preset-slot').forEach(btn => {
          btn.addEventListener('click', async (e) => {
            const presetNum = parseInt(e.target.dataset.preset);
            const currentSettings = getCurrentSettings();
            const saved = await saveViewerPreset(presetNum, currentSettings);
            if (!saved) {
              showPresetStatus(modal, `Preset ${presetNum} could not be saved.`, 'danger');
              return;
            }
            
            // Update the modal to reflect the saved preset
            await updatePresetModal();
            showPresetStatus(modal, `Current settings saved to preset ${presetNum}.`, 'success');
            
            // Show feedback
            const presetBtn = card.querySelector(`.imggr-preset-btn[data-preset="${presetNum}"]`);
            if (presetBtn) {
              presetBtn.classList.add('btn-success');
              setTimeout(() => presetBtn.classList.remove('btn-success'), 1000);
            }
          });
        });
        
        // Add click handlers for apply buttons
        slotsContainer.querySelectorAll('.apply-preset-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            const presetNum = parseInt(e.target.dataset.preset);
            const preset = presets[presetNum];
            
            if (preset) {
              applyPreset(preset);
              // Close modal
              const modalInstance = bootstrap.Modal.getInstance(modal);
              if (modalInstance) modalInstance.hide();
              
              // Show feedback
              const presetBtn = card.querySelector(`.imggr-preset-btn[data-preset="${presetNum}"]`);
              if (presetBtn) {
                presetBtn.classList.add('btn-success');
                setTimeout(() => presetBtn.classList.remove('btn-success'), 500);
              }
            }
          });
        });
        
        // Add click handlers for delete buttons
        slotsContainer.querySelectorAll('.delete-preset-btn').forEach(btn => {
          btn.addEventListener('click', async (e) => {
            const presetNum = parseInt(e.target.dataset.preset);
            
            if (confirm('Are you sure you want to delete this preset?')) {
              const deleted = await deleteViewerPreset(presetNum);
              if (!deleted) {
                showPresetStatus(modal, `Preset ${presetNum} could not be deleted.`, 'danger');
                return;
              }
              
              // Update the modal to reflect the deletion
              await updatePresetModal();
              showPresetStatus(modal, `Preset ${presetNum} deleted.`, 'success');
              
              // Show feedback
              const presetBtn = card.querySelector(`.imggr-preset-btn[data-preset="${presetNum}"]`);
              if (presetBtn) {
                presetBtn.classList.remove('btn-success');
                setTimeout(() => presetBtn.classList.remove('btn-success'), 500);
              }
            }
          });
        });
      }
    }

    function showPresetStatus(modal, message, level) {
      const status = modal.querySelector('[data-preset-status]');
      if (!status) return;
      status.textContent = message;
      status.className = `alert alert-${level} py-2`;
    }
    
    let saveViewerSettingsTimer = null;
    function writeViewerSettingsToStorage() {
      if (isLiteMode) return;
      try {
        const settings = {
          loupeEnabled: loupeEnabled
        };
        window.localStorage?.setItem(VIEWER_SETTINGS_KEY, JSON.stringify(settings));
        writeViewerZoomState(uuid, {
          zoom: currentZoom,
          panX: imgPanX,
          panY: imgPanY,
        });
      } catch(e) {
        console.error('Error saving viewer settings to localStorage:', e);
      }
    }
    
    function saveViewerSettingsToStorage(options = {}) {
      if (isLiteMode) return;
      const immediate = options && options.immediate === true;
      if (immediate) {
        if (saveViewerSettingsTimer) {
          clearTimeout(saveViewerSettingsTimer);
          saveViewerSettingsTimer = null;
        }
        writeViewerSettingsToStorage();
        return;
      }
      if (saveViewerSettingsTimer) {
        clearTimeout(saveViewerSettingsTimer);
      }
      saveViewerSettingsTimer = setTimeout(() => {
        saveViewerSettingsTimer = null;
        writeViewerSettingsToStorage();
      }, 150);
    }
    
    // Touch/gesture state
    let touchStartDistance = 0;
    let touchStartZoom = 100;
    let touchStartPanX = 0;
    let touchStartPanY = 0;
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let twoFingerStartCenterX = 0;
    let twoFingerStartCenterY = 0;
    let isMouseDragging = false;
    let mouseDragStartX = 0;
    let mouseDragStartY = 0;
    let mouseDragStartPanX = 0;
    let mouseDragStartPanY = 0;

    function svgUrlFor(val){
      switch((val||'').toLowerCase()){
        case 'redfree': return 'url(#pswp-greenmono)';
        case 'greenboost': return 'url(#pswp-greenboost)';
        case 'bluemono': return 'url(#pswp-bluemono)';
        case 'gray': return 'url(#pswp-gray)';
        case 'contrast': return 'url(#pswp-contrast)';
        case 'enhance': return 'url(#pswp-enhance)';
        default: return '';
      }
    }
    function currentRadio(){
      if (!card) return 'none';
      const c = card.querySelector('.imggr-filters input[type="radio"]:checked');
      return c ? c.value : 'none';
    }
    // Flags to indicate if we're in initial setup mode (don't save settings during initialization)
    let isInitializing = true;
    let isApplyingSavedSettings = false;
    
    function applyFilter(){
      const filterVal = currentRadio();
      const url = svgUrlFor(filterVal);
      const b = parseFloat((bright && bright.value) || '1') || 1;
      const c = parseFloat((contr && contr.value) || '1') || 1;
      let chain = `${url}${url? ' ' : ''}brightness(${b}) contrast(${c})`;
      if (filterVal === 'enhance') {
        applyMaskedBrightnessFilter(b);
        chain = `${url}${url? ' ' : ''}brightness(1) contrast(${c})`;
      }
      try {
        mainImg.style.filter = chain;
        if (loupe) loupe.style.filter = chain;
      } catch(_) {}
      updateZoomDisplay();
      // Save settings to localStorage for rapid loading
      saveViewerSettingsToStorage();
    }
    rad && rad.forEach && rad.forEach(r => r.addEventListener('change', applyFilter));
    const brightTip = card ? card.querySelector('.imggr-bright-tip') : null;
    const contrastTip = card ? card.querySelector('.imggr-contrast-tip') : null;

    function showRangeTip(inputEl, tipEl, value){
      if (!inputEl || !tipEl) return;
      tipEl.classList.remove('d-none');
      const min = parseFloat(inputEl.min || '0');
      const max = parseFloat(inputEl.max || '1');
      const raw = Number(value);
      const pct = max > min ? (raw - min) / (max - min) : 0;
      const trackWidth = inputEl.clientWidth;
      const thumbOffset = 8;
      const tipWidth = tipEl.offsetWidth || 0;
      const leftPx = Math.min(
        Math.max(trackWidth * pct - thumbOffset, 0),
        Math.max(trackWidth - tipWidth, 0)
      );

      const numeric = Number(value);
      tipEl.textContent = Number.isFinite(numeric) ? numeric.toFixed(2) : `${value}`;
      tipEl.style.left = `${leftPx}px`;
      tipEl.style.top = '-1.6rem';
      if (tipEl._hideTimer) {
        clearTimeout(tipEl._hideTimer);
      }
      tipEl._hideTimer = setTimeout(() => {
        tipEl.classList.add('d-none');
      }, 1200);
    }

    function attachRangeBlur(inputEl){
      if (!inputEl) return;
      const blurIfFocused = () => {
        if (document.activeElement === inputEl) {
          inputEl.blur();
        }
      };
      inputEl.addEventListener('change', blurIfFocused);
      inputEl.addEventListener('pointerup', blurIfFocused);
      inputEl.addEventListener('touchend', blurIfFocused);
      inputEl.addEventListener('mouseup', blurIfFocused);
    }

    bright && bright.addEventListener('input', () => {
      applyFilter();
      showRangeTip(bright, brightTip, bright.value);
    });
    attachRangeBlur(bright);
    contr && contr.addEventListener('input', () => {
      applyFilter();
      showRangeTip(contr, contrastTip, contr.value);
    });
    attachRangeBlur(contr);
    contr && contr.addEventListener('input', applyFilter);
    resetBtn && resetBtn.addEventListener('click', () => {
      if (bright) bright.value = '1';
      if (contr) contr.value = '1';
      const none = card && card.querySelector('.imggr-filters input[value="none"]');
      if (none) {
        none.checked = true;
        none.dispatchEvent(new Event('change', { bubbles: true }));
      }
      // Reset both zoom and pan
      resetImagePan();
      turnLoupeOff();
      hardResetAllLoupes();
      applyFilter();
      // Settings are saved by applyFilter()
    });
    // Initial apply without saving
    const initFilter = currentRadio();
    const url = svgUrlFor(initFilter);
    const b = parseFloat((bright && bright.value) || '1') || 1;
    const c = parseFloat((contr && contr.value) || '1') || 1;
    let chain = `${url}${url? ' ' : ''}brightness(${b}) contrast(${c})`;
    if (initFilter === 'enhance') {
      applyMaskedBrightnessFilter(b);
      chain = `${url}${url? ' ' : ''}brightness(1) contrast(${c})`;
    }
    try {
      mainImg.style.filter = chain;
      if (loupe) loupe.style.filter = chain;
    } catch(_) {}
    
    // Apply saved settings immediately if the image is already loaded
    function applySavedSettings() {
      isApplyingSavedSettings = true;
      
      // Apply saved filter
      // Apply current defaults only (no persisted filters/brightness/contrast)
      applyFilter();
      
      // Mark initialization as complete so future changes will be saved
      isInitializing = false;
      isApplyingSavedSettings = false;
    }
    
    // Apply saved filter and brightness/contrast after image is loaded
    mainImg.addEventListener('load', () => {
      updateViewportSize();
      clampPanToBounds();
      applyImagePan();
      applySavedSettings();
      if (loupeEnabled) updateLoupeAssets();
      if (loupeEnabled && lastPointerPos) updateLoupePosition(lastPointerPos);
      updateZoomDisplay();
      if (cdrDiscPoints.length || cdrCupPoints.length || cdrActive) {
        resizeCdrOverlay();
        scheduleCdrDraw();
      }
    });
    
    // If image is already loaded, apply settings immediately
    if (mainImg.complete && mainImg.naturalWidth > 0) {
      updateViewportSize();
      clampPanToBounds();
      applyImagePan();
      applySavedSettings();
    }

    if (main) {
      main.addEventListener('click', handleCdrClick);
      main.addEventListener('pointerdown', handleCdrPointerDown);
      main.addEventListener('pointermove', handleCdrPointerMove);
      main.addEventListener('pointerup', handleCdrPointerUp);
      main.addEventListener('pointerleave', handleCdrPointerUp);
      main.addEventListener('pointercancel', handleCdrPointerUp);
    }

    window.addEventListener('resize', () => {
      if (cdrDiscPoints.length || cdrCupPoints.length || cdrActive) {
        resizeCdrOverlay();
        scheduleCdrDraw();
      }
    });

    const commentTargets = findCommentTargets();
    commentTargets.forEach(el => {
      el.addEventListener('focus', () => {
        lastCommentTarget = el;
      });
      el.addEventListener('click', () => {
        lastCommentTarget = el;
      });
    });

    function applyLoupeDimensions(){
      if (!loupe) return;
      loupe.style.width = `${loupeSize}px`;
      loupe.style.height = `${loupeSize}px`;
    }

    function updateViewportSize(){
      if (!main || !root) return;
      if (main.dataset.fixedViewport === 'true') {
        return;
      }
      const configuredMinimum = Number.parseFloat(main.dataset.minViewportSize || '260');
      const minimumSize = Number.isFinite(configuredMinimum) ? Math.max(0, configuredMinimum) : 260;
      const wrap = main.closest('.imggr-main-wrap');
      const wrapRect = wrap ? wrap.getBoundingClientRect() : null;
      const rootRect = root.getBoundingClientRect();
      let availableW = (wrapRect && wrapRect.width) ? wrapRect.width : rootRect.width;
      const measuredHeights = [wrapRect?.height, rootRect.height].filter(
        value => Number.isFinite(value) && value > 0
      );
      let availableH = measuredHeights.length ? Math.min(...measuredHeights) : 0;

      if (!Number.isFinite(availableW) || availableW <= 0) {
        availableW = window.innerWidth * 0.92;
      }
      if (!Number.isFinite(availableH) || availableH <= 0) {
        const approxBottomMargin = 180;
        availableH = window.innerHeight - rootRect.top - approxBottomMargin;
      }

      const fitToWidth = main.dataset.fitMode === 'width'
        && window.matchMedia('(max-width: 991.98px)').matches;
      if (fitToWidth) {
        // Narrow layouts: span the full column width and take only the height
        // the image needs (capped at a square) so the whole image is visible.
        const targetW = Math.floor(Math.max(minimumSize, availableW));
        const natW = mainImg?.naturalWidth || 0;
        const natH = mainImg?.naturalHeight || 0;
        const aspect = natW > 0 && natH > 0 ? natH / natW : 1;
        const targetH = Math.floor(Math.max(minimumSize, Math.min(targetW, targetW * aspect)));
        main.style.width = `${targetW}px`;
        main.style.height = `${targetH}px`;
        return;
      }

      const viewportCap = Math.max(minimumSize, window.innerHeight * 0.72);
      const targetSize = Math.floor(Math.max(minimumSize, Math.min(availableW, availableH, viewportCap)));
      main.style.width = `${targetSize}px`;
      main.style.height = `${targetSize}px`;
    }

    function refreshViewportSize(){
      main.style.removeProperty('width');
      main.style.removeProperty('height');
      updateViewportSize();
      clampPanToBounds();
      applyImagePan();
      updateZoomDisplay();
    }

    const viewportWrap = main.closest('.imggr-main-wrap');
    if (viewportWrap && window.ResizeObserver && !root.__imggrViewportObserver) {
      root.__imggrViewportObserver = new ResizeObserver(() => {
        window.requestAnimationFrame(() => {
          updateViewportSize();
          clampPanToBounds();
          applyImagePan();
          updateZoomDisplay();
        });
      });
      root.__imggrViewportObserver.observe(viewportWrap);
    }

    function getPanRangePx(zoomPercent = currentZoom){
      if (!main || !mainImg) {
        return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
      }
      const containerW = main.clientWidth || 0;
      const containerH = main.clientHeight || 0;
      const natW = mainImg.naturalWidth || 0;
      const natH = mainImg.naturalHeight || 0;
      if (!containerW || !containerH || !natW || !natH) {
        return { minX: 0, maxX: 0, minY: 0, maxY: 0 };
      }

      const imgAspect = natW / natH;
      const containerAspect = containerW / containerH;
      let baseW = containerW;
      let baseH = containerH;
      if (imgAspect > containerAspect) {
        baseW = containerW;
        baseH = containerW / imgAspect;
      } else {
        baseH = containerH;
        baseW = containerH * imgAspect;
      }

      const scale = Math.max(0.01, zoomPercent / 100);
      const scaledW = baseW * scale;
      const scaledH = baseH * scale;
      const overflowX = Math.max(0, scaledW - containerW);
      const overflowY = Math.max(0, scaledH - containerH);
      return { minX: -overflowX, maxX: 0, minY: -overflowY, maxY: 0 };
    }

    function clampPanToBounds(){
      const { minX, maxX, minY, maxY } = getPanRangePx(currentZoom);
      imgPanX = clamp(imgPanX, minX, maxX);
      imgPanY = clamp(imgPanY, minY, maxY);
    }

    function applyImagePan(){
      if (!mainImg) return;
      clampPanToBounds();
      mainImg.style.transform = `translate3d(${imgPanX}px, ${imgPanY}px, 0) scale(${currentZoom / 100})`;
      if (cdrDiscPoints.length || cdrCupPoints.length || cdrActive) {
        setCdrOverlayVisible(false);
        scheduleCdrRedrawAfterIdle();
      }
    }

    function getDisplayedImageMetrics(){
      if (!mainImg || !main) return null;
      const rect = mainImg.getBoundingClientRect();
      const containerRect = main.getBoundingClientRect();
      const natW = mainImg.naturalWidth || 0;
      const natH = mainImg.naturalHeight || 0;
      if (!rect.width || !rect.height || !natW || !natH) {
        return {
          rect,
          displayWidth: rect.width,
          displayHeight: rect.height,
          offsetX: rect.left - containerRect.left,
          offsetY: rect.top - containerRect.top,
          zoomLevel: 0,
        };
      }
      const displayWidth = rect.width;
      const displayHeight = rect.height;
      const offsetX = rect.left - containerRect.left;
      const offsetY = rect.top - containerRect.top;
      const zoomLevel = Math.round((displayWidth / natW) * 100);
      return { rect, displayWidth, displayHeight, offsetX, offsetY, zoomLevel, natW, natH };
    }


    function ensureCdrOverlay(){
      if (!main) return null;
      if (!cdrOverlay) {
        cdrOverlay = document.createElement('canvas');
        cdrOverlay.className = 'imggr-cdr-overlay';
        cdrOverlay.setAttribute('aria-hidden', 'true');
        cdrOverlay.style.position = 'absolute';
        cdrOverlay.style.top = '0';
        cdrOverlay.style.left = '0';
        cdrOverlay.style.width = '100%';
        cdrOverlay.style.height = '100%';
        cdrOverlay.style.pointerEvents = 'none';
        main.appendChild(cdrOverlay);
      }
      return cdrOverlay;
    }

    function resizeCdrOverlay(){
      if (!cdrOverlay || !main) return;
      const rect = main.getBoundingClientRect();
      const deviceScale = window.devicePixelRatio || 1;
      const nextWidth = Math.max(1, Math.round(rect.width * deviceScale));
      const nextHeight = Math.max(1, Math.round(rect.height * deviceScale));
      if (nextWidth === cdrLastSize.width && nextHeight === cdrLastSize.height) {
        return;
      }
      cdrLastSize = { width: nextWidth, height: nextHeight };
      cdrOverlay.width = nextWidth;
      cdrOverlay.height = nextHeight;
      const ctx = cdrOverlay.getContext('2d');
      if (ctx) {
        ctx.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
      }
    }

    function updateCdrStatus(text){
      if (cdrStatus) {
        cdrStatus.textContent = text;
      }
    }

    function ensureCdrBubble() {
      if (cdrBubble) return cdrBubble;
      cdrBubble = document.createElement('div');
      cdrBubble.className = 'imggr-cdr-bubble';
      cdrBubble.setAttribute('aria-live', 'polite');
      cdrBubble.style.position = 'fixed';
      cdrBubble.style.zIndex = '1080';
      cdrBubble.style.maxWidth = '420px';
      cdrBubble.style.padding = '0.45rem 0.65rem';
      cdrBubble.style.borderRadius = '0.5rem';
      cdrBubble.style.background = 'rgba(33, 37, 41, 0.95)';
      cdrBubble.style.color = '#fff';
      cdrBubble.style.boxShadow = '0 0.4rem 1rem rgba(0,0,0,0.2)';
      cdrBubble.style.fontSize = '0.82rem';
      cdrBubble.style.lineHeight = '1.25';
      cdrBubble.style.pointerEvents = 'none';
      cdrBubble.style.display = 'none';
      document.body.appendChild(cdrBubble);
      return cdrBubble;
    }

    function positionCdrBubble() {
      if (!cdrBubble || !main) return;
      const rect = main.getBoundingClientRect();
      const margin = 10;
      const left = clamp(rect.left + margin, 8, Math.max(8, window.innerWidth - 440));
      const top = clamp(rect.top + margin, 8, Math.max(8, window.innerHeight - 80));
      cdrBubble.style.left = `${left}px`;
      cdrBubble.style.top = `${top}px`;
    }

    function hideCdrBubble() {
      if (cdrBubbleTimer) {
        clearTimeout(cdrBubbleTimer);
        cdrBubbleTimer = null;
      }
      if (cdrBubble) {
        cdrBubble.style.display = 'none';
      }
    }

    function showCdrBubble(text, persistent) {
      if (!text) {
        hideCdrBubble();
        return;
      }
      const bubble = ensureCdrBubble();
      bubble.textContent = text;
      positionCdrBubble();
      bubble.style.display = 'block';
      if (cdrBubbleTimer) {
        clearTimeout(cdrBubbleTimer);
        cdrBubbleTimer = null;
      }
      if (!persistent) {
        cdrBubbleTimer = setTimeout(() => {
          hideCdrBubble();
        }, 2400);
      }
    }

    function resetCdrValues(){
      if (cdrValue) cdrValue.textContent = '—';
      if (rdrValue) rdrValue.textContent = '—';
    }

    function clearCdrState(){
      cdrStep = 0;
      cdrDiscPoints = [];
      cdrCupPoints = [];
      resetCdrValues();
      setCdrDoneEnabled(false);
      scheduleCdrDraw();
      updateCdrStatus('');
      hideCdrBubble();
      if (cdrClear) cdrClear.disabled = true;
    }

    function setViewerControlsLocked(flag){
      if (!card) return;
      const disabled = !!flag;
      card.classList.toggle('imggr-cdr-locked', disabled);
      updateZoomControlLocks();
    }

    function updateZoomControlLocks() {
      if (!card) return;
      const zoomSlider = card.querySelector('.imggr-zoom-slider');
      const zoomFitButton = card.querySelector('.imggr-zoom-fit');
      const locked = isPanLocked() || cdrActive;
      if (zoomSlider) zoomSlider.disabled = locked;
      if (zoomFitButton) zoomFitButton.disabled = locked;
    }

    function findCommentTargets(){
      const candidates = Array.from(document.querySelectorAll('textarea'))
        .filter(el => {
          if (el.disabled) return false;
          if (el.closest('[aria-hidden="true"]')) return false;
          if (el.offsetParent === null) return false;
          const name = (el.getAttribute('name') || '').toLowerCase();
          const id = (el.getAttribute('id') || '').toLowerCase();
          return name.startsWith('comment') || id.includes('comment');
        });
      return candidates;
    }

    function selectCommentTarget(){
      if (lastCommentTarget && !lastCommentTarget.disabled) {
        return lastCommentTarget;
      }
      const candidates = findCommentTargets();
      if (candidates.length === 1) return candidates[0];
      if (candidates.length > 1) {
        const focused = candidates.find(el => el === document.activeElement);
        if (focused) return focused;
        return candidates[0];
      }
      return null;
    }

    function normalizeCdrNumber(value, decimals){
      const num = Number(value);
      if (!Number.isFinite(num)) return '0.00';
      return num.toFixed(decimals);
    }

    function buildCdrTag(){
      if (cdrDiscPoints.length !== 2 || cdrCupPoints.length !== 2) return null;
      const discA = cdrDiscPoints[0];
      const discB = cdrDiscPoints[1];
      const cupA = cdrCupPoints[0];
      const cupB = cdrCupPoints[1];
      const discLength = Math.hypot(discB.x - discA.x, discB.y - discA.y);
      const cupLength = Math.hypot(cupB.x - cupA.x, cupB.y - cupA.y);
      if (!discLength) return null;
      const cdr = Math.min(1, Math.max(0, cupLength / discLength));
      const rdr = Math.min(1, Math.max(0, 1 - cdr));
      const metrics = getDisplayedImageMetrics();
      const natW = metrics ? metrics.natW : 0;
      const natH = metrics ? metrics.natH : 0;
      const toPx = (pt) => ({
        x: Math.round((pt.x || 0) * natW),
        y: Math.round((pt.y || 0) * natH)
      });
      const coord = (pt) => `${toPx(pt).x},${toPx(pt).y}`;
      const discLine = `(${coord(discA)})-(${coord(discB)})`;
      const cupSeg = `(${coord(cupA)})-(${coord(cupB)})`;
      return `CDR=${normalizeCdrNumber(cdr, 2)}; RDR=${normalizeCdrNumber(rdr, 2)}; DiscLine=${discLine}; CupSeg=${cupSeg}`;
    }

    function upsertCdrTag(text, tag){
      const regex = /CDR=[^;]+;\s*RDR=[^;]+;\s*DiscLine=\([^\)]*\)-\([^\)]*\);\s*CupSeg=\([^\)]*\)-\([^\)]*\)/;
      if (regex.test(text)) {
        return text.replace(regex, tag);
      }
      if (!text) return tag;
      return `${text.trim()}\n${tag}`;
    }

    function setCdrDoneEnabled(flag){
      if (cdrDone) {
        cdrDone.disabled = !flag;
      }
    }

    function setCdrActive(active){
      cdrActive = !!active;
      if (cdrToggle) {
        cdrToggle.setAttribute('aria-pressed', cdrActive ? 'true' : 'false');
        cdrToggle.classList.toggle('active', cdrActive);
      }
      setViewerControlsLocked(cdrActive);
      if (cdrActive) {
        if (cdrPanel) cdrPanel.classList.add('is-active');
        ensureCdrOverlay();
        resizeCdrOverlay();
        setCdrOverlayVisible(true);
        cdrStep = 1;
        updateCdrStatus('Active');
        showCdrBubble('CDR/RDR: Step 1 of 2. Click two points to draw the disc diameter line.', true);
        if (cdrClear) cdrClear.disabled = false;
        setCdrDoneEnabled(cdrDiscPoints.length === 2 && cdrCupPoints.length === 2);
      } else {
        if (cdrPanel) cdrPanel.classList.remove('is-active');
        clearCdrState();
        setCdrOverlayVisible(false);
      }
    }

    function resetCdrForRedraw(){
      clearCdrState();
      cdrStep = 1;
      updateCdrStatus('Active');
      showCdrBubble('CDR/RDR cleared. Click two points to draw the disc diameter line.', true);
      if (cdrClear) cdrClear.disabled = false;
      setCdrOverlayVisible(true);
    }

    function projectPointToLine(point, lineStart, lineEnd){
      const vx = lineEnd.x - lineStart.x;
      const vy = lineEnd.y - lineStart.y;
      const lenSq = (vx * vx) + (vy * vy);
      if (lenSq == 0) {
        return { x: lineStart.x, y: lineStart.y, t: 0 };
      }
      const rawT = ((point.x - lineStart.x) * vx + (point.y - lineStart.y) * vy) / lenSq;
      const t = Math.min(1, Math.max(0, rawT));
      return {
        x: lineStart.x + t * vx,
        y: lineStart.y + t * vy,
        t
      };
    }

    function getPointOnImageFromEvent(event){
      if (!main || !mainImg) return null;
      const rect = main.getBoundingClientRect();
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return null;
      const { displayWidth, displayHeight, offsetX, offsetY } = metrics;
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      const imgLeft = offsetX;
      const imgTop = offsetY;
      const imgRight = offsetX + displayWidth;
      const imgBottom = offsetY + displayHeight;
      if (pointerX < imgLeft || pointerX > imgRight || pointerY < imgTop || pointerY > imgBottom) {
        return null;
      }
      const relX = (pointerX - imgLeft) / displayWidth;
      const relY = (pointerY - imgTop) / displayHeight;
      return { x: relX, y: relY };
    }


    function getCanvasPointForImagePoint(point){
      if (!main || !point) return null;
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return null;
      const { displayWidth, displayHeight, offsetX, offsetY } = metrics;
      return {
        x: offsetX + point.x * displayWidth,
        y: offsetY + point.y * displayHeight
      };
    }

    function findNearestCdrPoint(point, thresholdPx){
      const threshold = thresholdPx || 10;
      const target = getCanvasPointForImagePoint(point);
      if (!target) return null;

      const candidates = [];
      cdrDiscPoints.forEach((pt, idx) => {
        const c = getCanvasPointForImagePoint(pt);
        if (!c) return;
        candidates.push({ type: 'disc', index: idx, dist: Math.hypot(c.x - target.x, c.y - target.y) });
      });
      cdrCupPoints.forEach((pt, idx) => {
        const c = getCanvasPointForImagePoint(pt);
        if (!c) return;
        candidates.push({ type: 'cup', index: idx, dist: Math.hypot(c.x - target.x, c.y - target.y) });
      });
      if (!candidates.length) return null;
      candidates.sort((a, b) => a.dist - b.dist);
      const nearest = candidates[0];
      if (nearest.dist > threshold) return null;
      return nearest;
    }

    function updateCdrPoint(pointType, index, point){
      if (pointType === 'disc') {
        cdrDiscPoints[index] = point;
        if (cdrDiscPoints.length === 2 && cdrCupPoints.length > 0) {
          cdrCupPoints = cdrCupPoints.map(pt => {
            const projected = projectPointToLine(pt, cdrDiscPoints[0], cdrDiscPoints[1]);
            return { x: projected.x, y: projected.y };
          });
        }
      } else if (pointType === 'cup') {
        const projected = projectPointToLine(point, cdrDiscPoints[0], cdrDiscPoints[1]);
        cdrCupPoints[index] = { x: projected.x, y: projected.y };
      }
      scheduleCdrDraw();
      updateCdrValues();
    }

    function drawLine(ctx, start, end, color, width){
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.stroke();
      ctx.restore();
    }

    function drawPoint(ctx, point, color){
      ctx.save();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    function setCdrOverlayVisible(flag){
      if (!cdrOverlay) return;
      cdrOverlay.style.opacity = flag ? '1' : '0';
    }

    function scheduleCdrRedrawAfterIdle(){
      if (cdrRedrawTimer) {
        clearTimeout(cdrRedrawTimer);
      }
      cdrRedrawTimer = setTimeout(() => {
        cdrRedrawTimer = null;
        if (!cdrOverlay) return;
        resizeCdrOverlay();
        drawCdrOverlay();
        setCdrOverlayVisible(cdrActive);
      }, 1500);
    }

    function scheduleCdrDraw(){
      if (cdrDrawPending) return;
      cdrDrawPending = true;
      requestAnimationFrame(() => {
        cdrDrawPending = false;
        drawCdrOverlay();
        setCdrOverlayVisible(cdrActive);
      });
    }

    function drawCdrOverlay(){
      if (!cdrOverlay || !main) return;
      resizeCdrOverlay();
      const ctx = cdrOverlay.getContext('2d');
      if (!ctx) return;
      const rect = main.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return;
      const { displayWidth, displayHeight, offsetX, offsetY } = metrics;
      const toCanvas = (point) => ({
        x: offsetX + point.x * displayWidth,
        y: offsetY + point.y * displayHeight
      });

      if (cdrDiscPoints.length > 0) {
        drawPoint(ctx, toCanvas(cdrDiscPoints[0]), '#0088ff');
      }
      if (cdrDiscPoints.length == 2) {
        drawLine(ctx, toCanvas(cdrDiscPoints[0]), toCanvas(cdrDiscPoints[1]), '#0088ff', 4);
        drawPoint(ctx, toCanvas(cdrDiscPoints[1]), '#0088ff');
      }
      if (cdrCupPoints.length > 0) {
        drawPoint(ctx, toCanvas(cdrCupPoints[0]), '#00ff6a');
      }
      if (cdrCupPoints.length == 2) {
        drawLine(ctx, toCanvas(cdrCupPoints[0]), toCanvas(cdrCupPoints[1]), '#00ff6a', 4);
        drawPoint(ctx, toCanvas(cdrCupPoints[1]), '#00ff6a');
      }
    }

    function updateCdrValues(){
      if (cdrDiscPoints.length != 2 || cdrCupPoints.length != 2) {
        resetCdrValues();
        setCdrDoneEnabled(false);
        return;
      }
      const discA = cdrDiscPoints[0];
      const discB = cdrDiscPoints[1];
      const cupA = cdrCupPoints[0];
      const cupB = cdrCupPoints[1];
      const discLength = Math.hypot(discB.x - discA.x, discB.y - discA.y);
      if (!discLength) {
        resetCdrValues();
        return;
      }
      const cupLength = Math.hypot(cupB.x - cupA.x, cupB.y - cupA.y);
      const cdr = Math.min(1, Math.max(0, cupLength / discLength));
      const rdr = Math.min(1, Math.max(0, 1 - cdr));
      if (cdrValue) cdrValue.textContent = cdr.toFixed(2);
      if (rdrValue) rdrValue.textContent = rdr.toFixed(2);
      updateCdrStatus('Ready');
      showCdrBubble('CDR/RDR measurement ready. Click Done to insert into comments.', true);
      setCdrDoneEnabled(true);
    }

    function handleCdrClick(event){
      if (!cdrActive) return;
      if (isMouseDragging || isDragging || cdrDragging) return;
      const point = getPointOnImageFromEvent(event);
      if (!point) return;
      event.preventDefault();
      event.stopPropagation();

      const nearest = findNearestCdrPoint(point, 12);
      if (nearest) {
        updateCdrPoint(nearest.type, nearest.index, point);
        return;
      }

      if (cdrStep == 1) {
        cdrDiscPoints = [point];
        cdrCupPoints = [];
        updateCdrStatus('Active');
        showCdrBubble('Step 1 of 2: click second point for disc diameter line.', true);
        cdrStep = 2;
        scheduleCdrDraw();
        return;
      }
      if (cdrStep == 2) {
        cdrDiscPoints = [cdrDiscPoints[0], point];
        cdrCupPoints = [];
        updateCdrStatus('Active');
        showCdrBubble('Step 2 of 2: click first point for cup segment (on disc line).', true);
        cdrStep = 3;
        scheduleCdrDraw();
        return;
      }
      if (cdrStep == 3) {
        const projected = projectPointToLine(point, cdrDiscPoints[0], cdrDiscPoints[1]);
        cdrCupPoints = [{ x: projected.x, y: projected.y }];
        updateCdrStatus('Active');
        showCdrBubble('Step 2 of 2: click second point for cup segment.', true);
        cdrStep = 4;
        scheduleCdrDraw();
        return;
      }
      if (cdrStep == 4) {
        const projected = projectPointToLine(point, cdrDiscPoints[0], cdrDiscPoints[1]);
        cdrCupPoints = [cdrCupPoints[0], { x: projected.x, y: projected.y }];
        cdrStep = 5;
        scheduleCdrDraw();
        updateCdrValues();
      }
    }

    function handleCdrPointerDown(event){
      if (!cdrActive) return;
      const point = getPointOnImageFromEvent(event);
      if (!point) return;
      const nearest = findNearestCdrPoint(point, 12);
      if (!nearest) return;
      cdrDragging = true;
      cdrDragTarget = nearest;
      updateCdrPoint(nearest.type, nearest.index, point);
      if (event.pointerId != null && main && main.setPointerCapture) {
        try { main.setPointerCapture(event.pointerId); } catch(_) {}
      }
      event.preventDefault();
      event.stopPropagation();
    }

    function handleCdrPointerMove(event){
      if (!cdrActive || !cdrDragging || !cdrDragTarget) return;
      const point = getPointOnImageFromEvent(event);
      if (!point) return;
      updateCdrPoint(cdrDragTarget.type, cdrDragTarget.index, point);
      event.preventDefault();
      event.stopPropagation();
    }

    function handleCdrPointerUp(event){
      if (!cdrActive || !cdrDragging) return;
      cdrDragging = false;
      cdrDragTarget = null;
      if (event.pointerId != null && main && main.releasePointerCapture) {
        try { main.releasePointerCapture(event.pointerId); } catch(_) {}
      }
      event.preventDefault();
      event.stopPropagation();
    }

    function adjustImagePan(stepX, stepY){
      if (isPanLocked()) {
        return;
      }
      const { minX, maxX, minY, maxY } = getPanRangePx(currentZoom);
      const nextX = clamp(imgPanX + stepX * IMG_PAN_STEP, minX, maxX);
      const nextY = clamp(imgPanY + stepY * IMG_PAN_STEP, minY, maxY);
      if (Math.abs(nextX - imgPanX) < 0.01 && Math.abs(nextY - imgPanY) < 0.01) return;
      imgPanX = nextX;
      imgPanY = nextY;
      applyImagePan();
      if (loupeEnabled) {
        updateLoupeAssets();
        if (lastPointerPos) updateLoupePosition(lastPointerPos);
      }
      updateZoomDisplay();
      saveViewerSettingsToStorage();
    }

    function resetImagePan(){
      imgPanX = 0;
      imgPanY = 0;
      currentZoom = 100;
      applyImagePan();
      updateZoomDisplay();
      if (loupeEnabled && lastPointerPos) updateLoupePosition(lastPointerPos);
    }

    function updateLoupeAssets(){
      if (!loupe || !mainImg || !loupeEnabled) return;
      loupe.style.backgroundImage = 'none';
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return;
      const { displayWidth, displayHeight } = metrics;
      if (displayWidth > 0 && displayHeight > 0) {
        const sizeX = displayWidth * loupeZoom;
        const sizeY = displayHeight * loupeZoom;
        loupe.style.backgroundSize = `${sizeX}px ${sizeY}px`;
      }
    }

    function getLoupeBaseCanvas(){
      if (!loupe) return null;
      let canvas = loupe.querySelector('canvas.imggr-loupe-base');
      if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.className = 'imggr-loupe-base';
        canvas.style.position = 'absolute';
        canvas.style.inset = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.borderRadius = 'inherit';
        canvas.style.pointerEvents = 'none';
        loupe.prepend(canvas);
      }
      return canvas;
    }

    function clearLoupeBase(){
      const canvas = getLoupeBaseCanvas();
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width || 0, canvas.height || 0);
    }

    function renderLoupeBase(imageX, imageY, displayWidth, displayHeight){
      if (!loupe || !mainImg || !loupeEnabled) return;
      const canvas = getLoupeBaseCanvas();
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const dpr = window.devicePixelRatio || 1;
      const lw = Math.max(1, loupe.clientWidth || 1);
      const lh = Math.max(1, loupe.clientHeight || 1);
      const cw = Math.max(1, Math.round(lw * dpr));
      const ch = Math.max(1, Math.round(lh * dpr));
      if (canvas.width !== cw || canvas.height !== ch) {
        canvas.width = cw;
        canvas.height = ch;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, lw, lh);

      const natW = mainImg.naturalWidth || 0;
      const natH = mainImg.naturalHeight || 0;
      if (!natW || !natH || !displayWidth || !displayHeight) return;

      const centerNatX = (imageX / displayWidth) * natW;
      const centerNatY = (imageY / displayHeight) * natH;
      const srcW = (lw / Math.max(loupeZoom, 1e-6)) * (natW / displayWidth);
      const srcH = (lh / Math.max(loupeZoom, 1e-6)) * (natH / displayHeight);
      const sx = clamp(centerNatX - (srcW / 2), 0, Math.max(0, natW - srcW));
      const sy = clamp(centerNatY - (srcH / 2), 0, Math.max(0, natH - srcH));

      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      try {
        ctx.drawImage(mainImg, sx, sy, srcW, srcH, 0, 0, lw, lh);
      } catch(_) {}
    }

    function setLoupeEnabled(flag){
      if (!loupe) return;
      loupeEnabled = !!flag;
      if (loupeToggle) {
        loupeToggle.setAttribute('aria-pressed', loupeEnabled ? 'true' : 'false');
        loupeToggle.classList.toggle('active', loupeEnabled);
      }
      if (!loupeEnabled) {
        loupe.classList.remove('is-active');
        clearLoupeBase();
        return;
      }
      applyLoupeDimensions();
      updateLoupeAssets();
      if (lastPointerPos) {
        updateLoupePosition(lastPointerPos);
      }
    }

    function toggleLoupe() {
      setLoupeEnabled(!loupeEnabled);
      saveViewerSettingsToStorage({ immediate: true });
    }

    function turnLoupeOff() {
      setLoupeEnabled(false);
      saveViewerSettingsToStorage({ immediate: true });
    }

    function updateLoupePosition(e){
      if (!loupeEnabled || !loupe || !main || !e) return;
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return;
      const { displayWidth, displayHeight, offsetX, offsetY } = metrics;
      const containerRect = main.getBoundingClientRect();
      if (!containerRect.width || !containerRect.height || !displayWidth || !displayHeight) return;
      const pointerXRaw = e.clientX - containerRect.left;
      const pointerYRaw = e.clientY - containerRect.top;
      const constrainedX = clamp(pointerXRaw, 0, containerRect.width);
      const constrainedY = clamp(pointerYRaw, 0, containerRect.height);
      loupe.style.left = `${e.clientX}px`;
      loupe.style.top = `${e.clientY}px`;

      const imageX = clamp(constrainedX - offsetX, 0, displayWidth);
      const imageY = clamp(constrainedY - offsetY, 0, displayHeight);
      const loupeW = loupe.clientWidth || 0;
      const loupeH = loupe.clientHeight || 0;
      const bgPosX = (loupeW / 2) - (imageX * loupeZoom);
      const bgPosY = (loupeH / 2) - (imageY * loupeZoom);
      loupe.style.backgroundPosition = `${bgPosX}px ${bgPosY}px`;
      // Expose exact loupe mapping for overlay renderers (e.g., ROI overlay in feature geometry editor).
      loupe.dataset.imgX = String(imageX);
      loupe.dataset.imgY = String(imageY);
      loupe.dataset.imgW = String(displayWidth);
      loupe.dataset.imgH = String(displayHeight);
      loupe.dataset.imgZoom = String(loupeZoom);
      renderLoupeBase(imageX, imageY, displayWidth, displayHeight);
      loupe.classList.add('is-active');
    }

    function handlePointerLeave(){
      lastPointerPos = null;
      if (!loupeEnabled || !loupe) return;
      loupe.classList.remove('is-active');
      clearLoupeBase();
    }

    function adjustLoupeSize(stepDir){
      if (!loupe) return;
      const next = clamp(loupeSize + (stepDir * LOUPE_SIZE_STEP), LOUPE_SIZE_MIN, LOUPE_SIZE_MAX);
      if (Math.abs(next - loupeSize) < 1) {
        return;
      }
      loupeSize = next;
      applyLoupeDimensions();
      if (loupeEnabled) {
        updateLoupeAssets();
        if (lastPointerPos) updateLoupePosition(lastPointerPos);
      }
      writeLoupePrefs({ size: loupeSize, zoom: loupeZoom });
    }

    if (cdrToggle) {
      cdrToggle.addEventListener('click', () => {
        setCdrActive(!cdrActive);
      });
    }
    if (cdrClear) {
      cdrClear.addEventListener('click', () => {
        resetCdrForRedraw();
      });
    }

    if (cdrDone) {
      cdrDone.addEventListener('click', () => {
        const tag = buildCdrTag();
        if (!tag) {
          updateCdrStatus('Active');
          showCdrBubble('Complete CDR/RDR steps first.', false);
          return;
        }
        const target = selectCommentTarget();
        if (!target) {
          setCdrActive(false);
          showCdrBubble('No comments field found to store CDR/RDR text.', false);
          return;
        }
        const nextValue = upsertCdrTag(target.value || '', tag);
        target.value = nextValue;
        target.dispatchEvent(new Event('input', { bubbles: true }));
        target.dispatchEvent(new Event('change', { bubbles: true }));
        setCdrActive(false);
        showCdrBubble('CDR/RDR added to comments.', false);
      });
    }

    function adjustLoupeZoom(stepDir){
      if (!loupe) return;
      const next = clamp(parseFloat((loupeZoom + (stepDir * LOUPE_ZOOM_STEP)).toFixed(2)), LOUPE_ZOOM_MIN, LOUPE_ZOOM_MAX);
      if (Math.abs(next - loupeZoom) < 0.01) {
        return;
      }
      loupeZoom = next;
      if (loupeEnabled) {
        updateLoupeAssets();
        if (lastPointerPos) updateLoupePosition(lastPointerPos);
      }
      writeLoupePrefs({ size: loupeSize, zoom: loupeZoom });
    }

    function resetLoupe(){
      // Reset loupe values to defaults but don't disable it
      loupeSize = DEFAULT_LOUPE_SIZE;
      loupeZoom = DEFAULT_LOUPE_ZOOM;
      lastPointerPos = null;
      applyLoupeDimensions();
      if (loupeEnabled) updateLoupeAssets();
      // If loupe is currently enabled, update it with new values
      if (loupeEnabled && lastPointerPos) {
        updateLoupePosition(lastPointerPos);
      }
      resetImagePan();
    }

    loupeToggle?.addEventListener('click', () => {
      activeRoot = root;
      toggleLoupe();
      loupeToggle.blur();
    });
    
    // Preset button handlers
    const presetButtons = card ? card.querySelectorAll('.imggr-preset-btn') : [];
    presetButtons.forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const presetNum = parseInt(e.target.dataset.preset);
        const presets = await loadViewerPresets();
        const preset = presets[presetNum];
        
        if (preset) {
          applyPreset(preset);
          // Visual feedback
          e.target.classList.add('btn-success');
          setTimeout(() => e.target.classList.remove('btn-success'), 500);
        }
      });
    });
    
    // Save preset button handler
    const savePresetBtn = card ? card.querySelector('.imggr-save-preset') : null;
    if (savePresetBtn) {
      savePresetBtn.addEventListener('click', () => {
        updatePresetModal();
      });
    }
    
    // Add event listener to modal show event to update preset slots
    const modal = document.getElementById(presetModalId);
    if (modal) {
      // Bootstrap modals must not remain inside the transformed/clipped viewer
      // carousel; moving them to body also mirrors the older viewer behavior.
      if (modal.parentElement !== document.body) document.body.appendChild(modal);
      modal.addEventListener('show.bs.modal', () => {
        updatePresetModal();
      });
      
      // Fix accessibility issue by ensuring focus is removed when modal is hidden
      modal.addEventListener('hide.bs.modal', () => {
        // Remove focus from any focused element within the modal before it's hidden
        const activeElement = document.activeElement;
        if (activeElement && modal.contains(activeElement)) {
          activeElement.blur();
        }
      });
    }

    main.addEventListener('pointerenter', (e) => {
      lastPointerPos = { clientX: e.clientX, clientY: e.clientY };
      if (!loupeEnabled) return;
      updateLoupeAssets();
      updateLoupePosition(lastPointerPos);
    });
    main.addEventListener('pointermove', (e) => {
      lastPointerPos = { clientX: e.clientX, clientY: e.clientY };
      if (!loupeEnabled) return;
      updateLoupePosition(lastPointerPos);
    });
    main.addEventListener('pointerleave', handlePointerLeave);
    
    // Touch/gesture event handlers
    function getTouchDistance(touches) {
      if (!touches || touches.length < 2) return 0;
      const dx = touches[0].clientX - touches[1].clientX;
      const dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }
    
    function handleTouchStart(e) {
      if (cdrActive) {
        return;
      }
      // The annotation editor locks one-finger panning while a drawing tool is
      // active so a finger draws; two fingers always pan and pinch-zoom, and the
      // editor reads the multi-touch flag to keep the stroke out of the gesture.
      root.dataset.imggrMultiTouch = e.touches.length >= 2 ? 'true' : 'false';
      if (isPanLocked() && e.touches.length === 1) {
        return;
      }
      if (e.touches.length === 1) {
        // Single touch - prepare for drag
        isDragging = true;
        dragStartX = e.touches[0].clientX;
        dragStartY = e.touches[0].clientY;
        touchStartPanX = imgPanX;
        touchStartPanY = imgPanY;
      } else if (e.touches.length === 2) {
        // Two touches - prepare for pinch zoom
        isDragging = false;
        touchStartDistance = getTouchDistance(e.touches);
        touchStartZoom = currentZoom;
      }
      e.preventDefault();
    }
    
    function handleTouchMove(e) {
      if (cdrActive) {
        return;
      }
      if (e.touches.length >= 2) root.dataset.imggrMultiTouch = 'true';
      if (isPanLocked() && e.touches.length === 1) {
        return;
      }
      if (e.touches.length === 1 && isDragging) {
        // Single touch drag - pan the image
        const deltaX = e.touches[0].clientX - dragStartX;
        const deltaY = e.touches[0].clientY - dragStartY;
        const { minX, maxX, minY, maxY } = getPanRangePx(currentZoom);
        imgPanX = clamp(touchStartPanX + deltaX, minX, maxX);
        imgPanY = clamp(touchStartPanY + deltaY, minY, maxY);
        
        applyImagePan();
        updateZoomDisplay();
        // Save settings to localStorage for rapid loading
        saveViewerSettingsToStorage();
      } else if (e.touches.length === 2) {
        // Two touches - pinch zoom
        const currentDistance = getTouchDistance(e.touches);
        if (touchStartDistance > 0) {
          const scale = currentDistance / touchStartDistance;
          const newZoom = clamp(touchStartZoom * scale, ZOOM_MIN, ZOOM_MAX);
          setZoomLevel(newZoom);
        }
      }
      e.preventDefault();
    }
    
    function handleTouchEnd(e) {
      isDragging = false;
      touchStartDistance = 0;
      if (!e.touches || e.touches.length === 0) root.dataset.imggrMultiTouch = 'false';
      if (isLiteMode) {
        saveViewerSettingsToStorage();
      }
      e.preventDefault();
    }
    
    // Add touch event listeners
    main.addEventListener('touchstart', handleTouchStart, { passive: false });
    main.addEventListener('touchmove', handleTouchMove, { passive: false });
    main.addEventListener('touchend', handleTouchEnd, { passive: false });
    main.addEventListener('touchcancel', handleTouchEnd, { passive: false });
    
    // Mouse wheel zoom for desktop
    main.addEventListener('wheel', (e) => {
      if (cdrActive) {
        return;
      }
      if (isPanLocked()) {
        return;
      }
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
        setZoomLevel(currentZoom + delta);
      }
    }, { passive: false });
    
    // Mouse drag panning for desktop
    function handleMouseDown(e) {
      // Only enable mouse panning when left mouse button is pressed and loupe is not active
      if (cdrActive) {
        return;
      }
      if (isPanLocked()) {
        return;
      }
      if (e.button === 0 && !loupeEnabled) {
        isMouseDragging = true;
        mouseDragStartX = e.clientX;
        mouseDragStartY = e.clientY;
        mouseDragStartPanX = imgPanX;
        mouseDragStartPanY = imgPanY;
        main.style.cursor = 'grabbing';
        e.preventDefault();
      }
    }
    
    function handleMouseMove(e) {
      if (cdrActive) {
        return;
      }
      if (isPanLocked()) {
        return;
      }
      if (isMouseDragging) {
        const deltaX = e.clientX - mouseDragStartX;
        const deltaY = e.clientY - mouseDragStartY;
        const { minX, maxX, minY, maxY } = getPanRangePx(currentZoom);
        imgPanX = clamp(mouseDragStartPanX + deltaX, minX, maxX);
        imgPanY = clamp(mouseDragStartPanY + deltaY, minY, maxY);
        
        applyImagePan();
        updateZoomDisplay();
        // Save settings to localStorage for rapid loading
        saveViewerSettingsToStorage();
        e.preventDefault();
      }
    }
    
    function handleMouseUp(e) {
      if (isMouseDragging) {
        isMouseDragging = false;
        main.style.cursor = '';
        if (isLiteMode) {
          saveViewerSettingsToStorage();
        }
        e.preventDefault();
      }
    }
    
    // Add mouse event listeners
    main.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    
    // Handle case when mouse leaves the window
    window.addEventListener('blur', () => {
      if (isMouseDragging) {
        isMouseDragging = false;
        main.style.cursor = '';
      }
    });
    window.addEventListener('resize', () => {
      updateViewportSize();
      clampPanToBounds();
      applyImagePan();
      updateLoupeAssets();
      if (loupeEnabled && lastPointerPos) updateLoupePosition(lastPointerPos);
      updateZoomDisplay();
      if (cdrActive) {
        positionCdrBubble();
      }
    });
    
    // Save settings to localStorage when page is unloaded for rapid loading next time
    const saveSettingsOnUnload = () => {
      saveViewerSettingsToStorage({ immediate: true });
    };
    
    window.addEventListener('beforeunload', saveSettingsOnUnload);
    window.addEventListener('pagehide', saveSettingsOnUnload);
    function updateZoomDisplay() {
      const metrics = getDisplayedImageMetrics();
      if (!metrics || !card) return;
      
      const zoomInfo = card.querySelector('.imggr-zoom-level');
      const dimInfo = card.querySelector('.imggr-display-dim');
      const natDimInfo = card.querySelector('.imggr-natural-dim');
      const zoomSlider = card.querySelector('.imggr-zoom-slider');
      
      const hasNatural = Boolean(metrics.natW && metrics.natH);
      // Rendered size comes from the live bounding box, which already includes
      // the CSS transform scale, so it matches what is actually on screen.
      const renderedWidth = Math.round(metrics.displayWidth);
      const renderedHeight = Math.round(metrics.displayHeight);
      const nativeScale = hasNatural && renderedWidth ? Math.round((renderedWidth / metrics.natW) * 100) : null;

      if (zoomInfo) {
        zoomInfo.textContent = nativeScale !== null
          ? `${currentZoom}% (${nativeScale}% of original)`
          : `${currentZoom}%`;
      }

      if (dimInfo && hasNatural && renderedWidth && renderedHeight) {
        dimInfo.textContent = `${renderedWidth}×${renderedHeight}`;
      }

      if (natDimInfo && metrics.natW && metrics.natH) {
        natDimInfo.textContent = `${metrics.natW}×${metrics.natH}`;
      }
      
      if (zoomSlider) {
        zoomSlider.value = currentZoom;
      }
      updateZoomControlLocks();
    }

    // Zoom/pan are restored per image UUID so repeated partial renders of the
    // same image do not reset the viewer.

    updateViewportSize();
    applyImagePan();
    applyLoupeDimensions();
    updateZoomDisplay();
    
    // Get zoom controls
    const zoomSlider = card ? card.querySelector('.imggr-zoom-slider') : null;
    const zoomFitBtn = card ? card.querySelector('.imggr-zoom-fit') : null;
    
    function setZoomLevel(zoomPercent) {
      if (isPanLocked()) {
        updateZoomControlLocks();
        return;
      }
      currentZoom = clamp(zoomPercent, ZOOM_MIN, ZOOM_MAX);
      clampPanToBounds();
      setCdrOverlayVisible(false);
      scheduleCdrRedrawAfterIdle();
      applyImagePan();
      updateZoomDisplay();
      if (loupeEnabled) {
        updateLoupeAssets();
        if (lastPointerPos) updateLoupePosition(lastPointerPos);
      }
      // Save settings to localStorage for rapid loading
      saveViewerSettingsToStorage();
    }
    
    function fitToContainer() {
      // Set zoom to 100% to fit the image to its container
      setZoomLevel(100);
    }

    function setImage({ imageUuid, mediaUrl, alt }) {
      if (!imageUuid || !mediaUrl) return;
      saveViewerSettingsToStorage({ immediate: true });
      uuid = imageUuid;
      root.dataset.encId = imageUuid;
      const saved = readViewerZoomState(imageUuid);
      currentZoom = saved?.zoom ?? 100;
      imgPanX = saved?.panX ?? 0;
      imgPanY = saved?.panY ?? 0;
      if (alt) mainImg.alt = alt;
      mainImg.src = mediaUrl;
      fetchAndHydrateMetadata();
    }

    function setPanPercent(nextPanX, nextPanY) {
      imgPanX = Number(nextPanX) || 0;
      imgPanY = Number(nextPanY) || 0;
      clampPanToBounds();
      applyImagePan();
      updateZoomDisplay();
      if (loupeEnabled) {
        updateLoupeAssets();
        if (lastPointerPos) updateLoupePosition(lastPointerPos);
      }
      saveViewerSettingsToStorage();
    }
    
    // The saveSettingsOnUnload function is already defined above
    
    // Zoom slider event
    zoomSlider?.addEventListener('input', (e) => {
      if (isPanLocked()) {
        updateZoomControlLocks();
        return;
      }
      setZoomLevel(parseFloat(e.target.value));
    });
    
    // Fit button event
    zoomFitBtn?.addEventListener('click', () => {
      if (isPanLocked()) {
        updateZoomControlLocks();
        return;
      }
      fitToContainer();
    });
    
    viewerStates.set(root, {
      toggleLoupe,
      turnLoupeOff,
      setLoupeEnabled,
      adjustLoupeSize,
      adjustLoupeZoom,
      adjustImagePan,
      setPanPercent,
      resetLoupe,
      resetImagePan,
      setZoomLevel,
      fitToContainer,
      refreshViewportSize,
      setImage,
      hydrateMetadata: fetchAndHydrateMetadata,
      getCurrentZoom: () => currentZoom,
      getCurrentLoupeEnabled: () => loupeEnabled, // Expose current loupe state as getter
      applyPreset: async (presetNum) => {
        const presets = await loadViewerPresets();
        const preset = presets[presetNum];
        if (preset) {
          applyPreset(preset);
        }
      },
      isCdrActive: () => cdrActive,
      isPanLocked,
      refreshLockState: () => {
        updateZoomControlLocks();
      },
    });
    root.__imggrState = viewerStates.get(root);

    const activate = () => { activeRoot = root; };
    main.addEventListener('click', activate);
    main.addEventListener('mouseenter', activate);
    root.addEventListener('mouseenter', activate);
  }

  function initAll(root){
    if (root) { initGradingViewer(root); return; }
    document.querySelectorAll('.imggr-viewer-root').forEach(initGradingViewer);
  }
  document.addEventListener('DOMContentLoaded', () => { initAll(); });
  if (document.readyState !== 'loading') { try { initAll(); } catch(_) {} }
  // Expose a helper for late-loaded partials
  try { window.initImggrViewers = initAll; } catch(_) {}
  // Mark as loaded so partial can avoid double-loading
  try { window.__imggrViewerLoaded = true; } catch(_) {}
})();
