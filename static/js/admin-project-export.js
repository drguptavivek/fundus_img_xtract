(function () {
  // The form is swapped in by HTMX, so everything is delegated from the document.
  const form = () => document.getElementById('project-export-form');
  const el = (id) => document.getElementById(id);

  function selectedHospitals() {
    return Array.from(el('export-hospitals').selectedOptions).map((o) => o.value);
  }

  // Lab units follow the chosen hospitals; with no hospital chosen, every lab unit is listed.
  function filterLabs() {
    const chosen = selectedHospitals();
    Array.from(el('export-labs').options).forEach((option) => {
      const visible = chosen.length === 0 || chosen.includes(option.dataset.hospital);
      option.hidden = !visible;
      if (!visible) option.selected = false;
    });
  }

  function sync() {
    const none = el('export-project').value === 'none';
    el('no-project-fields').hidden = !none;
    el('export-hospitals').disabled = !none;
    el('export-labs').disabled = !none;
    if (none) filterLabs();
  }

  document.addEventListener('change', (event) => {
    if (!form() || !form().contains(event.target)) return;
    if (event.target.id === 'export-project') sync();
    if (event.target.id === 'export-hospitals') filterLabs();
  });

  document.addEventListener('submit', (event) => {
    if (event.target !== form()) return;
    const f = form();
    const project = el('export-project').value;
    const xlsx = event.submitter && event.submitter.value === 'xlsx';
    if (project === 'none') {
      if (selectedHospitals().length === 0 && el('export-labs').selectedOptions.length === 0) {
        event.preventDefault();
        (window.showFlashToast || window.alert)('Select at least one hospital or lab unit.', 'error');
        return;
      }
      f.action = xlsx ? f.dataset.noProjectXlsxUrl : f.dataset.noProjectUrl;
    } else {
      const base = xlsx ? f.dataset.projectXlsxUrl : f.dataset.projectUrl;
      f.action = base.replace(/\/0\//, '/' + encodeURIComponent(project) + '/');
    }
  });

  document.body.addEventListener('htmx:afterSwap', (event) => {
    if (event.target.id === 'project-export-workspace' && form()) sync();
  });
})();
