(() => {
  function byId(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    const str = value == null ? "" : String(value);
    return str
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function toNum(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function pctText(value) {
    const n = toNum(value);
    return `${n.toFixed(2)}%`;
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const diseaseId = byId("hd-filter-disease")?.value || "";
    const hospitalId = byId("hd-filter-hospital")?.value || "";
    const labUnitId = byId("hd-filter-lab")?.value || "";
    if (diseaseId) params.set("disease_id", diseaseId);
    if (hospitalId) params.set("hospital_id", hospitalId);
    if (labUnitId) params.set("lab_unit_id", labUnitId);
    return params.toString();
  }

  async function fetchJson(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  }

  function setLoading(isLoading) {
    const loadingEl = byId("hd-loading");
    if (!loadingEl) return;
    loadingEl.classList.toggle("d-none", !isLoading);
  }

  function renderEmpty(tbodyId, colCount, text = "No data") {
    const tbody = byId(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="${colCount}" class="text-muted">${escapeHtml(text)}</td></tr>`;
  }

  function renderDiseaseRows(data) {
    const tbody = byId("hd-table-disease");
    if (!tbody) return;
    if (!Array.isArray(data) || !data.length) {
      renderEmpty("hd-table-disease", 6);
      return;
    }
    tbody.innerHTML = data
      .map(
        (row) => `
        <tr>
          <td>${escapeHtml(row.disease_name)}</td>
          <td>${toNum(row.total_tasks)}</td>
          <td>${toNum(row.pending_resident)} (${pctText(row.pending_resident_pct)})</td>
          <td>${toNum(row.pending_resident2)} (${pctText(row.pending_resident2_pct)})</td>
          <td>${toNum(row.pending_arbitration)} (${pctText(row.pending_arbitration_pct)})</td>
          <td>${toNum(row.non_gradable_count)} (${pctText(row.non_gradable_pct)})</td>
        </tr>
      `
      )
      .join("");
  }

  function renderLabDiseaseRows(data) {
    const tbody = byId("hd-table-lab-disease");
    if (!tbody) return;
    if (!Array.isArray(data) || !data.length) {
      renderEmpty("hd-table-lab-disease", 8);
      return;
    }
    tbody.innerHTML = data
      .map(
        (row) => `
        <tr>
          <td>${escapeHtml(row.hospital_name)}</td>
          <td>${escapeHtml(row.lab_unit_name)}</td>
          <td>${escapeHtml(row.disease_name)}</td>
          <td>${toNum(row.total_tasks)}</td>
          <td>${toNum(row.pending_resident)} (${pctText(row.pending_resident_pct)})</td>
          <td>${toNum(row.pending_resident2)} (${pctText(row.pending_resident2_pct)})</td>
          <td>${toNum(row.pending_arbitration)} (${pctText(row.pending_arbitration_pct)})</td>
          <td>${toNum(row.non_gradable_count)} (${pctText(row.non_gradable_pct)})</td>
        </tr>
      `
      )
      .join("");
  }

  function renderUserRows(data) {
    const tbody = byId("hd-table-user");
    if (!tbody) return;
    if (!Array.isArray(data) || !data.length) {
      renderEmpty("hd-table-user", 3);
      return;
    }
    tbody.innerHTML = data
      .map(
        (row) => `
        <tr>
          <td>${escapeHtml(row.disease_name)}</td>
          <td>${escapeHtml(row.user_name)}</td>
          <td>${toNum(row.completed_count)}</td>
        </tr>
      `
      )
      .join("");
  }

  function renderRosterRows(data) {
    const tbody = byId("hd-table-roster");
    if (!tbody) return;
    if (!Array.isArray(data) || !data.length) {
      renderEmpty("hd-table-roster", 6);
      return;
    }
    const usersText = (items) =>
      Array.isArray(items) && items.length
        ? items.map((x) => escapeHtml(x.user_name)).join(", ")
        : "-";
    tbody.innerHTML = data
      .map(
        (row) => `
        <tr>
          <td>${escapeHtml(row.hospital_name)}</td>
          <td>${escapeHtml(row.lab_unit_name)}</td>
          <td>${escapeHtml(row.disease_name)}</td>
          <td>${usersText(row.resident_slot_users)}</td>
          <td>${usersText(row.resident2_slot_users)}</td>
          <td>${usersText(row.arbitrator_slot_users)}</td>
        </tr>
      `
      )
      .join("");
  }

  function renderKpis(meta) {
    byId("hd-kpi-total").textContent = `${toNum(meta?.cumulative_total_tasks)}`;
    byId("hd-kpi-non-gradable").textContent = `${toNum(meta?.cumulative_non_gradable_count)}`;
    byId("hd-kpi-non-gradable-pct").textContent = pctText(meta?.cumulative_non_gradable_pct);
  }

  function filterLabsByHospital() {
    const hospitalId = byId("hd-filter-hospital")?.value || "";
    const labSelect = byId("hd-filter-lab");
    if (!labSelect) return;
    const options = Array.from(labSelect.options || []);
    options.forEach((option, idx) => {
      if (idx === 0) return;
      const optHospitalId = option.getAttribute("data-hospital-id") || "";
      option.hidden = Boolean(hospitalId) && optHospitalId !== hospitalId;
    });
    if (labSelect.selectedOptions[0]?.hidden) labSelect.value = "";
  }

  async function loadAll() {
    setLoading(true);
    const query = buildQuery();
    const suffix = query ? `?${query}` : "";
    try {
      const [diseaseRes, labDiseaseRes, userRes, rosterRes] = await Promise.all([
        fetchJson(`/analytics/api/hospital-dashboard/disease-view${suffix}`),
        fetchJson(`/analytics/api/hospital-dashboard/lab-disease-view${suffix}`),
        fetchJson(`/analytics/api/hospital-dashboard/user-view${suffix}`),
        fetchJson(`/analytics/api/hospital-dashboard/roster-view${suffix}`),
      ]);

      renderDiseaseRows(diseaseRes.data);
      renderLabDiseaseRows(labDiseaseRes.data);
      renderUserRows(userRes.data);
      renderRosterRows(rosterRes.data);
      renderKpis(diseaseRes.meta || {});
    } catch (error) {
      renderEmpty("hd-table-disease", 6, "Failed to load data");
      renderEmpty("hd-table-lab-disease", 8, "Failed to load data");
      renderEmpty("hd-table-user", 4, "Failed to load data");
      renderEmpty("hd-table-roster", 6, "Failed to load data");
      byId("hd-kpi-total").textContent = "-";
      byId("hd-kpi-non-gradable").textContent = "-";
      byId("hd-kpi-non-gradable-pct").textContent = "-";
      console.error("Hospital dashboard fetch failed", error);
    } finally {
      setLoading(false);
    }
  }

  function init() {
    const applyBtn = byId("hd-apply-filters");
    if (!applyBtn) return;

    byId("hd-filter-hospital")?.addEventListener("change", filterLabsByHospital);
    byId("hd-clear-filters")?.addEventListener("click", () => {
      byId("hd-filter-disease").value = "";
      byId("hd-filter-hospital").value = "";
      byId("hd-filter-lab").value = "";
      filterLabsByHospital();
      loadAll();
    });
    applyBtn.addEventListener("click", loadAll);
    filterLabsByHospital();
    loadAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
