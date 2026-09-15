/* Grader PWA shell behaviour: service worker + update prompt, screen wake lock
 * while a session is open, and the phone bottom-sheet / annotate mode over the
 * shared workbench markup. Grading logic lives in grading-workbench-session.js. */
(function () {
  const body = document.body;

  // ---- Service worker: app shell only; prompt to reload when a new build lands ----
  if ('serviceWorker' in navigator && body.dataset.swUrl) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
    navigator.serviceWorker.register(body.dataset.swUrl, {
      scope: body.dataset.swScope || '/grader/',
      updateViaCache: 'none',
    })
      .then(registration => {
        const offerUpdate = worker => {
          if (!navigator.serviceWorker.controller || !worker) return;
          const container = document.getElementById('flash-toasts');
          if (!container) return;
          const toast = document.createElement('div');
          toast.className = 'toast text-bg-info border-0 shadow-sm small';
          toast.setAttribute('role', 'status');
          toast.innerHTML = '<div class="d-flex align-items-center"><div class="toast-body py-1">A new version is ready.</div>'
            + '<button type="button" class="btn btn-sm btn-light ms-auto me-2" data-pwa-reload>Reload</button></div>';
          toast.querySelector('[data-pwa-reload]').addEventListener('click', () => worker.postMessage({ type: 'SKIP_WAITING' }));
          container.appendChild(toast);
          if (window.bootstrap?.Toast) window.bootstrap.Toast.getOrCreateInstance(toast, { autohide: false }).show();
        };
        if (registration.waiting) offerUpdate(registration.waiting);
        registration.addEventListener('updatefound', () => {
          const worker = registration.installing;
          worker?.addEventListener('statechange', () => {
            if (worker.state === 'installed') offerUpdate(registration.waiting || worker);
          });
        });
      })
      .catch(() => undefined);
  }

  // ---- Token auth affordances: sign out, add a passkey ----
  const auth = window.GraderAuth;
  document.querySelectorAll('[data-grader-signout]').forEach(link => {
    link.addEventListener('click', async event => {
      event.preventDefault();
      if (auth) await auth.logout();
      window.location.assign(link.getAttribute('href') || '/grader/login');
    });
  });
  const passkeyCard = document.querySelector('[data-passkey-enrol]');
  // Passkeys belong to a token sign-in; a web-session visit to /grader/ has no
  // token to bind one to, so the card stays hidden there.
  // Passkeys are per browser: the account may already hold one from Safari
  // that Chrome cannot use. "has_passkey" is therefore a local fact - set only
  // when a passkey was created or used in THIS browser - and the card is
  // offered until then, unless dismissed here.
  const DISMISS_KEY = 'grader.passkey_offer_dismissed';
  let dismissed = false;
  try { dismissed = localStorage.getItem(DISMISS_KEY) === '1'; } catch (_) {}
  if (passkeyCard && auth && auth.isSignedIn() && !dismissed) {
    auth.platformAuthenticatorAvailable().then(ok => {
      if (!ok || auth.read()?.has_passkey) return;
      passkeyCard.hidden = false;
      passkeyCard.querySelector('[data-passkey-enrol-dismiss]')?.addEventListener('click', () => {
        try { localStorage.setItem(DISMISS_KEY, '1'); } catch (_) {}
        passkeyCard.hidden = true;
      });
      passkeyCard.querySelector('[data-passkey-enrol-button]').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await auth.registerPasskey();
          passkeyCard.querySelector('[data-passkey-enrol-status]').textContent = 'Passkey added. You can use it to confirm your identity after a break.';
          button.hidden = true;
          passkeyCard.querySelector('[data-passkey-enrol-dismiss]')?.setAttribute('hidden', '');
          // The job is done: let the confirmation read, then take the card away.
          window.setTimeout(() => { passkeyCard.hidden = true; }, 2500);
        } catch (error) {
          passkeyCard.querySelector('[data-passkey-enrol-status]').textContent = error.message || 'Could not add a passkey.';
          button.disabled = false;
        }
      });
    });
  }

  // ---- Native install prompt (Chromium): surface the browser's own dialog ----
  const installButton = document.querySelector('[data-pwa-install]');
  if (installButton) {
    let deferredPrompt = null;
    window.addEventListener('beforeinstallprompt', event => {
      event.preventDefault();
      deferredPrompt = event;
      installButton.classList.remove('d-none');
    });
    installButton.addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      try { await deferredPrompt.userChoice; } catch (_) {}
      deferredPrompt = null;
      installButton.classList.add('d-none');
    });
    if (window.matchMedia('(display-mode: standalone)').matches || navigator.standalone) {
      document.querySelector('[data-install-help]')?.remove();
    }
  }

  const workbench = document.getElementById('grading-workbench');
  if (!workbench) return;

  // ---- Keep the screen (and the lease heartbeat) alive while grading ----
  let wakeLock = null;
  async function requestWakeLock() {
    if (!('wakeLock' in navigator) || document.hidden) return;
    try {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => { wakeLock = null; });
    } catch (_) { wakeLock = null; }
  }
  requestWakeLock();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !wakeLock) requestWakeLock();
  });

  // ---- Fit: the image box takes the image's own aspect ratio, not a square ----
  // A viewer that initialised before this ran (a cached first image) has
  // already sized itself square, so it is re-fitted straight away.
  workbench.querySelectorAll('.imggr-main').forEach(main => { main.dataset.fitMode = 'fill'; });
  workbench.querySelectorAll('.imggr-viewer-root').forEach(viewer => {
    window.requestAnimationFrame(() => viewer.__imggrState?.refreshViewportSize?.());
  });

  // ---- Phone layout: overlay chrome, three-height grade sheet, annotate mode ----
  // Landscape phones are wider than the tablet breakpoint but far shorter, so
  // "phone" is either dimension. grading-workbench.css uses the same query.
  const PHONE_QUERY = '(max-width: 767.98px), (max-height: 500px)';
  const phone = window.matchMedia(PHONE_QUERY);
  const panels = Array.from(workbench.querySelectorAll('[data-task-uuid]'));
  const TOOLBAR_HIDDEN_KEY = 'grader.toolbar_hidden';
  const SHEET_STATES = ['rail', 'peek', 'open'];

  function refreshViewer(panel) {
    const viewer = panel.querySelector('.imggr-viewer-root');
    window.requestAnimationFrame(() => viewer?.__imggrState?.refreshViewportSize?.());
  }

  function iconButton(className, icon, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.setAttribute('aria-label', label);
    button.title = label;
    button.innerHTML = `<i class="fa-solid ${icon}" aria-hidden="true"></i>`;
    return button;
  }

  function setupSheet(panel) {
    const card = panel.querySelector('.gwb-grade-card');
    const header = card?.querySelector('.card-header');
    if (!card || !header || card.querySelector('.gpwa-sheet-handle')) return;
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'gpwa-sheet-handle';
    handle.innerHTML = '<span class="gpwa-sheet-grip" aria-hidden="true"></span><span class="gpwa-sheet-label"></span>';
    const label = handle.querySelector('.gpwa-sheet-label');
    const minimise = iconButton('gpwa-sheet-minimise', 'fa-chevron-down', 'Minimise grade sheet');
    header.prepend(handle);
    header.append(minimise);

    const disease = panel.dataset.diseaseName || 'Grade';
    const chosenGrade = () => {
      const checked = panel.querySelector('[data-grade-option]:checked');
      return checked ? panel.querySelector(`label[for="${checked.id}"]`)?.textContent.trim() : '';
    };
    const updateLabel = () => {
      const grade = chosenGrade();
      label.innerHTML = '';
      label.append(`${disease}: `);
      const value = document.createElement(grade ? 'strong' : 'span');
      value.textContent = grade || 'choose a grade';
      label.append(value);
    };

    const current = () => card.dataset.sheetState || 'peek';
    const setState = state => {
      card.dataset.sheetState = state;
      card.classList.toggle('is-rail', state === 'rail');
      card.classList.toggle('is-peek', state === 'peek');
      handle.setAttribute('aria-expanded', state === 'rail' ? 'false' : 'true');
      handle.setAttribute('aria-label', state === 'open' ? 'Show fewer grading controls' : 'Show more grading controls');
      const rail = state === 'rail';
      minimise.querySelector('i').className = `fa-solid ${rail ? 'fa-chevron-up' : 'fa-chevron-down'}`;
      const minimiseLabel = rail ? 'Show grade sheet' : 'Minimise grade sheet';
      minimise.setAttribute('aria-label', minimiseLabel);
      minimise.title = minimiseLabel;
      updateLabel();
      refreshViewer(panel);
    };
    const step = delta => {
      const index = SHEET_STATES.indexOf(current());
      setState(SHEET_STATES[Math.min(SHEET_STATES.length - 1, Math.max(0, index + delta))]);
    };

    // Tap the handle: rail -> peek, peek <-> open. The chevron: anything -> rail, rail -> peek.
    let swiped = false;
    handle.addEventListener('click', () => {
      if (swiped) { swiped = false; return; }
      setState(current() === 'open' ? 'peek' : (current() === 'rail' ? 'peek' : 'open'));
    });
    minimise.addEventListener('click', () => setState(current() === 'rail' ? 'peek' : 'rail'));
    // Swipe the header up or down to step through the heights.
    let startY = null;
    header.addEventListener('pointerdown', event => { startY = event.clientY; swiped = false; });
    header.addEventListener('pointerup', event => {
      if (startY === null) return;
      const delta = event.clientY - startY;
      startY = null;
      if (Math.abs(delta) < 28) return;
      swiped = true;
      step(delta < 0 ? 1 : -1);
    });
    header.addEventListener('pointercancel', () => { startY = null; });

    panel.querySelectorAll('[data-grade-option]').forEach(option => {
      option.addEventListener('change', () => {
        updateLabel();
        // A grade that carries features opens the sheet so they are not missed.
        window.requestAnimationFrame(() => {
          const fieldset = panel.querySelector('[data-feature-fieldset]');
          if (fieldset && !fieldset.classList.contains('d-none')) setState('open');
        });
      });
    });
    setState('peek');
  }

  function setupToolbar(panel) {
    const toolbar = panel.querySelector('.gwb-viewer-toolbar');
    if (!toolbar || toolbar.querySelector('.gpwa-toolbar-toggle')) return;
    const adjust = iconButton('btn btn-outline-secondary btn-sm gpwa-adjust-toggle', 'fa-sliders', 'Show brightness and contrast');
    adjust.setAttribute('aria-pressed', 'false');
    adjust.addEventListener('click', () => {
      const open = toolbar.classList.toggle('is-adjusting');
      adjust.setAttribute('aria-pressed', open ? 'true' : 'false');
      adjust.classList.toggle('active', open);
    });
    const fold = iconButton('btn btn-outline-secondary btn-sm gpwa-toolbar-toggle', 'fa-chevron-down', 'Hide image controls');
    const setHidden = hidden => {
      toolbar.classList.toggle('is-hidden', hidden);
      fold.querySelector('i').className = `fa-solid ${hidden ? 'fa-sliders' : 'fa-chevron-down'}`;
      const label = hidden ? 'Show image controls' : 'Hide image controls';
      fold.setAttribute('aria-label', label);
      fold.title = label;
    };
    fold.addEventListener('click', () => {
      const hidden = !toolbar.classList.contains('is-hidden');
      setHidden(hidden);
      try { localStorage.setItem(TOOLBAR_HIDDEN_KEY, hidden ? '1' : '0'); } catch (_) {}
    });
    toolbar.append(adjust, fold);
    let hidden = false;
    try { hidden = localStorage.getItem(TOOLBAR_HIDDEN_KEY) === '1'; } catch (_) {}
    setHidden(hidden);
  }

  // The header strip carries the fullscreen control; it relays to the active
  // panel's viewer button, which (on iPhone) pins the image over the screen.
  function setupHeaderFullscreen() {
    const actions = workbench.querySelector('.gwb-header > div:last-child');
    if (!actions || actions.querySelector('.gpwa-fullscreen')) return;
    const button = iconButton('btn btn-sm btn-outline-secondary gpwa-fullscreen', 'fa-expand', 'View image fullscreen');
    const activeViewerButton = () => workbench.querySelector('.carousel-item.active .imggr-full');
    const sync = () => {
      const target = activeViewerButton();
      button.hidden = !target;
      const active = Boolean(target?.classList.contains('is-active'));
      button.querySelector('i').className = `fa-solid ${active ? 'fa-compress' : 'fa-expand'}`;
      const label = active ? 'Exit fullscreen' : 'View image fullscreen';
      button.setAttribute('aria-label', label);
      button.title = label;
    };
    button.addEventListener('click', () => {
      activeViewerButton()?.click();
      window.requestAnimationFrame(() => window.requestAnimationFrame(sync));
    });
    actions.insertBefore(button, actions.querySelector('[data-release-workbench]'));
    sync();
    workbench.querySelector('#workbench-panels')?.addEventListener('slid.bs.carousel', sync);
    ['fullscreenchange', 'webkitfullscreenchange'].forEach(type => document.addEventListener(type, () => window.requestAnimationFrame(sync)));
  }

  function setupAnnotateMode(panel) {
    const toggle = panel.querySelector('[data-annot-toggle]');
    const host = panel.querySelector('[data-geometry-sidebar-host]');
    if (!toggle || !host || panel.dataset.gpwaAnnotateReady === 'true') return;
    panel.dataset.gpwaAnnotateReady = 'true';
    // The Tools toggle already shows/hides the editor sidebar; annotate mode
    // additionally hides the grade sheet so the image keeps the screen.
    toggle.addEventListener('click', () => {
      window.requestAnimationFrame(() => {
        const sidebar = panel.querySelector('.imggr-annot-sidebar');
        const open = sidebar && !sidebar.classList.contains('is-collapsed');
        panel.classList.toggle('gpwa-annotating', Boolean(open) && phone.matches);
      });
    });
  }

  function setupPhoneLayout() {
    setupHeaderFullscreen();
    panels.forEach(panel => { setupSheet(panel); setupToolbar(panel); setupAnnotateMode(panel); });
  }
  if (phone.matches) setupPhoneLayout();
  // Rotating a tablet or resizing a window can cross the phone breakpoint after
  // load; every setup is idempotent, so re-run them when it does.
  phone.addEventListener('change', event => { if (event.matches) setupPhoneLayout(); });
})();
