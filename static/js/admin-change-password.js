// static/js/admin-change-password.js
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.querySelector('form');
    if (!form) return;

    var pwEl = document.getElementById('new_password');
    var cfEl = document.getElementById('confirm_password');

    form.addEventListener('submit', function (e) {
      var pw = (pwEl && 'value' in pwEl) ? pwEl.value : '';
      var cf = (cfEl && 'value' in cfEl) ? cfEl.value : '';

      if (pw !== cf) {
        e.preventDefault();
        if (cfEl && typeof cfEl.setCustomValidity === 'function') {
          cfEl.setCustomValidity('Passwords do not match.');
          cfEl.reportValidity();
          var clear = function () {
            cfEl.setCustomValidity('');
            cfEl.removeEventListener('input', clear);
          };
          cfEl.addEventListener('input', clear);
        } else {
          alert('Passwords do not match.');
        }
      }
    });
  });
})();
