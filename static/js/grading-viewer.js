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

  // Bind once: global keyboard shortcuts routed to the active viewer
  if (!window.__imggrKeysBound) {
    window.__imggrKeysBound = true;
    window.addEventListener('keydown', (e) => {
      if (!activeRoot) return;
      const k = (e.key||'').toLowerCase();
      if (!k) return;
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
      if (['input','textarea','select'].includes(tag)) return;

      const main = activeRoot.querySelector('.imggr-main');
      if (!main) return;

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
