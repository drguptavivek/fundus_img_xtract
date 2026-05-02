(function () {
  "use strict";

  var POLL_MS = 4000;
  var MAX_POLLS = 90;
  var pollCount = 0;
  var timer = null;

  function getRoot() {
    return document.getElementById("glaucoma-ai-results");
  }

  function shouldPoll(root) {
    return root && root.getAttribute("data-poll-active") === "1";
  }

  function textOrPending(value) {
    if (value === null || value === undefined || value === "") return "Pending";
    return String(value);
  }

  function setText(card, selector, value) {
    var node = card.querySelector(selector);
    if (node) node.textContent = value;
  }

  function setOptionalText(card, selector, labelSelector, value) {
    var node = card.querySelector(selector);
    var label = card.querySelector(labelSelector);
    var hasValue = value !== null && value !== undefined && value !== "";
    if (node) {
      node.textContent = hasValue ? String(value) : "";
      node.classList.toggle("d-none", !hasValue);
    }
    if (label) label.classList.toggle("d-none", !hasValue);
  }

  function setStatus(card, status) {
    var badge = card.querySelector("[data-result-status]");
    if (!badge) return;
    badge.textContent = status;
    badge.classList.remove("text-bg-success", "text-bg-warning", "text-bg-danger", "text-bg-secondary");
    if (status === "success") {
      badge.classList.add("text-bg-success");
    } else if (status === "failed") {
      badge.classList.add("text-bg-danger");
    } else if (status === "pending" || status === "queued" || status === "running") {
      badge.classList.add("text-bg-warning");
    } else {
      badge.classList.add("text-bg-secondary");
    }
  }

  function confidenceText(confidence) {
    if (confidence === null || confidence === undefined || confidence === "") return "Pending";
    var number = Number(confidence);
    if (!Number.isFinite(number)) return "Pending";
    return (number * 100).toFixed(2) + "%";
  }

  function updateViewerCaption(card, item, inference) {
    var link = card.querySelector("[data-result-viewer-link]");
    if (!link) return;
    var prediction = inference.predicted_class_name || inference.prediction || inference.predicted_class;
    link.setAttribute(
      "title",
      [
        item.filename || "Uploaded image",
        "Impression: " + textOrPending(inference.grade_impression),
        "Prediction: " + textOrPending(prediction),
        "Confidence: " + confidenceText(inference.confidence)
      ].join(" | ")
    );
  }

  function updateCard(item) {
    if (!item || !item.image_uuid) return false;
    var card = document.querySelector('[data-result-card][data-image-uuid="' + CSS.escape(item.image_uuid) + '"]');
    if (!card) return false;

    var inference = item.inference || {};
    var status = inference.status || "pending";
    setStatus(card, status);
    setText(card, "[data-result-impression]", textOrPending(inference.grade_impression));
    setText(
      card,
      "[data-result-prediction]",
      textOrPending(inference.predicted_class_name || inference.prediction || inference.predicted_class)
    );
    setText(card, "[data-result-confidence]", confidenceText(inference.confidence));
    setOptionalText(card, "[data-result-error]", "[data-result-error-label]", inference.error_code);
    setOptionalText(card, "[data-result-message]", "[data-result-message-label]", inference.message);
    updateViewerCaption(card, item, inference);
    return status === "pending" || status === "queued" || status === "running";
  }

  function schedule() {
    var root = getRoot();
    if (!shouldPoll(root) || pollCount >= MAX_POLLS) return;
    clearTimeout(timer);
    timer = setTimeout(refresh, POLL_MS);
  }

  function selectedNumber(form, name) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    if (!input) return null;
    var value = Number(input.value);
    return Number.isFinite(value) ? value : null;
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

    var projectId = selectedNumber(form, "project_id");
    var labUnitId = selectedNumber(form, "lab_unit_id");
    var cameraId = selectedNumber(form, "camera_id");
    var areaId = selectedNumber(form, "area_id");
    var matches = profiles.filter(function (profile) {
      return profileMatches(profile, projectId, labUnitId, cameraId, areaId);
    });
    var profileInput = form.querySelector('input[name="profile_id"]');
    if (profileInput) profileInput.value = matches.length === 1 ? String(matches[0].profile_id || "") : "";
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
    ["project_id", "lab_unit_id", "camera_id", "area_id"].forEach(function (name) {
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (input) {
        input.addEventListener("change", function () {
          updateMydriaticDefaults(form);
        });
      });
    });
  }

  function refresh() {
    var root = getRoot();
    if (!shouldPoll(root)) return;
    var url = root.getAttribute("data-results-json-url");
    if (!url) return;
    pollCount += 1;

    fetch(url, {
      method: "GET",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("Failed to refresh glaucoma AI results");
        return response.json();
      })
      .then(function (payload) {
        var updated = getRoot();
        if (!updated) return;
        var items = Array.isArray(payload.items) ? payload.items : [];
        var stillPolling = items.some(updateCard);
        updated.setAttribute("data-poll-active", stillPolling ? "1" : "0");
        var label = updated.querySelector("[data-last-updated]");
        if (label) label.textContent = "Updated " + new Date().toLocaleTimeString();
        schedule();
      })
      .catch(function () {
        schedule();
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initUploadOptions();
    schedule();
  });
})();
