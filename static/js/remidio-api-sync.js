(function () {
  function enableTooltips(root) {
    if (!window.bootstrap || !window.bootstrap.Tooltip) {
      return;
    }
    (root || document).querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
      var existing = window.bootstrap.Tooltip.getInstance(element);
      if (existing) {
        existing.dispose();
      }
      new window.bootstrap.Tooltip(element);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    enableTooltips(document);
  });

  document.body.addEventListener('htmx:afterSwap', function (event) {
    enableTooltips(event.detail && event.detail.target ? event.detail.target : document);
  });
})();
