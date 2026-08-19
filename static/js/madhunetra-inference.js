(function () {
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-select-all-visible-encounters]');
    if (!button) {
      return;
    }
    var workspace = button.closest('#madhunetraWorkspace') || document;
    workspace.querySelectorAll('input[name="selected_encounter_ids"]:not(:disabled)').forEach(function (input) {
      input.checked = true;
    });
  });
})();
