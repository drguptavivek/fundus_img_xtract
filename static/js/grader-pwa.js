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
    navigator.serviceWorker.register(body.dataset.swUrl, { scope: body.dataset.swScope || '/grader/' })
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

  // ---- Phone layout: grade card as a bottom sheet, sidebar as annotate mode ----
  const phone = window.matchMedia('(max-width: 767.98px)');
  const panels = Array.from(workbench.querySelectorAll('[data-task-uuid]'));

  function setupSheet(panel) {
    const card = panel.querySelector('.gwb-grade-card');
    const header = card?.querySelector('.card-header');
    if (!card || !header || card.querySelector('.gpwa-sheet-handle')) return;
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'gpwa-sheet-handle';
    handle.setAttribute('aria-label', 'Show or hide features and comment');
    handle.setAttribute('aria-expanded', 'false');
    header.prepend(handle);
    card.classList.add('is-peek');
    const setOpen = open => {
      card.classList.toggle('is-peek', !open);
      handle.setAttribute('aria-expanded', open ? 'true' : 'false');
      const viewer = panel.querySelector('.imggr-viewer-root');
      window.requestAnimationFrame(() => viewer?.__imggrState?.refreshViewportSize?.());
    };
    handle.addEventListener('click', () => setOpen(card.classList.contains('is-peek')));
    // Choosing a grade that carries features opens the sheet so they are not missed.
    panel.querySelectorAll('[data-grade-option]').forEach(option => {
      option.addEventListener('change', () => {
        window.requestAnimationFrame(() => {
          const fieldset = panel.querySelector('[data-feature-fieldset]');
          if (fieldset && !fieldset.classList.contains('d-none')) setOpen(true);
        });
      });
    });
  }

  function setupAnnotateMode(panel) {
    const toggle = panel.querySelector('[data-annot-toggle]');
    const host = panel.querySelector('[data-geometry-sidebar-host]');
    if (!toggle || !host || host.querySelector('.gpwa-annotate-done')) return;
    const done = document.createElement('button');
    done.type = 'button';
    done.className = 'btn btn-success gpwa-annotate-done mt-2';
    done.innerHTML = '<i class="fa-solid fa-check me-1" aria-hidden="true"></i>Done annotating';
    host.appendChild(done);
    // The Tools toggle already shows/hides the editor sidebar; annotate mode
    // additionally hides the grade sheet so the image keeps the screen.
    toggle.addEventListener('click', () => {
      window.requestAnimationFrame(() => {
        const sidebar = panel.querySelector('.imggr-annot-sidebar');
        const open = sidebar && !sidebar.classList.contains('is-collapsed');
        panel.classList.toggle('gpwa-annotating', Boolean(open) && phone.matches);
      });
    });
    done.addEventListener('click', () => {
      panel.classList.remove('gpwa-annotating');
      const sidebar = panel.querySelector('.imggr-annot-sidebar');
      if (sidebar && !sidebar.classList.contains('is-collapsed')) toggle.click();
    });
  }

  function setupPhoneLayout() {
    panels.forEach(panel => { setupSheet(panel); setupAnnotateMode(panel); });
  }
  if (phone.matches) setupPhoneLayout();
  // Rotating a tablet or resizing a window can cross the phone breakpoint after
  // load; both setups are idempotent, so re-run them when it does.
  phone.addEventListener('change', event => { if (event.matches) setupPhoneLayout(); });
})();
