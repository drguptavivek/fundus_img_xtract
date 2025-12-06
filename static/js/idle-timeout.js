// static/js/idle-timeout.js
(function () {
  "use strict";

  // Find our own script tag (works with async)
  const me = document.currentScript || document.getElementById("idle-timeout-js");
  if (!me) return;

  // Read config from data-attributes (set in base.html)
  const enabled = me.dataset.enabled === "1";
  if (!enabled) return;

  const TIMEOUT_MIN = parseInt(me.dataset.timeoutMin || "30", 10);
  const WARN_LEAD_MIN = parseInt(me.dataset.warnLeadMin || "2", 10);
  const PING_URL = me.dataset.pingUrl || "/ping";
  const LOGIN_URL = me.dataset.loginUrl || "/login";

  const WARNING_AT_SEC = Math.max(0, (TIMEOUT_MIN - WARN_LEAD_MIN) * 60);
  const LOGOUT_AT_SEC  = TIMEOUT_MIN * 60;

  // State
  let idleSec = 0;
  let warnShown = false;
  let countdownTimer = null;
  let modal, modalEl, countdownEl, stayBtn;

  // Create modal lazily (only when needed)
  function ensureModal() {
    if (modalEl) return;
    modalEl = document.createElement("div");
    modalEl.innerHTML = `
      <div class="modal fade" id="idleModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered modal-sm">
          <div class="modal-content">
            <div class="modal-header py-2">
              <h5 class="modal-title">Are you still there?</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <p class="mb-0">
                You’ll be logged out in <strong><span id="idleCountdown">120</span>s</strong> due to inactivity.
              </p>
            </div>
            <div class="modal-footer py-2">
              <button id="staySignedInBtn" class="btn btn-primary btn-sm" type="button">Stay signed in</button>
              <a class="btn btn-outline-secondary btn-sm" href="${LOGIN_URL}">Log out now</a>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modalEl);

    countdownEl = document.getElementById("idleCountdown");
    stayBtn = document.getElementById("staySignedInBtn");

    // Prefer Bootstrap modal if present; fallback to simple confirm
    if (window.bootstrap && window.bootstrap.Modal) {
      modal = new window.bootstrap.Modal(document.getElementById("idleModal"), {
        backdrop: "static",
        keyboard: false
      });
    } else {
      modal = {
        show() {
          // Fallback: simple confirm loop
          const end = Date.now() + WARN_LEAD_MIN * 60 * 1000;
          const tick = () => {
            const remaining = Math.max(0, Math.round((end - Date.now()) / 1000));
            if (remaining === 0) {
              window.location.href = LOGIN_URL;
              return;
            }
            // no native modal; do nothing further
          };
          tick();
        },
        hide() {}
      };
    }

    if (stayBtn) {
      stayBtn.addEventListener("click", async () => {
        try {
          const res = await fetch(PING_URL, { method: "GET", credentials: "same-origin" });
          if (res.redirected) { window.location = res.url; return; }
        } catch (_) { /* ignore network errors; server will enforce */ }
        resetIdle();
      });
    }
  }

  function resetIdle() {
    idleSec = 0;
    if (warnShown) {
      warnShown = false;
      if (countdownTimer) clearInterval(countdownTimer);
      try { modal.hide(); } catch (_) {}
    }
    try { localStorage.setItem("lastActivityTs", String(Date.now())); } catch (_) {}
  }

  // Activity listeners (cross-tab aware)
  const resetEvents = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "click", "wheel"];
  resetEvents.forEach(evt => window.addEventListener(evt, resetIdle, { passive: true }));

  window.addEventListener("storage", (e) => {
    if (e.key === "lastActivityTs") resetIdle();
  });

  // Idle tick
  setInterval(() => {
    idleSec++;
    if (!warnShown && idleSec >= WARNING_AT_SEC) {
      warnShown = true;
      ensureModal();
      // live countdown
      let remaining = Math.max(0, LOGOUT_AT_SEC - idleSec);
      if (countdownEl) countdownEl.textContent = String(remaining);
      try { modal.show(); } catch (_) {}

      countdownTimer = setInterval(() => {
        remaining = Math.max(0, LOGOUT_AT_SEC - idleSec);
        if (countdownEl) countdownEl.textContent = String(remaining);
        if (remaining <= 0) {
          window.location.href = LOGIN_URL;
        }
      }, 1000);
    }
  }, 1000);

  // initial sync so multiple tabs start aligned
  try { localStorage.setItem("lastActivityTs", String(Date.now())); } catch (_) {}

})();
