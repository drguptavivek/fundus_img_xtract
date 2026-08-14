(() => {
  const loaderScript = document.currentScript;
  const gradingViewerUrl = loaderScript?.dataset.gradingViewerUrl || '/static/js/grading-viewer.js?v=encounter-viewer-v1';
  let enginePromise = null;
  function ensureViewerEngine() {
    if (window.initImggrViewers) return Promise.resolve();
    if (enginePromise) return enginePromise;
    enginePromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = gradingViewerUrl;
      script.defer = true;
      script.addEventListener('load', resolve, { once: true });
      script.addEventListener('error', reject, { once: true });
      document.head.appendChild(script);
    });
    return enginePromise;
  }

  function selected(root) {
    return root.querySelector('[data-uev-select-image].active')?.dataset.uevSelectImage || null;
  }

  function selectImage(root, button) {
    const uuid = button.dataset.uevSelectImage;
    const mediaUrl = button.dataset.mediaUrl;
    if (!uuid || !mediaUrl) return;
    root.querySelectorAll('[data-uev-select-image]').forEach((item) => {
      item.classList.toggle('active', item.dataset.uevSelectImage === uuid);
    });
    root.querySelectorAll('[data-uev-image-panel]').forEach((panel) => {
      panel.classList.toggle('d-none', panel.dataset.uevImagePanel !== uuid);
    });
    const viewerRoot = root.querySelector('.imggr-viewer-root');
    if (viewerRoot) {
      viewerRoot.dataset.encId = uuid;
      const image = viewerRoot.querySelector('.imggr-main-img');
      if (image && !viewerRoot.__imggrState) {
        image.src = mediaUrl;
        image.alt = `Fundus image ${uuid}`;
      }
      if (window.initImggrViewers) window.initImggrViewers(viewerRoot);
      viewerRoot.__imggrState?.setImage({ imageUuid: uuid, mediaUrl, alt: `Fundus image ${uuid}` });
    }
  }

  function moveImage(root, offset) {
    const buttons = [...root.querySelectorAll('.uev-strip-thumb[data-uev-select-image]')];
    if (!buttons.length) return;
    const current = buttons.findIndex((button) => button.dataset.uevSelectImage === selected(root));
    const target = buttons[(Math.max(current, 0) + offset + buttons.length) % buttons.length];
    selectImage(root, target);
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  }

  function init(root) {
    if (!root || root.dataset.uevInitialized === 'true') return;
    root.dataset.uevInitialized = 'true';
    ensureViewerEngine().then(() => window.initImggrViewers?.(root.querySelector('.imggr-viewer-root'))).catch(() => {});
    const modalElement = root.querySelector('[data-uev-modal]');
    const card = root.querySelector('[data-uev-image-card]');
    const compactHost = root.querySelector('[data-uev-compact-viewer-host]');
    const fullHost = root.querySelector('[data-uev-full-viewer-host]');
    const modal = modalElement && window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(modalElement) : null;
    root.addEventListener('click', (event) => {
      const imageButton = event.target.closest('[data-uev-select-image]');
      if (imageButton) selectImage(root, imageButton);
      if (event.target.closest('[data-uev-previous-image]')) moveImage(root, -1);
      if (event.target.closest('[data-uev-next-image]')) moveImage(root, 1);
      if (event.target.closest('[data-uev-open-fullscreen]') && modal) modal.show();
    });
    root.addEventListener('keydown', (event) => {
      if (!modalElement?.classList.contains('show') || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      if (event.target.matches('input, textarea, select')) return;
      event.preventDefault();
      moveImage(root, event.key === 'ArrowLeft' ? -1 : 1);
    });
    modalElement?.addEventListener('show.bs.modal', () => { if (card && fullHost) fullHost.appendChild(card); });
    modalElement?.addEventListener('shown.bs.modal', () => {
      ensureViewerEngine().then(() => window.initImggrViewers?.(card?.querySelector('.imggr-viewer-root'))).catch(() => {});
      window.dispatchEvent(new Event('resize'));
    });
    modalElement?.addEventListener('hidden.bs.modal', () => { if (card && compactHost) compactHost.appendChild(card); });
    if (root.dataset.uevAutolaunch === 'true' && modal) modal.show();
  }

  function initAll(scope = document) {
    if (scope.matches?.('[data-uev-root]')) init(scope);
    scope.querySelectorAll?.('[data-uev-root]').forEach(init);
  }

  document.addEventListener('DOMContentLoaded', () => initAll());
  document.addEventListener('htmx:afterSwap', (event) => initAll(event.target));
  window.initEncounterViewers = initAll;
  window.loadEncounterViewer = async (url, host, fullscreen = true) => {
    const target = typeof host === 'string' ? document.querySelector(host) : host;
    if (!target) return;
    const separator = url.includes('?') ? '&' : '?';
    if (!window.htmx) throw new Error('HTMX is not available');
    await window.htmx.ajax('GET', `${url}${separator}presentation=${fullscreen ? 'fullscreen' : 'compact'}`, {
      target, swap: 'innerHTML',
    });
  };
})();
