// static/js/password-policy.js
(function () {
  'use strict';

  function isStrong(pw, minLen, commons, allowedSpecials) {
    if (!pw || pw.length < minLen) {
      return { ok: false, msg: 'Password should be at least ' + minLen + ' characters.' };
    }
    // Allowed charset: letters, digits, allowed specials only
    var allowedRe = new RegExp('^[A-Za-z0-9' + escapeForCharClass(allowedSpecials) + ']+$');
    if (!allowedRe.test(pw)) {
      return { ok: false, msg: 'Password may contain only English letters, digits, and ' + allowedSpecials.split('').join(' ') + '.' };
    }
    var lower = pw.toLowerCase();
    for (var i = 0; i < commons.length; i++) {
      if (lower.indexOf(commons[i]) !== -1) {
        return { ok: false, msg: 'Password contains a common/weak pattern (e.g., 123, qwerty, abcd, xyz, password, aiims).' };
      }
    }
    if (!/[A-Z]/.test(pw)) return { ok: false, msg: 'Include at least one uppercase letter.' };
    if (!/[a-z]/.test(pw)) return { ok: false, msg: 'Include at least one lowercase letter.' };
    var specialRe = new RegExp('[' + escapeForCharClass(allowedSpecials) + ']');
    if (!specialRe.test(pw)) return { ok: false, msg: 'Include at least one special character: ' + allowedSpecials.split('').join(' ') + '.' };
    return { ok: true, msg: '' };
  }

  function isValidUsername(name, minLen) {
    if (!name || name.length < minLen) {
      return { ok: false, msg: 'Username should be at least ' + minLen + ' characters.' };
    }
    if (!/^[A-Za-z0-9]+$/.test(name)) {
      return { ok: false, msg: 'Username may contain only English letters and digits.' };
    }
    return { ok: true, msg: '' };
  }

  function escapeForCharClass(s) {
    // Escape characters that are special inside []
    return s.replace(/[-\\^$*+?.()|[\]{}]/g, '\\$&');
  }

  function attach(form) {
    var minLen = parseInt(form.dataset.minlen || '10', 10);
    var commons = (form.dataset.commons || '123,qwerty,abcd,xyz,password,aiims')
      .split(',').map(function (s) { return s.trim().toLowerCase(); }).filter(Boolean);
    var allowedSpecials = (form.dataset.allowedSpecials || '@#!&').trim();

    var pwEl = form.querySelector('#new_password');
    var cfEl = form.querySelector('#confirm_password');
    var userEl = form.querySelector('#username');
    var usernamePolicy = form.dataset.usernamePolicy === '1';
    var usernameMin = parseInt(form.dataset.usernameMin || '3', 10);

    function validatePassword() {
      if (!pwEl) return true;
      var r = isStrong(pwEl.value, minLen, commons, allowedSpecials);
      if (pwEl.setCustomValidity) pwEl.setCustomValidity(r.ok ? '' : r.msg);

      if (cfEl) {
        if (pwEl.value !== cfEl.value) {
          cfEl.setCustomValidity && cfEl.setCustomValidity('Passwords do not match.');
        } else {
          cfEl.setCustomValidity && cfEl.setCustomValidity('');
        }
      }
      return r.ok && (!cfEl || pwEl.value === cfEl.value);
    }

    function validateUsername() {
      if (!usernamePolicy || !userEl) return true;
      var r = isValidUsername(userEl.value, usernameMin);
      if (userEl.setCustomValidity) userEl.setCustomValidity(r.ok ? '' : r.msg);
      return r.ok;
    }

    ['input', 'change', 'blur'].forEach(function (ev) {
      pwEl && pwEl.addEventListener(ev, validatePassword);
      cfEl && cfEl.addEventListener(ev, validatePassword);
      userEl && userEl.addEventListener(ev, validateUsername);
    });

    form.addEventListener('submit', function (e) {
      var okU = validateUsername();
      var okP = validatePassword();
      if (!okU || !okP || !form.checkValidity()) {
        e.preventDefault();
        // Trigger browser UI
        (userEl && userEl.reportValidity && !userEl.reportValidity());
        (pwEl && pwEl.reportValidity && !pwEl.reportValidity());
        (cfEl && cfEl.reportValidity && !cfEl.reportValidity());
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form[data-password-policy="1"]').forEach(attach);
  });
})();
