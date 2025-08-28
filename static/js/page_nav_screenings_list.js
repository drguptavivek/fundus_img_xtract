document.addEventListener('DOMContentLoaded', function () {
  const input = document.getElementById('goto-page');
  if (!input) return;
  const form = input.closest('form');
  const min = parseInt(input.min || '1', 10);
  const max = parseInt(input.max || '1', 10);

  function clamp() {
    let v = parseInt(input.value || String(min), 10);
    if (isNaN(v)) v = min;
    if (v < min) v = min;
    if (v > max) v = max;
    input.value = v;
  }

  input.addEventListener('blur', function () { clamp(); form.requestSubmit ? form.requestSubmit() : form.submit(); });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); clamp(); form.requestSubmit ? form.requestSubmit() : form.submit(); }
  });
  input.addEventListener('change', clamp); // handles spinner clicks
});