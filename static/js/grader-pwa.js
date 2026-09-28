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
  // "phone" is either dimension. Portrait tablets below the lg breakpoint (iPad
  // portrait) get the same full-screen image and overlay sheet; grader-pwa.css
  // uses the same query.
  const PHONE_QUERY = '(max-width: 991.98px), (max-height: 500px), (max-width: 1919.98px) and (orientation: portrait)';
  const phone = window.matchMedia(PHONE_QUERY);
  const panels = Array.from(workbench.querySelectorAll('[data-task-uuid]'));
  const TOOLBAR_HIDDEN_KEY = 'grader.toolbar_hidden';
  const SHEET_STATES = ['rail', 'open'];

  function refreshViewer(panel) {
    const viewer = panel.querySelector('.imggr-viewer-root');
    window.requestAnimationFrame(() => {
      updateFitInsets(panel);
      viewer?.__imggrState?.refreshViewportSize?.();
    });
  }

  // The header strip (top) and the filter strip + sheet rail (bottom) overlay
  // the image stage; the viewer fits the image in the band between them
  // (data-fit-inset-*). Immersive mode and fullscreen clear the bands. The
  // bands are measured with the sheet as a rail and the sliders folded, so
  // opening either never resizes the image.
  function setFitInsets(main, top, bottom) {
    const changed = main.dataset.fitInsetTop !== String(Math.round(top))
      || main.dataset.fitInsetBottom !== String(Math.round(bottom));
    main.dataset.fitInsetTop = String(Math.round(top));
    main.dataset.fitInsetBottom = String(Math.round(bottom));
    main.style.setProperty('--imggr-inset-top', `${Math.round(top)}px`);
    main.style.setProperty('--imggr-inset-bottom', `${Math.round(bottom)}px`);
    if (changed) refitWhenReady(main);
  }
  // The viewer script is deferred and loads its image asynchronously, so the
  // first bands can land before it can re-fit: retry until its state exists
  // and the image has a size, then re-fit once.
  function refitWhenReady(main, attempt = 0) {
    const root = main.closest('.imggr-viewer-root');
    const img = main.querySelector('.imggr-main-img');
    const state = root?.__imggrState;
    if (state?.refreshViewportSize && img?.naturalWidth) {
      state.refreshViewportSize();
      return;
    }
    if (attempt < 40) window.setTimeout(() => refitWhenReady(main, attempt + 1), 100);
    if (img && !img.dataset.gpwaRefitOnLoad) {
      img.dataset.gpwaRefitOnLoad = 'true';
      img.addEventListener('load', () => root?.__imggrState?.refreshViewportSize?.());
    }
  }
  function updateFitInsets(panel, attempt = 0) {
    const main = panel.querySelector('.imggr-main');
    if (!main) return;
    const fullscreen = document.fullscreenElement || document.webkitFullscreenElement
      || body.classList.contains('imggr-fullscreen-active');
    if (!phone.matches || body.classList.contains(IMMERSIVE_CLASS) || fullscreen) {
      applyFitInsetsEverywhere(0, 0);
      return;
    }
    const card = panel.querySelector('.gwb-grade-card');
    const toolbar = panel.querySelector('.gwb-viewer-toolbar');
    const measuring = card?.dataset.sheetState !== 'open' && !toolbar?.classList.contains('is-adjusting');
    if (!measuring && Number(main.dataset.fitInsetBottom) > 0) return;
    const box = main.getBoundingClientRect();
    if (!box.height) {
      // Not laid out yet (first paint, or an off-screen carousel panel): try
      // again shortly rather than leaving the image under the overlays.
      if (attempt < 30 && panel.closest('.carousel-item.active')) {
        window.setTimeout(() => updateFitInsets(panel, attempt + 1), 100);
      }
      return;
    }
    const overlaps = rect => rect.width > 0 && rect.left < box.right - 1 && rect.right > box.left + 1;
    let top = 0;
    const header = workbench.querySelector('.gwb-header');
    if (header && getComputedStyle(header).position === 'absolute') {
      const rect = header.getBoundingClientRect();
      if (overlaps(rect)) top = Math.max(0, rect.bottom - box.top);
    }
    let bottom = 0;
    [toolbar && !toolbar.classList.contains('is-hidden') ? toolbar : null, card].forEach(element => {
      if (!element) return;
      const rect = element.getBoundingClientRect();
      if (overlaps(rect) && rect.top < box.bottom && rect.top > box.top + box.height / 2) {
        bottom = Math.max(bottom, box.bottom - rect.top);
      }
    });
    applyFitInsetsEverywhere(top, bottom);
  }
  // Every panel shares the same chrome, so the bands measured on the visible
  // panel apply to all of them: the next image is already fitted when it
  // slides in instead of settling (and visibly shifting) afterwards.
  function applyFitInsetsEverywhere(top, bottom) {
    workbench.querySelectorAll('.imggr-main').forEach(main => setFitInsets(main, top, bottom));
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

  // Open / closed is one choice for the whole package: closing the sheet on one
  // image keeps it closed as the grader moves forward and back. Rotation resets
  // it to the orientation's default.
  const sheetSetters = new Set();
  let sheetPreference = null;
  function chooseSheet(state) {
    sheetPreference = state;
    sheetSetters.forEach(set => set(state));
  }
  workbench.querySelector('#workbench-panels')?.addEventListener('slide.bs.carousel', () => {
    if (sheetPreference) sheetSetters.forEach(set => set(sheetPreference));
  });

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
    // Portrait bar reads "DR: Mild DR" on one line. The landscape side strip
    // shows the disease (first 15 characters) over "< Mild DR" - or "< Grade"
    // before one is chosen - so it reads as the way to the grade buttons.
    const shortDisease = disease.length > 15 ? `${disease.slice(0, 14)}…` : disease;
    const updateLabel = () => {
      const grade = chosenGrade();
      label.replaceChildren();
      const name = document.createElement('span');
      name.className = 'gpwa-sheet-disease';
      name.dataset.short = shortDisease;
      name.textContent = disease;
      const separator = document.createElement('span');
      separator.className = 'gpwa-sheet-sep';
      separator.textContent = ': ';
      const line = document.createElement('span');
      line.className = 'gpwa-sheet-grade';
      const arrow = document.createElement('i');
      arrow.className = 'fa-solid fa-chevron-left gpwa-sheet-open-arrow';
      arrow.setAttribute('aria-hidden', 'true');
      const value = document.createElement(grade ? 'strong' : 'span');
      value.textContent = grade || 'choose a grade';
      value.dataset.short = grade || 'Grade';
      line.append(arrow, value);
      label.append(name, separator, line);
    };

    // Steady height: grades carry different feature lists and guidelines, so
    // the open sheet would jump as the grader moves between grades. Reserve
    // room for the longest feature list up front (at the current column count)
    // and let the guidelines block only ever grow.
    const featureHost = panel.querySelector('[data-feature-options]');
    const guidelines = panel.querySelector('[data-grade-guidelines]');
    const FEATURE_ROW_PX = 40;
    const FEATURE_COL_PX = 9.5 * 16 + 8;
    // Guidelines are measured off-screen, rebuilt from an inert parse with only
    // text-formatting tags (no attributes), never injected as raw HTML.
    const SAFE_TAGS = new Set(['P', 'UL', 'OL', 'LI', 'B', 'STRONG', 'I', 'EM', 'BR', 'SPAN', 'DIV']);
    const safeClone = (source, target) => {
      source.childNodes.forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) { target.append(node.textContent); return; }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        const copy = document.createElement(SAFE_TAGS.has(node.tagName) ? node.tagName : 'span');
        safeClone(node, copy);
        target.append(copy);
      });
    };
    const tallestGuidelines = (data, width) => {
      if (!guidelines || !width) return 0;
      const probe = document.createElement('div');
      probe.className = guidelines.className;
      probe.style.cssText = `position:absolute;visibility:hidden;left:-9999px;top:0;width:${width}px;min-height:0`;
      card.querySelector('.card-body').append(probe);
      let tallest = 0;
      (data?.features || []).forEach(grade => {
        probe.replaceChildren();
        safeClone(new DOMParser().parseFromString(grade.guidelines || '', 'text/html').body, probe);
        tallest = Math.max(tallest, probe.offsetHeight);
      });
      probe.remove();
      return tallest;
    };
    const reserveSheetSpace = () => {
      if (card.dataset.sheetState === 'rail') return;
      const data = window.linkedGradingData?.[panel.dataset.taskUuid];
      const body = card.querySelector('.card-body');
      const style = body ? getComputedStyle(body) : null;
      const width = body ? body.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) : 0;
      if (!width) return;
      const maxFeatures = Math.max(0, ...(data?.features || []).map(grade => (grade.features || []).length));
      if (featureHost && maxFeatures) {
        const columns = Math.max(1, Math.floor((width + 8) / FEATURE_COL_PX));
        featureHost.style.minHeight = `${Math.ceil(maxFeatures / columns) * FEATURE_ROW_PX}px`;
        panel.classList.add('gpwa-reserve-features');
      }
      const tallest = tallestGuidelines(data, width);
      if (tallest && guidelines) guidelines.style.minHeight = `${tallest}px`;
    };
    // The estimate assumes one-line labels; a longer list that wraps grows the
    // reservation once and it then holds (grow-only, like the guidelines).
    const holdGrown = element => {
      if (!element) return;
      const height = element.offsetHeight;
      const held = parseFloat(element.style.minHeight) || 0;
      if (height > held) element.style.minHeight = `${height}px`;
    };
    const holdGuidelinesHeight = () => {
      if (card.dataset.sheetState === 'rail') return;
      holdGrown(guidelines);
      holdGrown(featureHost);
    };
    window.addEventListener('resize', () => window.requestAnimationFrame(reserveSheetSpace));

    const landscapePhone = window.matchMedia('(max-height: 500px) and (orientation: landscape), (max-width: 991.98px) and (orientation: landscape)');
    const current = () => card.dataset.sheetState || 'rail';
    const setState = state => {
      card.dataset.sheetState = state;
      card.classList.toggle('is-rail', state === 'rail');
      handle.setAttribute('aria-expanded', state === 'rail' ? 'false' : 'true');
      handle.setAttribute('aria-label', state === 'open' ? 'Hide grading controls' : 'Show grading controls');
      const rail = state === 'rail';
      // Portrait: a bottom sheet (up opens, down closes). Landscape: a side
      // column on the right (left opens it out, right tucks it away).
      const icon = landscapePhone.matches
        ? (rail ? 'fa-chevron-left' : 'fa-chevron-right')
        : (rail ? 'fa-chevron-up' : 'fa-chevron-down');
      minimise.querySelector('i').className = `fa-solid ${icon}`;
      const minimiseLabel = rail ? 'Open grade sheet' : 'Minimise grade sheet';
      minimise.setAttribute('aria-label', minimiseLabel);
      minimise.title = minimiseLabel;
      updateLabel();
      if (state === 'open') window.requestAnimationFrame(() => { reserveSheetSpace(); holdGuidelinesHeight(); });
      refreshViewer(panel);
    };
    const step = delta => {
      const index = SHEET_STATES.indexOf(current());
      chooseSheet(SHEET_STATES[Math.min(SHEET_STATES.length - 1, Math.max(0, index + delta))]);
    };

    // Tap the handle or the chevron: rail <-> open. Swipe the header up / down likewise.
    let swiped = false;
    const toggle = () => chooseSheet(current() === 'rail' ? 'open' : 'rail');
    handle.addEventListener('click', () => {
      if (swiped) { swiped = false; return; }
      toggle();
    });
    minimise.addEventListener('click', toggle);
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
          holdGuidelinesHeight();
          const fieldset = panel.querySelector('[data-feature-fieldset]');
          if (fieldset && !fieldset.classList.contains('d-none')) setState('open');
        });
      });
    });
    // Portrait: starts as the rail so the image has the screen; pull up for the
    // grades. Landscape phones: the image is height-limited and leaves spare
    // width, so the sheet starts open as a side column at no cost to the image.
    sheetSetters.add(setState);
    setState(sheetPreference || (landscapePhone.matches ? 'open' : 'rail'));
    landscapePhone.addEventListener('change', event => {
      sheetPreference = null;
      setState(event.matches ? 'open' : 'rail');
    });
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
      refreshViewer(panel);
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
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => { sync(); refitActivePanels(); }));
    });
    actions.insertBefore(button, actions.querySelector('[data-release-workbench]'));
    sync();
    workbench.querySelector('#workbench-panels')?.addEventListener('slid.bs.carousel', sync);
    ['fullscreenchange', 'webkitfullscreenchange'].forEach(type => document.addEventListener(type, () => window.requestAnimationFrame(sync)));
    // Leaving via the viewer's own exit button fires no fullscreenchange in the CSS fallback.
    workbench.addEventListener('click', event => {
      if (event.target.closest('.imggr-full')) window.requestAnimationFrame(() => window.requestAnimationFrame(() => { sync(); refitActivePanels(); }));
    });
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
        // The viewer re-measured before the sidebar became an overlay (it was
        // still taking height in the stacked layout); fit again now.
        refreshViewer(panel);
      });
    });
  }

  // Immersive mode: a sideways swipe on the image hides the header, filter
  // strip, grade sheet and pager so the image has the whole screen; another
  // sideways swipe brings them back.
  const IMMERSIVE_CLASS = 'gpwa-immersive';
  function setImmersive(on) {
    body.classList.toggle(IMMERSIVE_CLASS, on);
    const panel = workbench.querySelector('.carousel-item.active [data-task-uuid]')
      || workbench.querySelector('.carousel-item.active');
    if (panel) refreshViewer(panel);
  }
  function setupImmersiveSwipe() {
    if (workbench.dataset.gpwaImmersiveReady === 'true') return;
    workbench.dataset.gpwaImmersiveReady = 'true';
    workbench.addEventListener('imggr:swipe', () => {
      if (!phone.matches) return;
      setImmersive(!body.classList.contains(IMMERSIVE_CLASS));
    });
    phone.addEventListener('change', event => { if (!event.matches) setImmersive(false); });
  }

  function refitActivePanels() { panels.forEach(panel => refreshViewer(panel)); }
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(type => document.addEventListener(type, refitActivePanels));
  window.addEventListener('resize', () => window.requestAnimationFrame(refitActivePanels));
  // Panels off-screen in the carousel have no size to measure until shown.
  workbench.querySelector('#workbench-panels')?.addEventListener('slid.bs.carousel', refitActivePanels);

  // iPad / Full modes: the header's badges and actions ride in the footer row
  // (between the pager and previous / next) so the image gets the header's
  // height. Phone mode keeps its overlay header. Moving the nodes keeps their
  // listeners and data hooks, so lease and progress updates still land.
  const headerActions = workbench.querySelector('.gwb-header > div:last-child');
  const footer = workbench.querySelector('.gwb-footer');
  function placeHeaderActions() {
    if (!headerActions || !footer) return;
    const header = workbench.querySelector('.gwb-header');
    if (phone.matches) {
      if (headerActions.parentElement !== header) header.append(headerActions);
      body.classList.remove('gpwa-actions-in-footer');
    } else {
      const nav = footer.querySelector(':scope > .btn-group');
      if (headerActions.parentElement !== footer) footer.insertBefore(headerActions, nav);
      body.classList.add('gpwa-actions-in-footer');
    }
  }
  placeHeaderActions();
  phone.addEventListener('change', placeHeaderActions);

  function setupPhoneLayout() {
    setupImmersiveSwipe();
    setupHeaderFullscreen();
    panels.forEach(panel => { setupSheet(panel); setupToolbar(panel); setupAnnotateMode(panel); });
  }
  if (phone.matches) { setupPhoneLayout(); refitActivePanels(); }
  // Rotating a tablet or resizing a window can cross the phone breakpoint after
  // load; every setup is idempotent, so re-run them when it does.
  phone.addEventListener('change', event => { if (event.matches) setupPhoneLayout(); });
})();
