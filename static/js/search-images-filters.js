(() => {
  function parseGradeMap(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  let cachedGradeMap = null;

  async function loadGradeMap(elementId, apiUrl) {
    if (cachedGradeMap) return cachedGradeMap;
    const parsed = parseGradeMap(elementId);
    if (Object.keys(parsed).length) {
      cachedGradeMap = parsed;
      return cachedGradeMap;
    }
    try {
      const res = await fetch(apiUrl || "/api/diseases-with-gradings");
      if (!res.ok) {
        return {};
      }
      const data = await res.json();
      const map = {};
      (data?.diseases || []).forEach((d) => {
        map[String(d.id)] = (d.gradings || []).map((g) => g.impression).filter(Boolean);
      });
      cachedGradeMap = map;
      return cachedGradeMap;
    } catch (e) {
      return {};
    }
  }

  function selectedValues(selector) {
    return Array.from(document.querySelectorAll(selector))
      .filter((el) => el.checked)
      .map((el) => el.value);
  }

  function rebuildGradeOptions(containerId, nameAttr, selectedValues, grades, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = "";
    const values = Array.isArray(grades) ? [...grades] : [];
    if (options.includeUnresolved && !values.includes("Unresolved")) {
      values.push("Unresolved");
    }
    if (!values.length) {
      container.innerHTML = '<div class="text-muted small">Select a disease to load grades.</div>';
      return;
    }
    values.forEach((grade, idx) => {
      const wrapper = document.createElement("div");
      wrapper.className = "form-check";
      const input = document.createElement("input");
      input.className = "form-check-input";
      input.type = "checkbox";
      input.name = nameAttr;
      input.id = `${containerId}_${idx}`;
      input.value = grade;
      if (selectedValues.includes(grade)) {
        input.checked = true;
      }
      const label = document.createElement("label");
      label.className = "form-check-label";
      label.htmlFor = input.id;
      label.textContent = grade;
      wrapper.appendChild(input);
      wrapper.appendChild(label);
      container.appendChild(wrapper);
    });
  }

  function toggleReviewControls(hasReviewSelectId, reviewContainerId) {
    const select = document.getElementById(hasReviewSelectId);
    const container = document.getElementById(reviewContainerId);
    if (!select || !container) return;
    const enable = select.value === "yes";
    container.querySelectorAll("input[type='checkbox']").forEach((el) => {
      el.disabled = !enable;
      if (!enable) el.checked = false;
    });
  }

  function toggleAiControls(hasAiSelectId) {
    const select = document.getElementById(hasAiSelectId);
    const enable = select && select.value === "yes";
    document.querySelectorAll(".ai-dependent").forEach((el) => {
      el.disabled = !enable;
      if (!enable) {
        if (el.tagName === "SELECT") {
          Array.from(el.options).forEach((opt) => (opt.selected = false));
        } else if (el.type === "checkbox") {
          el.checked = false;
        }
      }
    });
  }

  function refreshGradeBlocks(cfg, diseaseId, gradeMap) {
    const grades = gradeMap[String(diseaseId)] || [];
    const finalBasisSelect = document.getElementById(cfg.finalGradeBasisSelectId);
    const includeUnresolved = finalBasisSelect && window.FinalGradeBasis
      ? window.FinalGradeBasis.basisUsesUnresolved(finalBasisSelect.value)
      : false;
    rebuildGradeOptions(cfg.containers.resident, "resident_grade", selectedValues('input[name="resident_grade"]:checked'), grades);
    rebuildGradeOptions(cfg.containers.resident2, "resident2_grade", selectedValues('input[name="resident2_grade"]:checked'), grades);
    rebuildGradeOptions(cfg.containers.arbitrator, "arbitrator_grade", selectedValues('input[name="arbitrator_grade"]:checked'), grades);
    rebuildGradeOptions(cfg.containers.review, "review_grade", selectedValues('input[name="review_grade"]:checked'), grades);
    rebuildGradeOptions(cfg.containers.final, "final_grade", selectedValues('input[name="final_grade"]:checked'), grades, { includeUnresolved });
    rebuildGradeOptions(cfg.containers.ai, "ai_grade", selectedValues('input[name="ai_grade"]:checked'), grades);
  }

  async function init(config) {
    const gradeMap = await loadGradeMap(config.gradeMapElementId, config.apiUrl);
    const diseaseSelect = document.getElementById(config.diseaseSelectId);
    if (diseaseSelect) {
      diseaseSelect.addEventListener("change", (e) => {
        refreshGradeBlocks(config, e.target.value, gradeMap);
      });
      if (diseaseSelect.value) {
        refreshGradeBlocks(config, diseaseSelect.value, gradeMap);
      }
    }

    if (config.finalGradeBasisSelectId) {
      const basisSelect = document.getElementById(config.finalGradeBasisSelectId);
      if (basisSelect) {
        window.FinalGradeBasis.initSelect(basisSelect, () => {
          if (diseaseSelect && diseaseSelect.value) {
            refreshGradeBlocks(config, diseaseSelect.value, gradeMap);
          }
        });
      }
    }

    if (config.hasReviewSelectId && config.containers.review) {
      const select = document.getElementById(config.hasReviewSelectId);
      if (select) {
        select.addEventListener("change", () => toggleReviewControls(config.hasReviewSelectId, config.containers.review));
        toggleReviewControls(config.hasReviewSelectId, config.containers.review);
      }
    }

    if (config.hasAiSelectId) {
      const select = document.getElementById(config.hasAiSelectId);
      if (select) {
        select.addEventListener("change", () => toggleAiControls(config.hasAiSelectId));
        toggleAiControls(config.hasAiSelectId);
      }
    }
  }

  window.SearchImagesFilters = { init };
})();
