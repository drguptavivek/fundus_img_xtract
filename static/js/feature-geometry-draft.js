(function () {
  const PREFIX = "geometry_draft";
  const VERSION = 1;
  const POLL_MS = 1000;

  function safeJsonParse(raw) {
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }

  function stableStringify(obj) {
    if (obj == null) return "";
    try {
      return JSON.stringify(obj);
    } catch (_) {
      return "";
    }
  }

  function buildKey(userId, taskUuid, slot) {
    const u = userId == null ? "anonymous" : String(userId);
    const t = taskUuid || "unknown_task";
    const s = slot || "unknown_slot";
    return `${PREFIX}:${u}:${t}:${s}`;
  }

  function getServerGeometryForTask(taskUuid) {
    if (!taskUuid) return null;
    if (window.linkedGradingData && window.linkedGradingData[taskUuid]) {
      return window.linkedGradingData[taskUuid].existingFeatureGeometry || null;
    }
    return window.existingFeatureGeometry || null;
  }

  function readDraft(key) {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = safeJsonParse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.version !== VERSION) return null;
    if (!parsed.payload || typeof parsed.payload !== "object") return null;
    return parsed;
  }

  function writeDraft(key, payloadObj) {
    const envelope = {
      version: VERSION,
      saved_at: Date.now(),
      payload: payloadObj,
    };
    window.localStorage.setItem(key, JSON.stringify(envelope));
  }

  function attachDraftForField(form, field, taskUuid, slot, userId) {
    const key = buildKey(userId, taskUuid, slot);
    const serverGeom = getServerGeometryForTask(taskUuid);
    const serverSer = stableStringify(serverGeom);
    let lastSeenValue = field.value || "";

    const existingDraft = readDraft(key);
    if (existingDraft) {
      const draftSer = stableStringify(existingDraft.payload);
      if (draftSer && serverSer && draftSer === serverSer) {
        window.localStorage.removeItem(key);
      }
    }

    function persistIfNeeded() {
      const nextValue = field.value || "";
      if (nextValue === lastSeenValue) return;
      lastSeenValue = nextValue;
      const parsed = safeJsonParse(nextValue);
      if (!parsed || typeof parsed !== "object") return;
      writeDraft(key, parsed);
    }

    field.addEventListener("input", persistIfNeeded);
    field.addEventListener("change", persistIfNeeded);

    const intervalId = window.setInterval(persistIfNeeded, POLL_MS);
    form.addEventListener("submit", function () {
      // Keep draft on submit; clear occurs on next load when it matches server payload.
      window.clearInterval(intervalId);
    });
  }

  function init() {
    const forms = document.querySelectorAll('form[data-grading-form="true"]');
    if (!forms.length) return;

    forms.forEach((form) => {
      const userId = window.currentUserId;
      const slotInput = form.querySelector('input[name="slot"]');
      const slot = (slotInput && slotInput.value) || window.currentSlot || "unknown_slot";
      const taskInput = form.querySelector('input[name="task_uuid"]');
      const defaultTaskUuid = (taskInput && taskInput.value) || window.taskId || null;

      const linkedFields = form.querySelectorAll('input[type="hidden"][data-feature-geometry-field]');
      if (linkedFields.length) {
        linkedFields.forEach((field) => {
          const taskUuid = field.getAttribute("data-feature-geometry-field");
          attachDraftForField(form, field, taskUuid, slot, userId);
        });
        return;
      }

      const field = form.querySelector('input[type="hidden"][name="feature_geometry_json"]');
      if (field) {
        attachDraftForField(form, field, defaultTaskUuid, slot, userId);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
