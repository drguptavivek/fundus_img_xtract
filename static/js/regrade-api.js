(() => {
  document.body.addEventListener("regrade:error", (event) => {
    const message = event.detail && event.detail.message
      ? event.detail.message
      : "The regrade operation could not be completed.";
    if (typeof window.showFlashToast === "function") {
      window.showFlashToast(message, "danger");
    }
  });
})();
