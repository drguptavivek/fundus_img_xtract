(function () {
  "use strict";

  function selectedNumber(form, name) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    if (!input) return null;
    var value = Number(input.value);
    return Number.isFinite(value) ? value : null;
  }

  function setGroupRadio(form, name, value) {
    form.querySelectorAll('input[name="' + name + '"]').forEach(function (input) {
      input.checked = String(input.value) === String(value);
    });
  }

  function optionValues(profile, key) {
    return Array.isArray(profile[key]) ? profile[key].map(Number) : [];
  }

  function setRadioVisible(input, visible) {
    var label = input.id ? document.querySelector('label[for="' + CSS.escape(input.id) + '"]') : null;
    input.disabled = !visible;
    if (!visible) input.checked = false;
    if (label) label.classList.toggle("d-none", !visible);
  }

  function firstVisibleRadio(form, name) {
    return Array.prototype.find.call(form.querySelectorAll('input[name="' + name + '"]'), function (input) {
      return !input.disabled;
    });
  }

  function ensureSelection(form, name) {
    var selected = form.querySelector('input[name="' + name + '"]:checked');
    if (selected && !selected.disabled) return;
    var first = firstVisibleRadio(form, name);
    if (first) first.checked = true;
  }

  function setMydriaticOption(form, value, allowed, checked) {
    var input = form.querySelector('input[name="is_mydriatic"][value="' + value + '"]');
    if (!input) return;
    input.disabled = !allowed;
    if (checked && allowed) input.checked = true;
  }

  function profileMatches(profile, projectId, labUnitId, cameraId, areaId) {
    if (projectId && profile.project_id !== projectId) return false;
    if (labUnitId && profile.lab_unit_id !== labUnitId) return false;
    if (cameraId && Array.isArray(profile.camera_ids) && profile.camera_ids.indexOf(cameraId) === -1) return false;
    if (areaId && Array.isArray(profile.area_ids) && profile.area_ids.indexOf(areaId) === -1) return false;
    return true;
  }

  function updateMydriaticDefaults(form) {
    var holder = form.querySelector("[data-upload-profiles]");
    if (!holder) return;
    var profiles = [];
    try {
      profiles = JSON.parse(holder.getAttribute("data-upload-profiles") || "[]");
    } catch (err) {
      return;
    }
    if (!Array.isArray(profiles) || profiles.length === 0) return;

    var selectedProfileId = selectedNumber(form, "profile_id");
    var matches = profiles.filter(function (profile) {
      return !selectedProfileId || Number(profile.profile_id) === selectedProfileId;
    });
    if (matches.length === 1) {
      var profile = matches[0];
      setGroupRadio(form, "project_id", profile.project_id);
      setGroupRadio(form, "lab_unit_id", profile.lab_unit_id);
      var cameraIds = optionValues(profile, "camera_ids");
      var areaIds = optionValues(profile, "area_ids");
      form.querySelectorAll('input[name="camera_id"]').forEach(function (input) {
        setRadioVisible(input, cameraIds.indexOf(Number(input.value)) !== -1);
      });
      form.querySelectorAll('input[name="area_id"]').forEach(function (input) {
        setRadioVisible(input, areaIds.indexOf(Number(input.value)) !== -1);
      });
      ensureSelection(form, "camera_id");
      ensureSelection(form, "area_id");
    } else {
      form.querySelectorAll('input[name="camera_id"], input[name="area_id"]').forEach(function (input) {
        setRadioVisible(input, true);
      });
    }
    var projectId = selectedNumber(form, "project_id");
    var labUnitId = selectedNumber(form, "lab_unit_id");
    var cameraId = selectedNumber(form, "camera_id");
    var areaId = selectedNumber(form, "area_id");
    matches = matches.filter(function (profile) {
      return profileMatches(profile, projectId, labUnitId, cameraId, areaId);
    });
    if (matches.length === 0) return;

    var allowMydriatic = matches.some(function (profile) { return Boolean(profile.allow_mydriatic); });
    var allowNonMydriatic = matches.some(function (profile) { return Boolean(profile.allow_non_mydriatic); });
    var selectedProfile = matches.length === 1 ? matches[0] : null;
    var defaultIsMydriatic = selectedProfile
      ? Boolean(selectedProfile.default_is_mydriatic)
      : allowMydriatic && !allowNonMydriatic;

    setMydriaticOption(form, "false", allowNonMydriatic, !defaultIsMydriatic);
    setMydriaticOption(form, "true", allowMydriatic, defaultIsMydriatic);
  }

  function initUploadOptions() {
    var form = document.querySelector(".glaucoma-ai-upload-form");
    if (!form) return;
    updateMydriaticDefaults(form);
    ["profile_id", "project_id", "lab_unit_id", "camera_id", "area_id"].forEach(function (name) {
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (input) {
        input.addEventListener("change", function () {
          updateMydriaticDefaults(form);
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initUploadOptions();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (
      event.target
      && (event.target.id === "glaucoma-ai-workspace" || event.target.id === "glaucoma-ai-form-panel")
    ) {
      initUploadOptions();
    }
  });
})();
