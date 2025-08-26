// static/js/lightbox.js
(function () {
  let overlay, contentWrap, titleBar, closeBtn, prevBtn, nextBtn, frame, items, idx;
  let zoomInBtn, zoomOutBtn, resetBtn;           // PANZOOM: controls
  let panzoomInstance = null;                    // PANZOOM: instance

  function el(tag, cls) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function buildOverlay() {
    overlay = el('div', 'lb-overlay');
    const dialog = el('div', 'lb-dialog');

    titleBar = el('div', 'lb-title');
    closeBtn = el('button', 'lb-close btn btn-sm btn-light');
    closeBtn.type = 'button';
    closeBtn.innerText = '×';
    closeBtn.setAttribute('aria-label', 'Close');

    contentWrap = el('div', 'lb-content'); // holds img or iframe

    const nav = el('div', 'lb-nav');

    // PANZOOM: Zoom controls
    zoomInBtn = el('button', 'btn btn-sm btn-secondary btn-zoom');
    zoomOutBtn = el('button', 'btn btn-sm btn-secondary btn-zoom');
    resetBtn = el('button', 'btn btn-sm btn-outline-secondary btn-zoom');
    zoomInBtn.type = zoomOutBtn.type = resetBtn.type = 'button';
    zoomInBtn.textContent = '+';
    zoomOutBtn.textContent = '−';
    resetBtn.textContent = 'Reset';

    prevBtn = el('button', 'btn btn-sm btn-secondary me-2');
    nextBtn = el('button', 'btn btn-sm btn-secondary');
    prevBtn.type = nextBtn.type = 'button';
    prevBtn.innerText = 'Prev';
    nextBtn.innerText = 'Next';

    titleBar.appendChild(closeBtn);
    dialog.appendChild(titleBar);
    dialog.appendChild(contentWrap);

    // Place zoom controls before Prev/Next
    nav.appendChild(zoomInBtn);
    nav.appendChild(zoomOutBtn);
    nav.appendChild(resetBtn);
    nav.appendChild(prevBtn);
    nav.appendChild(nextBtn);

    dialog.appendChild(nav);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
    closeBtn.addEventListener('click', close);
    prevBtn.addEventListener('click', () => show(idx - 1));
    nextBtn.addEventListener('click', () => show(idx + 1));

    window.addEventListener('keydown', (e) => {
      if (!overlay.classList.contains('open')) return;
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowLeft') show(idx - 1);
      if (e.key === 'ArrowRight') show(idx + 1);
    });

    // PANZOOM: handlers (bound later when an image is active)
    zoomInBtn.addEventListener('click', () => {
      if (panzoomInstance) panzoomInstance.zoomIn();
    });
    zoomOutBtn.addEventListener('click', () => {
      if (panzoomInstance) panzoomInstance.zoomOut();
    });
    resetBtn.addEventListener('click', () => {
      if (panzoomInstance) panzoomInstance.reset();
    });
  }

  function destroyPanzoom() {
    if (panzoomInstance && panzoomInstance.destroy) {
      try { panzoomInstance.destroy(); } catch (_) {}
    }
    panzoomInstance = null;
  }

  function renderItem(item) {
    // Reset content & zoom state
    contentWrap.innerHTML = '';
    destroyPanzoom();

    const kind = item.dataset.kind;
    const src = item.dataset.src;
    const title = item.dataset.title || '';

    // Title (text left, close on right)
    titleBar.innerHTML = '';
    const t = el('div', 'lb-title-text');
    t.textContent = title;
    titleBar.appendChild(t);
    titleBar.appendChild(closeBtn);

    if (kind === 'image') {
      const img = new Image();
      img.className = 'lb-media img-panzoom';
      img.alt = title || 'image';
      img.onload = () => {
        // PANZOOM: initialize once image is loaded
        panzoomInstance = Panzoom(img, {
          contain: 'outside',  // allow pan outside container
          maxScale: 8,
          minScale: 1,
          step: 0.2
        });

        // Wheel to zoom (Ctrl/Cmd optional — here we zoom always)
        img.parentElement.addEventListener('wheel', function (e) {
          e.preventDefault();
          panzoomInstance.zoomWithWheel(e);
        }, { passive: false });

        // Double-click to toggle zoom 1 ↔ 2.5
        img.addEventListener('dblclick', (e) => {
          const targetScale = (panzoomInstance.getScale() > 1.01) ? 1 : 2.5;
          // zoomTo(scale, { animate, focal: {x,y} })
          panzoomInstance.zoomTo(targetScale, { animate: true, focal: e });
        });
      };
      img.src = src;
      contentWrap.appendChild(img);
    } else {
      // PDF or other → use iframe
      const iframe = el('iframe', 'lb-media');
      iframe.src = src;
      iframe.setAttribute('title', title || 'document');
      iframe.setAttribute('frameborder', '0');
      contentWrap.appendChild(iframe);
    }
  }

  function show(newIdx) {
    if (!items || !items.length) return;
    if (newIdx < 0) newIdx = items.length - 1;
    if (newIdx >= items.length) newIdx = 0;
    idx = newIdx;
    renderItem(items[idx]);
  }

  function openFromNodeList(nodeList) {
    items = Array.from(nodeList);
    if (!overlay) buildOverlay();
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    show(0);
  }

  function close() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
    destroyPanzoom();
    items = null;
  }

  // exposed: openEncounterLightbox(containerId)
  window.openEncounterLightbox = function (containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const nodeList = container.querySelectorAll('a[data-src]');
    if (!nodeList.length) return;
    openFromNodeList(nodeList);
  };
})();
