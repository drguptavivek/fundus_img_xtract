// static/js/flash-toasts.js
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var container = document.getElementById('flash-toasts');
    if (!container) return;

    function setToastTopOffset() {
      var nav = document.querySelector('.navbar');
      var h = nav ? Math.round(nav.getBoundingClientRect().height) : 56; // default navbar height
      container.style.setProperty('--toast-top', (h + 8) + 'px'); // +8px gap
    }

    // Set on load + on resize
    setToastTopOffset();
    window.addEventListener('resize', setToastTopOffset);

    // Recompute when the navbar collapses/expands (Bootstrap events if available)
    var collapseEl = document.getElementById('navbarNav');
    if (collapseEl) {
      collapseEl.addEventListener('shown.bs.collapse', setToastTopOffset);
      collapseEl.addEventListener('hidden.bs.collapse', setToastTopOffset);
    } else {
      // Fallback: watch toggler clicks
      document.querySelectorAll('.navbar-toggler').forEach(function (btn) {
        btn.addEventListener('click', function () {
          setTimeout(setToastTopOffset, 250);
        });
      });
    }

    // Auto-show flashes as Bootstrap toasts (3s)
    document.querySelectorAll('#flash-toasts .toast').forEach(function (el) {
      try {
        if (window.bootstrap && window.bootstrap.Toast) {
          var inst = window.bootstrap.Toast.getOrCreateInstance(el, { autohide: true, delay: 3000 });
          inst.show();
        } else {
          // Fallback without Bootstrap JS
          el.classList.add('show');
          setTimeout(function () { el.classList.remove('show'); }, 3000);
        }
      } catch (_) {}
    });
  });
})();
