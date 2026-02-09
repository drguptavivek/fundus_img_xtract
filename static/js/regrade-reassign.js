(() => {
  const selectAll = document.getElementById("select-all");
  if (!selectAll) return;
  selectAll.addEventListener("change", () => {
    document.querySelectorAll(".task-checkbox").forEach((box) => {
      box.checked = selectAll.checked;
    });
  });
})();
