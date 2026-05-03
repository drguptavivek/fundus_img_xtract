(function () {
  "use strict";

  var DEFAULT_FIELDS = ["project_id", "hospital_id", "lab_unit_id", "camera_id", "disease_id", "area_id"];

  function numberValue(selector, root) {
    var checked = root.querySelector(selector + ":checked");
    if (!checked) return null;
    var value = Number(checked.value);
    return Number.isFinite(value) ? value : null;
  }

  function setRadioVisible(input, visible) {
    var label = document.querySelector('label[for="' + CSS.escape(input.id) + '"]');
    input.disabled = !visible;
    input.classList.toggle("d-none", !visible);
    if (label) label.classList.toggle("d-none", !visible);
    if (!visible) input.checked = false;
  }

  function setOptionVisible(option, visible) {
    option.disabled = !visible;
    option.hidden = !visible;
    if (!visible) option.selected = false;
  }

  function idsFor(profiles, field) {
    var ids = new Set();
    profiles.forEach(function (profile) {
      var values = Array.isArray(profile[field]) ? profile[field] : [];
      values.forEach(function (value) { ids.add(Number(value)); });
    });
    return ids;
  }

  function storageKey(form) {
    return form.getAttribute("data-upload-defaults-storage-key") || "";
  }

  function localStorageRef() {
    try {
      return window.localStorage;
    } catch (err) {
      return null;
    }
  }

  function readSavedDefaults(form) {
    var key = storageKey(form);
    var storage = localStorageRef();
    if (!key || !storage) return {};
    try {
      var parsed = JSON.parse(storage.getItem(key) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function radioByValue(form, name, value) {
    var expected = String(value);
    var match = null;
    form.querySelectorAll('input[type="radio"][name="' + name + '"]').forEach(function (input) {
      if (input.value === expected) match = input;
    });
    return match;
  }

  function applySavedDefaults(form) {
    var defaults = readSavedDefaults(form);
    DEFAULT_FIELDS.forEach(function (name) {
      if (defaults[name] === null || defaults[name] === undefined || defaults[name] === "") return;
      var radio = radioByValue(form, name, defaults[name]);
      if (radio && !radio.disabled) radio.checked = true;
    });

    var mydriatic = form.querySelector('[name="is_mydriatic"]');
    if (mydriatic && typeof defaults.is_mydriatic === "boolean" && !mydriatic.disabled) {
      mydriatic.checked = defaults.is_mydriatic;
    }
  }

  function saveDefaults(form) {
    var key = storageKey(form);
    var storage = localStorageRef();
    if (!key || !storage) return;

    var defaults = {};
    DEFAULT_FIELDS.forEach(function (name) {
      var checked = form.querySelector('[name="' + name + '"]:checked');
      if (checked && !checked.disabled) defaults[name] = checked.value;
    });

    var mydriatic = form.querySelector('[name="is_mydriatic"]');
    if (mydriatic && !mydriatic.disabled) defaults.is_mydriatic = Boolean(mydriatic.checked);

    try {
      storage.setItem(key, JSON.stringify(defaults));
    } catch (err) {
      // Ignore storage quota or privacy-mode failures; upload behavior should continue.
    }
  }

  function scalarIdsFor(profiles, field) {
    var ids = new Set();
    profiles.forEach(function (profile) {
      if (profile[field] !== null && profile[field] !== undefined) ids.add(Number(profile[field]));
    });
    return ids;
  }

  function updateMydriatic(form, profiles) {
    var checkbox = form.querySelector('[name="is_mydriatic"]');
    var label = form.querySelector("[data-mydriatic-label], #mydriatic-label");
    if (!checkbox) return;

    var allowMydriatic = profiles.some(function (profile) { return Boolean(profile.allow_mydriatic); });
    var allowNonMydriatic = profiles.some(function (profile) { return Boolean(profile.allow_non_mydriatic); });
    checkbox.disabled = !allowMydriatic;
    if (!allowMydriatic) checkbox.checked = false;
    if (allowMydriatic && !allowNonMydriatic) checkbox.checked = true;
    if (label) label.textContent = checkbox.checked ? "Mydriatic" : "Non Mydriatic";
  }

  function updateForm(form) {
    var profiles = form._uploadProfiles || [];
    var projectId = numberValue('[name="project_id"]', form);
    var hospitalId = numberValue('[name="hospital_id"]', form);
    var labUnitId = numberValue('[name="lab_unit_id"]', form);
    var cameraId = numberValue('[name="camera_id"]', form);
    var diseaseId = numberValue('[name="disease_id"]', form);
    var areaId = numberValue('[name="area_id"]', form);

    var matches = profiles.filter(function (profile) {
      if (projectId && Number(profile.project_id) !== projectId) return false;
      if (labUnitId && Number(profile.lab_unit_id) !== labUnitId) return false;
      if (cameraId && Array.isArray(profile.camera_ids) && profile.camera_ids.indexOf(cameraId) === -1) return false;
      if (diseaseId && Array.isArray(profile.disease_ids) && profile.disease_ids.indexOf(diseaseId) === -1) return false;
      if (areaId && Array.isArray(profile.area_ids) && profile.area_ids.indexOf(areaId) === -1) return false;
      return true;
    });

    var projectIds = scalarIdsFor(profiles, "project_id");
    var labIds = scalarIdsFor(matches.length ? matches : profiles, "lab_unit_id");
    var cameraIds = idsFor(matches.length ? matches : profiles, "camera_ids");
    var diseaseIds = idsFor(matches.length ? matches : profiles, "disease_ids");
    var areaIds = idsFor(matches.length ? matches : profiles, "area_ids");

    form.querySelectorAll('[name="project_id"]').forEach(function (input) {
      setRadioVisible(input, projectIds.has(Number(input.value)));
    });
    form.querySelectorAll('[name="lab_unit_id"]').forEach(function (input) {
      var hospitalMatches = !hospitalId || String(input.dataset.hospitalId || "") === String(hospitalId);
      setRadioVisible(input, hospitalMatches && labIds.has(Number(input.value)));
    });
    form.querySelectorAll('[name="camera_id"]').forEach(function (input) {
      setRadioVisible(input, cameraIds.has(Number(input.value)));
    });
    form.querySelectorAll('select[name="camera_id"] option').forEach(function (option) {
      setOptionVisible(option, !option.value || cameraIds.has(Number(option.value)));
    });
    form.querySelectorAll('[name="disease_id"]').forEach(function (input) {
      setRadioVisible(input, diseaseIds.has(Number(input.value)));
    });
    form.querySelectorAll('[name="area_id"]').forEach(function (input) {
      setRadioVisible(input, areaIds.has(Number(input.value)));
    });

    updateMydriatic(form, matches.length ? matches : profiles);
    var submit = form.querySelector('[type="submit"]');
    if (submit) submit.disabled = profiles.length === 0;
  }

  function initForm(form) {
    var holder = form.querySelector("[data-upload-profiles]");
    try {
      form._uploadProfiles = JSON.parse((holder && holder.getAttribute("data-upload-profiles")) || "[]");
    } catch (err) {
      form._uploadProfiles = [];
    }
    applySavedDefaults(form);
    form.querySelectorAll('input[type="radio"], select, [name="is_mydriatic"]').forEach(function (input) {
      input.addEventListener("change", function () {
        updateForm(form);
        saveDefaults(form);
      });
    });
    var mydriatic = form.querySelector('[name="is_mydriatic"]');
    var label = form.querySelector("[data-mydriatic-label], #mydriatic-label");
    if (mydriatic && label) {
      mydriatic.addEventListener("change", function () {
        label.textContent = mydriatic.checked ? "Mydriatic" : "Non Mydriatic";
      });
    }
    updateForm(form);
    form.addEventListener("submit", function () { saveDefaults(form); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-upload-profile-form]").forEach(initForm);
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    event.target.querySelectorAll("[data-upload-profile-form]").forEach(initForm);
  });
})();
