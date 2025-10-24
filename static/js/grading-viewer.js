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
    try { (document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen)?.call(document); } catch(_) {}
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
      const rawKey = e.key || '';
      const k = rawKey.toLowerCase();
      if (!k) return;
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (['input','textarea','select'].includes(tag)) return;

      const main = activeRoot.querySelector('.imggr-main');
      if (!main) return;

      const card = activeRoot.closest('.card');
      const bright = card ? card.querySelector('.imggr-bright') : null;
      const contr = card ? card.querySelector('.imggr-contrast') : null;
      const resetBtn = card ? card.querySelector('.imggr-reset') : null;

      if (rawKey === '<' || rawKey === ',') { e.preventDefault(); adjustRangeInput(bright, -1); return; }
      if (rawKey === '>' || rawKey === '.') { e.preventDefault(); adjustRangeInput(bright, +1); return; }
      if (rawKey === ';' || rawKey === ':') { e.preventDefault(); adjustRangeInput(contr, -1); return; }
      if (rawKey === '\'' || rawKey === '"') { e.preventDefault(); adjustRangeInput(contr, +1); return; }
      if (rawKey === '/' || rawKey === '?') { e.preventDefault(); resetBtn?.click(); return; }

      if (k === 'f') { e.preventDefault(); isFullscreenFor(main) ? exitFullscreen() : requestFullscreen(main); return; }
      if (k === 'escape') { e.preventDefault(); exitFullscreen(); return; }
      if (k === 'arrowleft') { e.preventDefault(); cycleFilter(activeRoot, -1); return; }
      if (k === 'arrowright') { e.preventDefault(); cycleFilter(activeRoot, +1); return; }
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
    let loupeEnabled = false;
    let lastPointerPos = null;

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
    function applyFilter(){
      const url = svgUrlFor(currentRadio());
      const b = parseFloat((bright && bright.value) || '1') || 1;
      const c = parseFloat((contr && contr.value) || '1') || 1;
      const chain = `${url}${url? ' ' : ''}brightness(${b}) contrast(${c})`;
      try { mainImg.style.filter = chain; } catch(_) {}
    }
    rad && rad.forEach && rad.forEach(r => r.addEventListener('change', applyFilter));
    bright && bright.addEventListener('input', applyFilter);
    contr && contr.addEventListener('input', applyFilter);
    resetBtn && resetBtn.addEventListener('click', () => {
      if (bright) bright.value = '1';
      if (contr) contr.value = '1';
      const none = card && card.querySelector('.imggr-filters input[value="none"]');
      if (none) {
        none.checked = true;
        none.dispatchEvent(new Event('change', { bubbles: true }));
      }
      applyFilter();
    });
    // Initial
    applyFilter();

    function updateLoupeAssets(){
      if (!loupe || !mainImg) return;
      const src = mainImg.currentSrc || mainImg.src;
      if (src) loupe.style.backgroundImage = `url(${JSON.stringify(src)})`;
      const rect = mainImg.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        loupe.style.backgroundSize = `${rect.width * 2}px ${rect.height * 2}px`;
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
      updateLoupeAssets();
      if (lastPointerPos) {
        updateLoupePosition(lastPointerPos);
      }
    }

    function pointerWithinRect(coord, size){
      return Math.max(0, Math.min(size, coord));
    }

    function updateLoupePosition(e){
      if (!loupeEnabled || !loupe || !main || !e) return;
      const mainRect = main.getBoundingClientRect();
      if (!mainRect.width || !mainRect.height) return;
      const pointerX = pointerWithinRect(e.clientX - mainRect.left, mainRect.width);
      const pointerY = pointerWithinRect(e.clientY - mainRect.top, mainRect.height);
      loupe.style.left = `${pointerX}px`;
      loupe.style.top = `${pointerY}px`;

      const imgRect = mainImg.getBoundingClientRect();
      if (imgRect.width && imgRect.height) {
        const imgX = pointerWithinRect(e.clientX - imgRect.left, imgRect.width);
        const imgY = pointerWithinRect(e.clientY - imgRect.top, imgRect.height);
        const bgX = (imgX / imgRect.width) * 100;
        const bgY = (imgY / imgRect.height) * 100;
        loupe.style.backgroundPosition = `${bgX}% ${bgY}%`;
      }
      loupe.classList.add('is-active');
    }

    function handlePointerLeave(){
      lastPointerPos = null;
      if (!loupeEnabled || !loupe) return;
      loupe.classList.remove('is-active');
    }

    loupeToggle?.addEventListener('click', () => {
      setLoupeEnabled(!loupeEnabled);
    });

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
    window.addEventListener('resize', () => { if (loupeEnabled) updateLoupeAssets(); });
    mainImg.addEventListener('load', () => { if (loupeEnabled) updateLoupeAssets(); });

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
