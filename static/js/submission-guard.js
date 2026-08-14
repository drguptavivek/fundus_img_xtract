(function (global, document) {
  'use strict';

  const activeSubmissions = new WeakMap();

  function asElements(value) {
    if (!value) return [];
    if (value instanceof Element) return [value];
    return Array.from(value).filter(item => item instanceof Element);
  }

  function setButtonProgress(button, label) {
    if (!button) return;
    if (button instanceof HTMLInputElement) {
      button.value = label || 'Working…';
      return;
    }
    const spinner = document.createElement('span');
    spinner.className = 'spinner-border spinner-border-sm me-2';
    spinner.setAttribute('aria-hidden', 'true');
    button.replaceChildren(spinner, document.createTextNode(label || 'Working…'));
  }

  function acquire(target, options) {
    if (!target || activeSubmissions.has(target)) return null;

    const settings = options || {};
    const submitter = settings.submitter || null;
    const controls = asElements(settings.controls || submitter);
    const overlay = settings.overlay || null;
    const overlayMessage = settings.overlayMessage || null;
    const targetAriaBusy = target.getAttribute('aria-busy');
    const snapshots = controls.map(control => ({
      control,
      disabled: 'disabled' in control ? control.disabled : null,
      ariaDisabled: control.getAttribute('aria-disabled'),
      pointerEvents: control.style.pointerEvents,
      html: control === submitter && !(control instanceof HTMLInputElement) ? control.innerHTML : null,
      value: control === submitter && control instanceof HTMLInputElement ? control.value : null
    }));
    const overlayWasHidden = overlay ? overlay.classList.contains('d-none') : null;
    const overlayAriaHidden = overlay ? overlay.getAttribute('aria-hidden') : null;

    target.setAttribute('aria-busy', 'true');
    snapshots.forEach(snapshot => {
      snapshot.control.setAttribute('aria-disabled', 'true');
      if (settings.disableControls === false) {
        snapshot.control.style.pointerEvents = 'none';
      } else if (snapshot.disabled !== null) {
        snapshot.control.disabled = true;
      }
    });
    if (submitter) setButtonProgress(submitter, settings.busyLabel);
    if (overlayMessage && settings.message) overlayMessage.textContent = settings.message;
    if (overlay) {
      overlay.classList.remove('d-none');
      overlay.setAttribute('aria-hidden', 'false');
    }

    let released = false;
    const token = {
      release: function () {
        if (released) return;
        released = true;
        activeSubmissions.delete(target);
        if (targetAriaBusy === null) target.removeAttribute('aria-busy');
        else target.setAttribute('aria-busy', targetAriaBusy);
        snapshots.forEach(snapshot => {
          if (snapshot.disabled !== null) snapshot.control.disabled = snapshot.disabled;
          if (snapshot.ariaDisabled === null) snapshot.control.removeAttribute('aria-disabled');
          else snapshot.control.setAttribute('aria-disabled', snapshot.ariaDisabled);
          snapshot.control.style.pointerEvents = snapshot.pointerEvents;
          if (snapshot.html !== null) snapshot.control.innerHTML = snapshot.html;
          if (snapshot.value !== null) snapshot.control.value = snapshot.value;
        });
        if (overlay) {
          overlay.classList.toggle('d-none', Boolean(overlayWasHidden));
          if (overlayAriaHidden === null) overlay.removeAttribute('aria-hidden');
          else overlay.setAttribute('aria-hidden', overlayAriaHidden);
        }
      }
    };
    activeSubmissions.set(target, token);
    return token;
  }

  function isActive(target) {
    return Boolean(target && activeSubmissions.has(target));
  }

  document.addEventListener('submit', function (event) {
    const form = event.target.closest('form[data-submission-guard]');
    if (!form) return;
    if (isActive(form)) {
      event.preventDefault();
      return;
    }
    const submitter = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
    acquire(form, {
      submitter,
      controls: form.querySelectorAll('button[type="submit"], input[type="submit"]'),
      disableControls: false,
      busyLabel: form.dataset.submissionBusyLabel || 'Saving…'
    });
  }, true);

  global.SubmissionGuard = Object.freeze({acquire, isActive});
})(window, document);
