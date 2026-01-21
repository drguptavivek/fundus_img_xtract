document.addEventListener("DOMContentLoaded", () => {
  const updatedEl = document.getElementById("verify-remedio-kpi-updated");
  const fetchedAt = Date.now();
  const updateText = () => {
    if (!updatedEl) {
      return;
    }
    const minutes = Math.max(0, Math.floor((Date.now() - fetchedAt) / 60000));
    updatedEl.textContent = `Updated ${minutes} mins back`;
  };
  updateText();
  setInterval(updateText, 60000);

  const canvas = document.getElementById("verify-remedio-kpi-chart");
  if (!canvas || typeof Chart === "undefined") {
    return;
  }

  const url = canvas.dataset.url || "";
  if (!url) {
    return;
  }

  fetch(`${url}?days=7`, { credentials: "same-origin" })
    .then((response) => (response.ok ? response.json() : null))
    .then((payload) => {
      if (!payload) {
        return;
      }

      const ctx = canvas.getContext("2d");
      if (!ctx) {
        return;
      }

      new Chart(ctx, {
        type: "line",
        data: {
          labels: payload.labels || [],
          datasets: [
            {
              label: "DR",
              data: payload.dr || [],
              borderColor: "#0d6efd",
              backgroundColor: "rgba(13, 110, 253, 0.15)",
              tension: 0.3,
              fill: false,
            },
            {
              label: "Glaucoma",
              data: payload.glaucoma || [],
              borderColor: "#20c997",
              backgroundColor: "rgba(32, 201, 151, 0.15)",
              tension: 0.3,
              fill: false,
            },
            {
              label: "Encounter",
              data: payload.encounter || [],
              borderColor: "#fd7e14",
              backgroundColor: "rgba(253, 126, 20, 0.15)",
              tension: 0.3,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                boxWidth: 10,
                boxHeight: 10,
                usePointStyle: true,
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                precision: 0,
              },
            },
          },
        },
      });
    })
    .catch(() => {});
});
