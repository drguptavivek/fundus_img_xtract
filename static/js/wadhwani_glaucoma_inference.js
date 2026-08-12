document.addEventListener("DOMContentLoaded", () => {
  function toggleSourceFilters() {
    const sourceTypeSelect = document.getElementById("sourceTypeSelect");
    const zipFilters = document.getElementById("wadhwaniZipFilters");
    const directFilters = document.getElementById("wadhwaniDirectFilters");
    if (!sourceTypeSelect || !zipFilters || !directFilters) {
      return;
    }
    const sourceType = sourceTypeSelect.value;
    zipFilters.hidden = sourceType !== "zip";
    directFilters.hidden = !["direct", "pregraded"].includes(sourceType);
  }

  function stopJobPollingIfDone() {
    const jobContainer = document.getElementById("wadhwaniJobStatus");
    if (!jobContainer) {
      return;
    }
    const statusCard = jobContainer.querySelector("[data-job-done='true']");
    if (!statusCard) {
      return;
    }
    jobContainer.removeAttribute("hx-trigger");
    jobContainer.removeAttribute("hx-get");
  }

  function updateRunButtonState() {
    const runButton = document.getElementById("wadhwaniRunButton");
    const selectAll = document.getElementById("wadhwaniSelectAll");
    const checkboxes = Array.from(document.querySelectorAll(".wadhwani-task-checkbox"));

    if (!runButton) {
      return;
    }

    const checkedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
    runButton.disabled = checkedCount === 0;

    if (selectAll) {
      selectAll.checked = checkboxes.length > 0 && checkedCount === checkboxes.length;
      selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
    }
  }

  document.body.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.id === "sourceTypeSelect") {
      toggleSourceFilters();
      return;
    }

    if (target.id === "wadhwaniSelectAll") {
      const checked = target.checked;
      document.querySelectorAll(".wadhwani-task-checkbox").forEach((checkbox) => {
        checkbox.checked = checked;
      });
      updateRunButtonState();
      return;
    }

    if (target.classList.contains("wadhwani-task-checkbox")) {
      updateRunButtonState();
    }
  });

  document.body.addEventListener("htmx:afterSwap", () => {
    toggleSourceFilters();
    updateRunButtonState();
    stopJobPollingIfDone();
  });

  toggleSourceFilters();
  updateRunButtonState();
  stopJobPollingIfDone();
});
