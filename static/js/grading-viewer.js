(function(){
  // Active root for global key handling (Safari-friendly)
  let activeRoot = null;

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
  const FILTER_ORDER = ['none','redfree','greenboost','bluemono','gray','contrast'];
  const viewerStates = new WeakMap();
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
  const IMG_PAN_STEP = 5;
  const IMG_PAN_MIN = -600;
  const IMG_PAN_MAX = 600;
  const ZOOM_MIN = 40;
  const ZOOM_MAX = 500;
  const ZOOM_STEP = 20;

  function clamp(value, min, max){
    return Math.min(max, Math.max(min, value));
  }

  // Helper function to get CSRF token from the save button
  function getCsrfToken() {
    const csrfInput = document.querySelector('#imggr-preset-save-button input[name="csrf_token"]');
    return csrfInput ? csrfInput.value : null;
  }

  // API functions for viewer presets only

  async function fetchViewerPresets() {
    try {
      const response = await fetch('/api/viewer/presets');
      if (response.ok) {
        return await response.json();
      }
      return {};
    } catch(_) { return {}; }
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
        headers['X-CSRF-Token'] = csrfToken;
      }
      
      const response = await fetch(`/api/viewer/presets/${slotNumber}`, {
        method: 'DELETE',
        headers
      });
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

  // Bind once: global keyboard shortcuts routed to the active viewer
  if (!window.__imggrKeysBound) {
    window.__imggrKeysBound = true;
    window.addEventListener('keydown', (e) => {
      if (!activeRoot) return;
    const state = viewerStates.get(activeRoot);
    if (state && typeof state.isCdrActive === 'function' && state.isCdrActive()) return;
      const rawKey = e.key || '';
      const k = rawKey.toLowerCase();
      if (!k) return;
      const card = activeRoot.closest('.card');

      if (k === 'l' && state?.getCurrentLoupeEnabled?.()) {
        e.preventDefault();
        state?.toggleLoupe?.();
        return;
      }

      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (['input','textarea','select'].includes(tag)) return;

      const main = activeRoot.querySelector('.imggr-main');
      if (!main) return;

      const bright = card ? card.querySelector('.imggr-bright') : null;
      const contr = card ? card.querySelector('.imggr-contrast') : null;
      const resetBtn = card ? card.querySelector('.imggr-reset') : null;

      if (k === 'l') { e.preventDefault(); state?.toggleLoupe?.(); return; }
      if (rawKey === '[' || rawKey === '{') { e.preventDefault(); state?.adjustLoupeSize?.(-1); return; }
      if (rawKey === ']' || rawKey === '}') { e.preventDefault(); state?.adjustLoupeSize?.(+1); return; }
      if (rawKey === '-' || rawKey === '_') { e.preventDefault(); state?.adjustLoupeZoom?.(-1); return; }
      if (rawKey === '=' || rawKey === '+' ) { e.preventDefault(); state?.adjustLoupeZoom?.(+1); return; }
      if (k === 'w') { e.preventDefault(); state?.adjustImagePan?.(0, -1); return; }
      if (k === 's') { e.preventDefault(); state?.adjustImagePan?.(0, +1); return; }
      if (k === 'a') { e.preventDefault(); state?.adjustImagePan?.(-1, 0); return; }
      if (k === 'd') { e.preventDefault(); state?.adjustImagePan?.(+1, 0); return; }
      // Use Z and X keys for image zoom to avoid conflict with loupe zoom
      if (k === 'z') { e.preventDefault(); state?.setZoomLevel?.((state.currentZoom || 100) + ZOOM_STEP); return; }
      if (k === 'x') { e.preventDefault(); state?.setZoomLevel?.((state.currentZoom || 100) - ZOOM_STEP); return; }
      if (k === '0') { e.preventDefault(); state?.setZoomLevel?.(100); return; }
      if (k === 'home') { e.preventDefault(); state?.fitToContainer?.(); return; }

      if (rawKey === '<' || rawKey === ',') { e.preventDefault(); adjustRangeInput(bright, -1); return; }
      if (rawKey === '>' || rawKey === '.') { e.preventDefault(); adjustRangeInput(bright, +1); return; }
      if (rawKey === ';' || rawKey === ':') { e.preventDefault(); adjustRangeInput(contr, -1); return; }
      if (rawKey === '\'' || rawKey === '"') { e.preventDefault(); adjustRangeInput(contr, +1); return; }
      if (rawKey === '/' || rawKey === '?') {
        e.preventDefault();
        resetBtn?.click();
        // Reset loupe values but don't disable it
        state?.resetLoupe?.();
        return;
      }

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
      if (['r','g','b','y','h','c','n'].includes(k)) {
        e.preventDefault();
        if (k === 'r') selectFilter(activeRoot, 'redfree');
        else if (k === 'g') selectFilter(activeRoot, 'greenboost');
        else if (k === 'b') selectFilter(activeRoot, 'bluemono');
        else if (k === 'y') selectFilter(activeRoot, 'gray');
        else if (k === 'h') selectFilter(activeRoot, 'contrast');
        else selectFilter(activeRoot, 'none');
      }
    }, { capture: true });
  }

  function initGradingViewer(root){
    const main = root.querySelector('.imggr-main');
    const mainImg = root.querySelector('.imggr-main-img');
    const fullBtn = root.querySelector('.imggr-full');
    if (!main || !mainImg) return;
    
    // Get UUID from root element's data-enc-id attribute
    const uuid = root.dataset.encId;

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
    
    // Apply other saved settings
    if (savedSettings.zoom !== undefined) {
      currentZoom = clamp(savedSettings.zoom, ZOOM_MIN, ZOOM_MAX);
    }
    if (savedSettings.panX !== undefined) {
      imgPanX = clamp(savedSettings.panX, IMG_PAN_MIN, IMG_PAN_MAX);
    }
    if (savedSettings.panY !== undefined) {
      imgPanY = clamp(savedSettings.panY, IMG_PAN_MIN, IMG_PAN_MAX);
    }
    if (savedSettings.brightness !== undefined && bright) {
      bright.value = clamp(savedSettings.brightness, 0.5, 5);
    }
    if (savedSettings.contrast !== undefined && contr) {
      contr.value = clamp(savedSettings.contrast, 0.5, 5);
    }
    if (savedSettings.filter) {
      const filterInput = card.querySelector(`.imggr-filters input[value="${savedSettings.filter}"]`);
      if (filterInput) {
        filterInput.checked = true;
      }
    }
    
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
        pan_x: imgPanX,
        pan_y: imgPanY,
        loupe_enabled: loupeEnabled
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
      if (preset.brightness && bright) {
        bright.value = clamp(preset.brightness, 0.5, 5);
      }
      if (preset.contrast && contr) {
        contr.value = clamp(preset.contrast, 0.5, 5);
      }
      
      // Apply zoom and pan
      if (preset.zoom !== undefined) {
        currentZoom = clamp(preset.zoom, ZOOM_MIN, ZOOM_MAX);
      }
      if (preset.panX !== undefined) {
        imgPanX = clamp(preset.panX, IMG_PAN_MIN, IMG_PAN_MAX);
      }
      if (preset.panY !== undefined) {
        imgPanY = clamp(preset.panY, IMG_PAN_MIN, IMG_PAN_MAX);
      }
      
      // Apply loupe state
      if (preset.loupeEnabled !== undefined) {
        setLoupeEnabled(preset.loupeEnabled);
      }
      
      // Apply all changes
      applyFilter();
      applyImagePan();
      updateZoomDisplay();
      
      isApplyingSavedSettings = false;
    }
    
    async function updatePresetModal() {
      const modal = document.getElementById(`imggr-preset-modal-${uuid}`);
      if (!modal) return;
      
      const presets = await loadViewerPresets();
      const currentSettings = getCurrentSettings();
      
      // Update current settings display
      const filterDisplay = modal.querySelector('#current-filter-display');
      const brightnessDisplay = modal.querySelector('#current-brightness-display');
      const contrastDisplay = modal.querySelector('#current-contrast-display');
      const zoomDisplay = modal.querySelector('#current-zoom-display');
      
      if (filterDisplay) filterDisplay.textContent = currentSettings.filter || 'None';
      if (brightnessDisplay) brightnessDisplay.textContent = (currentSettings.brightness || 1).toFixed(2);
      if (contrastDisplay) contrastDisplay.textContent = (currentSettings.contrast || 1).toFixed(2);
      if (zoomDisplay) zoomDisplay.textContent = `${currentSettings.zoom || 100}%`;
      
      // Update preset slots
      const slotsContainer = modal.querySelector('#preset-slots');
      if (slotsContainer) {
        // Clear the slots container first
        slotsContainer.innerHTML = '';
        
        for (let i = 1; i <= 5; i++) {
          const preset = presets[i];
          const slotDiv = document.createElement('div');
          slotDiv.className = 'col-12 mb-2';
          
          let presetInfo = 'Empty';
          if (preset) {
            presetInfo = `
              <strong>Filter:</strong> ${preset.filter || 'None'} |
              <strong>Bright:</strong> ${(preset.brightness || 1).toFixed(1)} |
              <strong>Contrast:</strong> ${(preset.contrast || 1).toFixed(1)} |
              <strong>Zoom:</strong> ${preset.zoom || 100}%
            `;
          }
          
          slotDiv.innerHTML = `
            <div class="card">
              <div class="card-body p-2">
                <div class="d-flex justify-content-between align-items-center">
                  <div>
                    <strong>Preset ${i}:</strong>
                    <div class="small text-muted">${presetInfo}</div>
                  </div>
                  <div class="d-flex gap-2">
                    <button type="button" class="btn btn-sm btn-primary save-preset-slot" data-preset="${i}">
                      Save
                    </button>
                    ${preset ? `
                      <button type="button" class="btn btn-sm btn-success apply-preset-btn" data-preset="${i}">
                        Apply
                      </button>
                      <button type="button" class="btn btn-sm btn-danger delete-preset-btn" data-preset="${i}">
                        Delete
                      </button>
                    ` : ''}
                  </div>
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
            await saveViewerPreset(presetNum, currentSettings);
            
            // Update the modal to reflect the saved preset
            updatePresetModal();
            
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
              await deleteViewerPreset(presetNum);
              
              // Update the modal to reflect the deletion
              updatePresetModal();
              
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
    
    function saveViewerSettingsToStorage() {
      try {
        const settings = {
          zoom: currentZoom,
          panX: imgPanX,
          panY: imgPanY,
          brightness: bright ? parseFloat(bright.value) : 1,
          contrast: contr ? parseFloat(contr.value) : 1,
          filter: currentRadio(),
          loupeEnabled: loupeEnabled
        };
        window.localStorage?.setItem(VIEWER_SETTINGS_KEY, JSON.stringify(settings));
      } catch(e) {
        console.error('Error saving viewer settings to localStorage:', e);
      }
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
      const url = svgUrlFor(currentRadio());
      const b = parseFloat((bright && bright.value) || '1') || 1;
      const c = parseFloat((contr && contr.value) || '1') || 1;
      const chain = `${url}${url? ' ' : ''}brightness(${b}) contrast(${c})`;
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
      applyFilter();
      // Settings are saved by applyFilter()
    });
    // Initial apply without saving
    const url = svgUrlFor(currentRadio());
    const b = parseFloat((bright && bright.value) || '1') || 1;
    const c = parseFloat((contr && contr.value) || '1') || 1;
    const chain = `${url}${url? ' ' : ''}brightness(${b}) contrast(${c})`;
    try {
      mainImg.style.filter = chain;
      if (loupe) loupe.style.filter = chain;
    } catch(_) {}
    
    // Apply saved settings immediately if the image is already loaded
    function applySavedSettings() {
      isApplyingSavedSettings = true;
      
      // Apply saved filter
      if (savedSettings.filter) {
        const filterInput = card.querySelector(`.imggr-filters input[value="${savedSettings.filter}"]`);
        if (filterInput) {
          filterInput.checked = true;
        }
      }
      
      // Apply saved brightness and contrast
      if (savedSettings.brightness && bright) {
        bright.value = clamp(savedSettings.brightness, 0.5, 5);
      }
      if (savedSettings.contrast && contr) {
        contr.value = clamp(savedSettings.contrast, 0.5, 5);
      }
      
      // Apply the filter with the saved values
      applyFilter();
      
      // Mark initialization as complete so future changes will be saved
      isInitializing = false;
      isApplyingSavedSettings = false;
    }
    
    // Apply saved filter and brightness/contrast after image is loaded
    mainImg.addEventListener('load', () => {
      applySavedSettings();
      updateLoupeAssets();
      if (loupeEnabled && lastPointerPos) updateLoupePosition(lastPointerPos);
      updateZoomDisplay();
      if (cdrDiscPoints.length || cdrCupPoints.length || cdrActive) {
        resizeCdrOverlay();
        scheduleCdrDraw();
      }
    });
    
    // If image is already loaded, apply settings immediately
    if (mainImg.complete && mainImg.naturalWidth > 0) {
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

    function applyImagePan(){
      if (!mainImg) return;
      mainImg.style.transform = `translate(${imgPanX}%, ${imgPanY}%) scale(${currentZoom / 100})`;
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
      updateCdrStatus('Inactive');
      if (cdrClear) cdrClear.disabled = true;
    }

    function setViewerControlsLocked(flag){
      if (!card) return;
      const disabled = !!flag;
      card.classList.toggle('imggr-cdr-locked', disabled);
      const zoomSlider = card.querySelector('.imggr-zoom-slider');
      const zoomFitButton = card.querySelector('.imggr-zoom-fit');
      if (zoomSlider) zoomSlider.disabled = disabled;
      if (zoomFitButton) zoomFitButton.disabled = disabled;
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
        updateCdrStatus('Select disc line: click 2 points');
        if (cdrClear) cdrClear.disabled = false;
        setCdrDoneEnabled(cdrDiscPoints.length === 2 && cdrCupPoints.length === 2);
      } else {
        if (cdrPanel) cdrPanel.classList.remove('is-active');
        clearCdrState();
      }
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
        setCdrOverlayVisible(true);
      }, 1000);
    }

    function scheduleCdrDraw(){
      if (cdrDrawPending) return;
      cdrDrawPending = true;
      requestAnimationFrame(() => {
        cdrDrawPending = false;
        drawCdrOverlay();
        setCdrOverlayVisible(true);
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
      updateCdrStatus('Measurement ready');
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
        updateCdrStatus('Select disc line: click 2nd point');
        cdrStep = 2;
        scheduleCdrDraw();
        return;
      }
      if (cdrStep == 2) {
        cdrDiscPoints = [cdrDiscPoints[0], point];
        cdrCupPoints = [];
        updateCdrStatus('Select cup segment: click 1st point');
        cdrStep = 3;
        scheduleCdrDraw();
        return;
      }
      if (cdrStep == 3) {
        const projected = projectPointToLine(point, cdrDiscPoints[0], cdrDiscPoints[1]);
        cdrCupPoints = [{ x: projected.x, y: projected.y }];
        updateCdrStatus('Select cup segment: click 2nd point');
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
      const nextX = clamp(imgPanX + stepX * IMG_PAN_STEP, IMG_PAN_MIN, IMG_PAN_MAX);
      const nextY = clamp(imgPanY + stepY * IMG_PAN_STEP, IMG_PAN_MIN, IMG_PAN_MAX);
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
      if (!loupe || !mainImg) return;
      const src = mainImg.currentSrc || mainImg.src;
      if (src) loupe.style.backgroundImage = `url(${JSON.stringify(src)})`;
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return;
      const { displayWidth, displayHeight } = metrics;
      if (displayWidth > 0 && displayHeight > 0) {
        const sizeX = displayWidth * loupeZoom;
        const sizeY = displayHeight * loupeZoom;
        loupe.style.backgroundSize = `${sizeX}px ${sizeY}px`;
      }
    }

    function setLoupeEnabled(flag){
      if (!loupe || !loupeToggle) return;
      loupeEnabled = !!flag;
      loupeToggle.setAttribute('aria-pressed', loupeEnabled ? 'true' : 'false');
      loupeToggle.classList.toggle('active', loupeEnabled);
      if (!loupeEnabled) {
        loupe.classList.remove('is-active');
        return;
      }
      applyLoupeDimensions();
      updateLoupeAssets();
      if (lastPointerPos) {
        updateLoupePosition(lastPointerPos);
      }
    }

    function updateLoupePosition(e){
      if (!loupeEnabled || !loupe || !main || !e) return;
      const metrics = getDisplayedImageMetrics();
      if (!metrics) return;
      const { rect: mainRect, displayWidth, displayHeight, offsetX, offsetY } = metrics;
      if (!mainRect.width || !mainRect.height) return;
      const pointerXRaw = e.clientX - mainRect.left;
      const pointerYRaw = e.clientY - mainRect.top;
      const constrainedX = clamp(pointerXRaw, 0, mainRect.width);
      const constrainedY = clamp(pointerYRaw, 0, mainRect.height);
      loupe.style.left = `${e.clientX}px`;
      loupe.style.top = `${e.clientY}px`;

      const imgRect = mainImg.getBoundingClientRect();
      if (imgRect.width && imgRect.height) {
        const imageX = clamp(constrainedX - offsetX, 0, displayWidth);
        const imageY = clamp(constrainedY - offsetY, 0, displayHeight);
        const bgX = displayWidth > 0 ? (imageX / displayWidth) * 100 : 50;
        const bgY = displayHeight > 0 ? (imageY / displayHeight) * 100 : 50;
        loupe.style.backgroundPosition = `${bgX}% ${bgY}%`;
      }
      loupe.classList.add('is-active');
    }

    function handlePointerLeave(){
      lastPointerPos = null;
      if (!loupeEnabled || !loupe) return;
      loupe.classList.remove('is-active');
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
        clearCdrState();
        if (cdrActive) {
          if (cdrPanel) cdrPanel.classList.add('is-active');
          updateCdrStatus('Select disc line: click 2 points');
          cdrStep = 1;
          if (cdrClear) cdrClear.disabled = false;
        }
      });
    }

    if (cdrDone) {
      cdrDone.addEventListener('click', () => {
        const tag = buildCdrTag();
        if (!tag) {
          updateCdrStatus('Complete CDR steps first');
          return;
        }
        const target = selectCommentTarget();
        if (!target) {
          updateCdrStatus('No comment field found');
          return;
        }
        const nextValue = upsertCdrTag(target.value || '', tag);
        target.value = nextValue;
        target.dispatchEvent(new Event('input', { bubbles: true }));
        target.dispatchEvent(new Event('change', { bubbles: true }));
        updateCdrStatus('Added to comments');
        cdrActive = false;
        if (cdrToggle) {
          cdrToggle.setAttribute('aria-pressed', 'false');
          cdrToggle.classList.remove('active');
        }
        setViewerControlsLocked(false);
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
      updateLoupeAssets();
      // If loupe is currently enabled, update it with new values
      if (loupeEnabled && lastPointerPos) {
        updateLoupePosition(lastPointerPos);
      }
      resetImagePan();
    }

    loupeToggle?.addEventListener('click', () => {
      const newState = !loupeEnabled;
      setLoupeEnabled(newState);
      // Save loupe state to localStorage for rapid loading
      saveViewerSettingsToStorage();
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
    const modal = document.getElementById(`imggr-preset-modal-${uuid}`);
    if (modal) {
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
      if (e.touches.length === 1 && isDragging) {
        // Single touch drag - pan the image
        const deltaX = e.touches[0].clientX - dragStartX;
        const deltaY = e.touches[0].clientY - dragStartY;
        
        // Convert pixel movement to percentage-based pan
        const containerRect = main.getBoundingClientRect();
        const panStepX = (deltaX / containerRect.width) * 100;
        const panStepY = (deltaY / containerRect.height) * 100;
        
        imgPanX = clamp(touchStartPanX + panStepX, IMG_PAN_MIN, IMG_PAN_MAX);
        imgPanY = clamp(touchStartPanY + panStepY, IMG_PAN_MIN, IMG_PAN_MAX);
        
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
      if (isMouseDragging) {
        const deltaX = e.clientX - mouseDragStartX;
        const deltaY = e.clientY - mouseDragStartY;
        
        // Convert pixel movement to percentage-based pan
        const containerRect = main.getBoundingClientRect();
        const panStepX = (deltaX / containerRect.width) * 150; // Use same sensitivity as touch
        const panStepY = (deltaY / containerRect.height) * 150;
        
        imgPanX = clamp(mouseDragStartPanX + panStepX, IMG_PAN_MIN, IMG_PAN_MAX);
        imgPanY = clamp(mouseDragStartPanY + panStepY, IMG_PAN_MIN, IMG_PAN_MAX);
        
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
      updateLoupeAssets();
      if (loupeEnabled && lastPointerPos) updateLoupePosition(lastPointerPos);
      updateZoomDisplay();
    });
    
    // Save settings to localStorage when page is unloaded for rapid loading next time
    const saveSettingsOnUnload = () => {
      saveViewerSettingsToStorage();
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
      
      if (zoomInfo) {
        zoomInfo.textContent = `${currentZoom}%`;
      }
      
      if (dimInfo && metrics.natW && metrics.natH) {
        // Calculate actual display dimensions based on zoom level
        const mainDiv = main.querySelector('.imggr-main');
        if (mainDiv) {
          const containerRect = mainDiv.getBoundingClientRect();
          const aspectRatio = metrics.natW / metrics.natH;
          
          // Calculate the base display size (without zoom)
          let baseDisplayWidth, baseDisplayHeight;
          if (aspectRatio > 1) {
            // Landscape image
            baseDisplayWidth = containerRect.width;
            baseDisplayHeight = containerRect.width / aspectRatio;
          } else {
            // Portrait or square image
            baseDisplayHeight = containerRect.height;
            baseDisplayWidth = containerRect.height * aspectRatio;
          }
          
          // Apply zoom to get actual display dimensions
          const scaledWidth = Math.round(baseDisplayWidth * (currentZoom / 100));
          const scaledHeight = Math.round(baseDisplayHeight * (currentZoom / 100));
          dimInfo.textContent = `${scaledWidth}×${scaledHeight}`;
        }
      }
      
      if (natDimInfo && metrics.natW && metrics.natH) {
        natDimInfo.textContent = `${metrics.natW}×${metrics.natH}`;
      }
      
      if (zoomSlider) {
        zoomSlider.value = currentZoom;
      }
    }

    // Apply saved zoom and pan settings
    if (savedSettings.zoom) {
      currentZoom = clamp(savedSettings.zoom, ZOOM_MIN, ZOOM_MAX);
    }
    if (savedSettings.panX !== undefined) {
      imgPanX = clamp(savedSettings.panX, IMG_PAN_MIN, IMG_PAN_MAX);
    }
    if (savedSettings.panY !== undefined) {
      imgPanY = clamp(savedSettings.panY, IMG_PAN_MIN, IMG_PAN_MAX);
    }
    
    applyImagePan();
    applyLoupeDimensions();
    updateZoomDisplay();
    
    // Get zoom controls
    const zoomSlider = card ? card.querySelector('.imggr-zoom-slider') : null;
    const zoomFitBtn = card ? card.querySelector('.imggr-zoom-fit') : null;
    
    function setZoomLevel(zoomPercent) {
      currentZoom = clamp(zoomPercent, ZOOM_MIN, ZOOM_MAX);
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
    
    // The saveSettingsOnUnload function is already defined above
    
    // Zoom slider event
    zoomSlider?.addEventListener('input', (e) => {
      setZoomLevel(parseFloat(e.target.value));
    });
    
    // Fit button event
    zoomFitBtn?.addEventListener('click', () => {
      fitToContainer();
    });
    
    viewerStates.set(root, {
      toggleLoupe: () => {
        const currentState = loupeEnabled;
        setLoupeEnabled(!currentState);
      },
      adjustLoupeSize,
      adjustLoupeZoom,
      adjustImagePan,
      resetLoupe,
      resetImagePan,
      setZoomLevel,
      fitToContainer,
      currentZoom, // Expose current zoom level for keyboard shortcuts
      getCurrentLoupeEnabled: () => loupeEnabled, // Expose current loupe state as getter
      applyPreset: async (presetNum) => {
        const presets = await loadViewerPresets();
        const preset = presets[presetNum];
        if (preset) {
          applyPreset(preset);
        }
      },
      isCdrActive: () => cdrActive
    });

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
