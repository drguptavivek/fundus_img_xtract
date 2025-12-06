// static/js/flash-toasts.js
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var container = document.getElementById('flash-toasts');
    if (!container) return;

    function setToastTopOffset() {
      var nav = document.querySelector('.navbar');
      var h = nav ? Math.round(nav.getBoundingClientRect().height) : 40; // default navbar height
      container.style.setProperty('--toast-top', (h + 2) + 'px'); // minimal gap
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

  // Global function to show flash toasts dynamically
  window.showFlashToast = function(message, type = 'info') {
    // Find or create toast container
    let container = document.getElementById('flash-toasts');
    if (!container) {
      container = document.createElement('div');
      container.id = 'flash-toasts';
      container.className = 'toast-container position-fixed top-0 end-0 p-3';
      container.style.zIndex = '1055';
      
      // Set toast top offset based on navbar
      function setToastTopOffset() {
        var nav = document.querySelector('.navbar');
        var h = nav ? Math.round(nav.getBoundingClientRect().height) : 40;
        container.style.setProperty('--toast-top', (h + 2) + 'px');
      }
      
      setToastTopOffset();
      window.addEventListener('resize', setToastTopOffset);
      
      // Handle navbar collapse/expand
      var collapseEl = document.getElementById('navbarNav');
      if (collapseEl) {
        collapseEl.addEventListener('shown.bs.collapse', setToastTopOffset);
        collapseEl.addEventListener('hidden.bs.collapse', setToastTopOffset);
      } else {
        document.querySelectorAll('.navbar-toggler').forEach(function (btn) {
          btn.addEventListener('click', function () {
            setTimeout(setToastTopOffset, 250);
          });
        });
      }
      
      document.body.appendChild(container);
    }

    // Create toast element
    const toastId = 'toast-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const bgClass = type === 'error' ? 'bg-danger' : type === 'success' ? 'bg-success' : type === 'warning' ? 'bg-warning' : 'bg-info';
    
    const toastHtml = `
      <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="d-flex">
          <div class="toast-body">
            ${message}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
      </div>
    `;

    // Add toast to container (handle Trusted Types)
    let toastElement;
    if (window.trustedTypes && window.trustedTypes.createPolicy) {
      // Use Trusted Types if available
      const policy = window.trustedTypes.createPolicy('toastPolicy', {
        createHTML: (string) => string
      });
      container.insertAdjacentHTML('beforeend', policy.createHTML(toastHtml));
      toastElement = document.getElementById(toastId);
    } else {
      // Fallback for browsers without Trusted Types
      container.insertAdjacentHTML('beforeend', toastHtml);
      toastElement = document.getElementById(toastId);
    }

    // Show toast using Bootstrap if available, otherwise fallback
    try {
      if (window.bootstrap && window.bootstrap.Toast) {
        const toast = new window.bootstrap.Toast(toastElement, { autohide: true, delay: 3000 });
        toast.show();
        
        // Remove element from DOM after hiding
        toastElement.addEventListener('hidden.bs.toast', () => {
          toastElement.remove();
        });
      } else {
        // Fallback without Bootstrap
        toastElement.classList.add('show');
        toastElement.style.position = 'relative';
        toastElement.style.marginBottom = '10px';
        
        setTimeout(() => {
          toastElement.classList.remove('show');
          toastElement.style.opacity = '0';
          toastElement.style.transform = 'translateX(100%)';
          toastElement.style.transition = 'all 0.3s ease-in-out';
          
          setTimeout(() => toastElement.remove(), 300);
        }, 3000);
      }
    } catch (error) {
      console.error('Error showing toast:', error);
      // Fallback to console
      console.log(`[${type.toUpperCase()}] ${message}`);
      toastElement.remove();
    }
  };
})();
