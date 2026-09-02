/* Grading workbench session controller: lease heartbeat, draft autosave, submit / save-next,
 * target navigation. Extracted from templates/grading/workbench.html; reads its per-session
 * values from the [data-workbench-config] JSON block rendered by grading/_workbench_body.html.
 * Shared by the web workbench and the grader PWA. */
(function () {
  const root = document.getElementById('grading-workbench');
  const config = JSON.parse(root.querySelector('[data-workbench-config]').textContent);
  const token = config.sessionToken;
  const submissionIdempotencyKey = config.submissionIdempotencyKey;
  const fingerprint = config.configurationFingerprint;
  const sessionUuid = root.dataset.sessionUuid;
  const generation = root.dataset.tokenGeneration;
  const messageBox = root.querySelector('[data-workbench-message]');
  const panels = Array.from(root.querySelectorAll('[data-task-uuid]'));
  const imagePanels = panels.filter(panel => panel.dataset.targetLevel === 'image');
  const editablePanels = panels.filter(panel => panel.dataset.readOnly !== 'true');
  const editableImagePanels = editablePanels.filter(panel => panel.dataset.targetLevel === 'image');
  const encounterPanels = panels.filter(panel => panel.dataset.targetLevel === 'encounter');
  const contextualSubmission = Boolean(encounterPanels.length && imagePanels.length);
  const submitActionGroups = Array.from(root.querySelectorAll('[data-workbench-submit-actions]'));
  const submitButtons = Array.from(root.querySelectorAll('[data-submit-workbench]'));
  const nextDiseaseButtons = Array.from(root.querySelectorAll('[data-next-disease]'));
  const submitOverlay = root.querySelector('[data-workbench-submit-overlay]');
  const submitOverlayMessage = root.querySelector('[data-workbench-submit-overlay-message]');
  const draftStatus = root.querySelector('[data-draft-status]');
  const draftStatusIcons = {
    'Draft ready': 'fa-solid fa-check',
    'Draft saved': 'fa-solid fa-check',
    'Draft restored': 'fa-solid fa-check',
    'Saving draft…': 'fa-solid fa-spinner fa-spin',
    'Unsaved changes': 'fa-solid fa-pen',
    'Draft not saved': 'fa-solid fa-triangle-exclamation text-danger',
  };
  function setDraftStatus(text) {
    draftStatus.querySelector('.gwb-full').textContent = text;
    draftStatus.querySelector('.gwb-short').className = `gwb-short ${draftStatusIcons[text] || 'fa-solid fa-circle-info'}`;
    draftStatus.title = text;
  }
  const workbenchForm = root.querySelector('[data-workbench-form]');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const headers = {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrf,
    'X-Workbench-Token': token,
    'X-Workbench-Generation': generation
  };

  async function loadPanelMedia(panel) {
    const viewer = panel?.querySelector('.imggr-viewer-root');
    const image = viewer?.querySelector('.imggr-main-img');
    if (!viewer || !image) return;

    const deferredUrl = image.dataset.src;
    const imageReady = deferredUrl
      ? new Promise(resolve => {
          const finish = () => resolve();
          image.addEventListener('load', finish, {once: true});
          image.addEventListener('error', finish, {once: true});
          image.src = deferredUrl;
          image.removeAttribute('data-src');
          if (image.complete) resolve();
        })
      : Promise.resolve();
    const metadataReady = Promise.resolve(
      viewer.__imggrState?.hydrateMetadata?.()
    ).catch(() => undefined);
    await Promise.all([imageReady, metadataReady]);
    viewer.dataset.imggrDeferred = 'false';
  }

  async function preloadRemainingImagesSerially() {
    for (const panel of imagePanels) {
      if (panel.classList.contains('active')) continue;
      await loadPanelMedia(panel);
    }
  }

  window.addEventListener('load', () => {
    preloadRemainingImagesSerially().catch(() => undefined);
  }, {once: true});

  function selectedGrade(panel) {
    return panel.querySelector('[data-grade-option]:checked')?.value || '';
  }

  function sanitizeGuidelineHtml(value) {
    const documentFragment = new DOMParser().parseFromString(value || '', 'text/html');
    const allowedTags = new Set(['UL', 'OL', 'LI', 'P', 'BR', 'STRONG', 'EM', 'B', 'I']);
    Array.from(documentFragment.body.querySelectorAll('*')).forEach(element => {
      if (!allowedTags.has(element.tagName)) {
        element.replaceWith(...Array.from(element.childNodes));
        return;
      }
      Array.from(element.attributes).forEach(attribute => element.removeAttribute(attribute.name));
    });
    return documentFragment.body.innerHTML;
  }

  let submitting = false;
  let submissionOutcomeUnknown = false;
  let activePanelIndex = panels.findIndex(panel => panel.classList.contains('active'));
  let draftDirty = false;
  let draftTimer = null;
  let draftSavePromise = null;

  setDraftStatus(panels.some(
    panel => window.linkedGradingData[panel.dataset.taskUuid]?.hasDraft
  ) ? 'Draft restored' : 'Draft ready');

  function collectObservations() {
    const observations = {};
    editablePanels.forEach(panel => {
      const taskUuid = panel.dataset.taskUuid;
      const selected = selectedGrade(panel);
      const geometryRaw = panel.querySelector('[data-feature-geometry-field]').value;
      observations[taskUuid] = {
        disease_grading_id: selected ? Number(selected) : null,
        comment: panel.querySelector('textarea').value,
        selected_feature_ids: Array.from(
          panel.querySelectorAll('input[name^="selected_features_"]:checked')
        ).map(item => Number(item.value)),
        annotation_policy_revision: Number(
          panel.querySelector('input[name^="annotation_policy_revision_"]').value
        ),
        feature_geometry: geometryRaw ? JSON.parse(geometryRaw) : null
      };
    });
    return observations;
  }

  async function flushDraft() {
    window.clearTimeout(draftTimer);
    draftTimer = null;
    if (submitting || (!draftDirty && !draftSavePromise)) return;
    if (draftSavePromise) {
      await draftSavePromise;
      if (draftDirty && !submitting) return flushDraft();
      return;
    }
    draftDirty = false;
    setDraftStatus('Saving draft…');
    const body = {
      configuration_fingerprint: fingerprint,
      observations: collectObservations()
    };
    draftSavePromise = api(`/api/grading/workbench/sessions/${sessionUuid}/draft`, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
    let saveFailed = false;
    let retryDraft = false;
    try {
      await draftSavePromise;
      setDraftStatus('Draft saved');
    } catch (error) {
      saveFailed = true;
      retryDraft = Boolean(error.transient);
      draftDirty = true;
      setDraftStatus('Draft not saved');
      showMessage(error.message, 'warning');
      if (error.reloadRequired) reloadForConfigurationChange(error.message);
    } finally {
      draftSavePromise = null;
    }
    if (draftDirty && !submitting) {
      if (retryDraft) scheduleDraft(2000);
      else if (!saveFailed) scheduleDraft();
    }
  }

  function scheduleDraft(delay = 450) {
    if (submitting) return;
    draftDirty = true;
    setDraftStatus('Unsaved changes');
    window.clearTimeout(draftTimer);
    draftTimer = window.setTimeout(flushDraft, delay);
  }

  function updateSubmissionControls() {
    const activePanel = panels[activePanelIndex];
    const nextPanel = panels[activePanelIndex + 1];
    const hasNextDisease = activePanel?.dataset.targetLevel === 'encounter'
      && Boolean(activePanel.dataset.scopeId)
      && Boolean(nextPanel?.dataset.scopeId)
      && activePanel.dataset.scopeId !== nextPanel.dataset.scopeId;
    const showActions = activePanel?.dataset.readOnly !== 'true'
      && (!contextualSubmission || activePanel?.dataset.targetLevel === 'encounter');
    const allTargetsGraded = editablePanels.every(panel => Boolean(selectedGrade(panel)));
    submitActionGroups.forEach(group => {
      group.classList.toggle('d-none', !showActions || group.closest('[data-task-uuid]') !== activePanel);
    });
    submitButtons.forEach(button => {
      button.disabled = submissionOutcomeUnknown
        || submitting
        || !allTargetsGraded;
    });
    nextDiseaseButtons.forEach(button => {
      const isActiveTransition = hasNextDisease
        && button.closest('[data-task-uuid]') === activePanel;
      button.classList.toggle('d-none', !isActiveTransition);
      button.disabled = submissionOutcomeUnknown
        || submitting
        || !isActiveTransition
        || !selectedGrade(activePanel);
      if (isActiveTransition) {
        button.textContent = `Next Disease: ${nextPanel.dataset.diseaseName}`;
      }
    });
  }

  function showMessage(message, level = 'danger') {
    messageBox.textContent = message;
    messageBox.className = `alert alert-${level} py-2`;
  }

  function showSubmissionOutcomeUnknown() {
    messageBox.className = 'alert alert-warning py-2';
    const message = document.createElement('span');
    message.textContent = 'Submission status is unknown. Reload to read the saved server state; this form will not submit again automatically. ';
    const reloadButton = document.createElement('button');
    reloadButton.type = 'button';
    reloadButton.className = 'btn btn-sm btn-outline-dark ms-2';
    reloadButton.textContent = 'Reload status';
    reloadButton.addEventListener('click', () => window.location.reload());
    messageBox.replaceChildren(message, reloadButton);
  }

  // A history-restored form is stale. Hide its cached overlay and read current
  // state with GET; never leave the old form available for another POST.
  window.SubmissionGuard.reloadOnHistoryRestore();

  function updateProgress() {
    const graded = editablePanels.filter(panel => Boolean(selectedGrade(panel))).length;
    const total = editablePanels.length;
    const gradedImages = editableImagePanels.filter(panel => Boolean(selectedGrade(panel))).length;
    const progressBadge = root.querySelector('[data-workbench-progress]');
    progressBadge.querySelector('.gwb-full').textContent =
      `${gradedImages} of ${editableImagePanels.length} images graded · ${editableImagePanels.length - gradedImages} pending · ${graded} of ${total} targets`;
    progressBadge.querySelector('.gwb-short').textContent = `${gradedImages}/${editableImagePanels.length}`;
    panels.forEach((panel, index) => {
      root.querySelector(`[data-workbench-target="${index}"]`)?.classList.toggle('is-graded', Boolean(selectedGrade(panel)));
      const grade = window.linkedGradingData[panel.dataset.taskUuid]?.features.find(
        item => String(item.id) === String(selectedGrade(panel))
      );
      root.querySelectorAll(`[data-encounter-image-grade][data-source-task-uuid="${panel.dataset.taskUuid}"]`).forEach(item => {
        item.textContent = grade?.impression || 'Pending';
        item.classList.toggle('text-bg-danger', !grade);
        item.classList.toggle('text-bg-success', Boolean(grade));
        item.closest('[data-encounter-image-navigate]')?.classList.toggle('is-pending', !grade);
      });
    });
    updateSubmissionControls();
  }

  function renderFeatures(panel) {
    const fieldset = panel.querySelector('[data-feature-fieldset]');
    const host = panel.querySelector('[data-feature-options]');
    const guidelines = panel.querySelector('[data-grade-guidelines]');
    const data = window.linkedGradingData[panel.dataset.taskUuid];
    const grade = data.features.find(item => String(item.id) === String(selectedGrade(panel)));
    host.innerHTML = '';
    guidelines.innerHTML = sanitizeGuidelineHtml(grade?.guidelines || '');
    const selected = new Set((data.existingSelectedFeatures || []).map(Number));
    (grade?.features || []).forEach(feature => {
      const id = `feature-${panel.dataset.taskUuid}-${feature.id}`;
      const row = document.createElement('div');
      row.className = 'form-check';
      row.innerHTML = `<input class="form-check-input" type="checkbox" name="selected_features_${panel.dataset.taskUuid}" id="${id}" value="${feature.id}">
        <label class="form-check-label" for="${id}"></label>`;
      row.querySelector('input').checked = selected.has(Number(feature.id));
      row.querySelector('input').disabled = data.readOnly;
      row.querySelector('label').textContent = feature.label;
      host.appendChild(row);
    });
    fieldset.classList.toggle('d-none', !(grade?.features || []).length);
    document.dispatchEvent(new CustomEvent('fgw:features-changed'));
  }

  panels.forEach(panel => {
    panel.querySelectorAll('[data-grade-option]').forEach(option => {
      option.addEventListener('change', () => {
        window.linkedGradingData[panel.dataset.taskUuid].existingSelectedFeatures = [];
        renderFeatures(panel);
        updateProgress();
        const fieldset = panel.querySelector('[data-feature-fieldset]');
        if (fieldset && !fieldset.classList.contains('d-none')) {
          window.requestAnimationFrame(() => fieldset.scrollIntoView({block: 'nearest', behavior: 'smooth'}));
        }
      });
    });
    renderFeatures(panel);
    panel.querySelector('[data-clear-selection]')?.addEventListener('click', () => {
      panel.querySelectorAll('[data-grade-option], input[name^="selected_features_"]').forEach(input => {
        input.checked = false;
      });
      const data = window.linkedGradingData[panel.dataset.taskUuid];
      data.existingSelectedFeatures = [];
      panel.querySelector('[data-feature-geometry-field]').value = '';
      renderFeatures(panel);
      updateProgress();
      scheduleDraft(0);
    });
    panel.querySelectorAll('[data-evidence-select]').forEach(button => {
      button.addEventListener('click', () => {
        const viewer = panel.querySelector('[data-evidence-viewer]');
        const state = viewer?.__imggrState;
        const image = viewer?.querySelector('.imggr-main-img');
        if (state?.setImage) {
          state.setImage({
            imageUuid: button.dataset.imageUuid,
            mediaUrl: button.dataset.mediaUrl,
            alt: button.dataset.imageAlt
          });
        } else if (viewer && image) {
          viewer.dataset.encId = button.dataset.imageUuid;
          image.src = button.dataset.mediaUrl;
          image.alt = button.dataset.imageAlt;
        }
        panel.querySelectorAll('[data-evidence-select]').forEach(item => {
          const selected = item === button;
          item.classList.toggle('border-primary', selected);
          item.setAttribute('aria-pressed', selected ? 'true' : 'false');
        });
      });
    });
  });
  updateProgress();

  workbenchForm.addEventListener('input', event => {
    if (
      event.target.matches('textarea')
      || event.target.matches('[data-feature-geometry-field]')
    ) scheduleDraft();
  });
  workbenchForm.addEventListener('change', event => {
    if (
      event.target.matches('[data-grade-option]')
      || event.target.matches('textarea')
      || event.target.matches('input[name^="selected_features_"]')
      || event.target.matches('[data-feature-geometry-field]')
    ) scheduleDraft(0);
  });

  root.querySelector('[data-workbench-dashboard]').addEventListener('click', async event => {
    event.preventDefault();
    const destination = event.currentTarget.href;
    await flushDraft();
    if (draftSavePromise) await draftSavePromise;
    if (!draftDirty) window.location.assign(destination);
  });

  const carouselElement = root.querySelector('#workbench-panels');
  let carousel = null;
  function relocateViewerModals() {
    // Transformed carousel items create a containing/stacking context that can
    // leave a visible modal unable to receive Bootstrap dismiss interactions.
    carouselElement.querySelectorAll('.modal').forEach(modal => document.body.appendChild(modal));
  }
  function initializeCarousel() {
    relocateViewerModals();
    if (window.bootstrap?.Carousel) {
      carousel = window.bootstrap.Carousel.getOrCreateInstance(
        carouselElement,
        {interval: false, wrap: false, touch: false}
      );
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeCarousel, {once: true});
  } else {
    initializeCarousel();
  }
  carouselElement.addEventListener('slid.bs.carousel', event => {
    activePanelIndex = event.to;
    root.querySelectorAll('[data-workbench-target]').forEach((item, index) => {
      item.classList.toggle('active', index === event.to);
      if (index === event.to) {
        const pager = item.parentElement;
        pager.scrollTo({left: item.offsetLeft - (pager.clientWidth - item.offsetWidth) / 2, behavior: 'smooth'});
      }
    });
    const activeViewer = panels[event.to]?.querySelector('.imggr-viewer-root');
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      activeViewer?.__imggrState?.refreshViewportSize?.();
    }));
    updateSubmissionControls();
  });
  root.querySelectorAll('[data-workbench-target]').forEach(button => {
    button.addEventListener('click', () => carousel?.to(Number(button.dataset.workbenchTarget)));
  });
  const narrowLayout = window.matchMedia('(max-width: 991.98px)');
  function scrollImageIntoView(panel, behavior = 'smooth') {
    if (!narrowLayout.matches) return;
    const target = panel?.querySelector('.imggr-main-wrap');
    const row = target?.closest('.gwb-panel-row');
    if (!target || !row) return;
    const offset = target.getBoundingClientRect().top - row.getBoundingClientRect().top + row.scrollTop;
    row.scrollTo({top: offset, behavior});
  }
  window.addEventListener('load', () => scrollImageIntoView(panels[activePanelIndex]), {once: true});
  // Pre-position the incoming panel while it is still sliding in so the
  // image top is already in view when the transition ends, with no visible jump.
  carouselElement.addEventListener('slide.bs.carousel', event => {
    window.requestAnimationFrame(() => scrollImageIntoView(panels[event.to], 'auto'));
  });
  if (window.matchMedia('(max-width: 767.98px)').matches) {
    root.querySelectorAll('.imggr-annot-sidebar').forEach(sidebar => sidebar.classList.add('is-collapsed'));
    root.querySelectorAll('[data-annot-toggle]').forEach(button => {
      button.setAttribute('aria-pressed', 'false');
      button.classList.remove('active');
    });
  }
  root.querySelectorAll('[data-annot-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const viewer = button.closest('.linked-grading-panel')?.querySelector('.imggr-viewer-root');
      const sidebar = viewer?.querySelector('.imggr-annot-sidebar');
      if (!sidebar) return;
      const collapsed = sidebar.classList.toggle('is-collapsed');
      button.setAttribute('aria-pressed', String(!collapsed));
      button.classList.toggle('active', !collapsed);
      window.requestAnimationFrame(() => viewer.__imggrState?.refreshViewportSize?.());
    });
  });
  root.querySelectorAll('[data-image-navigate]').forEach(button => {
    button.addEventListener('click', () => {
      const currentPanel = button.closest('[data-task-uuid]');
      const panelIndex = panels.indexOf(currentPanel);
      const nextPanelIndex = panelIndex + (button.dataset.imageNavigate === 'prev' ? -1 : 1);
      if (panels[nextPanelIndex]) carousel?.to(nextPanelIndex);
    });
  });
  root.querySelectorAll('[data-encounter-image-navigate]').forEach(button => {
    button.addEventListener('click', () => {
      const imagePanel = panels.find(
        panel => panel.dataset.taskUuid === button.dataset.encounterImageNavigate
      );
      if (imagePanel) carousel?.to(panels.indexOf(imagePanel));
    });
  });
  nextDiseaseButtons.forEach(button => {
    button.addEventListener('click', async () => {
      const currentPanel = button.closest('[data-task-uuid]');
      const panelIndex = panels.indexOf(currentPanel);
      const nextPanel = panels[panelIndex + 1];
      if (
        currentPanel?.dataset.targetLevel !== 'encounter'
        || !currentPanel.dataset.scopeId
        || !nextPanel?.dataset.scopeId
        || currentPanel.dataset.scopeId === nextPanel.dataset.scopeId
      ) return;
      await flushDraft();
      if (!draftDirty) carousel?.to(panelIndex + 1);
    });
  });

  const expandButton = root.querySelector('[data-workbench-expand]');
  document.body.classList.toggle('gwb-expanded-lock', root.classList.contains('is-expanded'));
  expandButton.addEventListener('click', () => {
    const expanded = root.classList.toggle('is-expanded');
    document.body.classList.toggle('gwb-expanded-lock', expanded);
    expandButton.setAttribute('aria-pressed', expanded ? 'true' : 'false');
    expandButton.setAttribute('aria-label', expanded ? 'Restore grading view' : 'Expand grading view');
    expandButton.title = expanded ? 'Restore grading view' : 'Expand grading view';
    root.querySelector('[data-workbench-expand-icon]').className =
      expanded ? 'fa-solid fa-compress' : 'fa-solid fa-expand';
    window.setTimeout(() => window.dispatchEvent(new Event('resize')), 0);
  });

  root.querySelectorAll('[data-workbench-navigate]').forEach(button => {
    button.addEventListener('click', () => {
      const direction = button.dataset.workbenchNavigate;
      if (panels.length > 1 && carousel) {
        direction === 'prev' ? carousel.prev() : carousel.next();
      }
    });
  });

  async function api(path, options) {
    let response;
    try {
      response = await fetch(path, {...options, headers});
    } catch (_) {
      const error = new Error('The grading server is temporarily unavailable. Your unsaved draft will retry.');
      error.code = 'network_error';
      error.transient = true;
      throw error;
    }

    const rawBody = await response.text();
    let payload;
    try {
      payload = JSON.parse(rawBody);
    } catch (_) {
      const redirectedToLogin = response.redirected && /\/login(?:[/?#]|$)/.test(response.url);
      const transient = response.status >= 500 || response.status === 429;
      const message = redirectedToLogin
        ? 'Your login session has expired. Reload this page and sign in again.'
        : transient
          ? 'The grading server is restarting or temporarily unavailable. Your unsaved draft will retry.'
          : `The grading server returned an unexpected response (HTTP ${response.status}). Please reload before submitting.`;
      const error = new Error(message);
      error.code = redirectedToLogin ? 'authentication_required' : 'non_json_response';
      error.transient = transient;
      throw error;
    }
    if (!response.ok || !payload.success) {
      const error = new Error(payload.error?.message || 'Workbench request failed.');
      error.code = payload.error?.code || 'workbench_error';
      error.reloadRequired = Boolean(payload.error?.reload_required);
      error.transient = response.status >= 500 || response.status === 429;
      throw error;
    }
    return payload;
  }

  function reloadForConfigurationChange(message) {
    clearInterval(heartbeatTimer);
    showMessage(message || 'Grading options changed. Reloading this package…', 'warning');
    window.setTimeout(() => window.location.reload(), 900);
  }

  workbenchForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting) return;
    const firstIncompletePanel = editablePanels.find(panel => !selectedGrade(panel));
    if (firstIncompletePanel) {
      carousel?.to(panels.indexOf(firstIncompletePanel));
      const targetName = firstIncompletePanel.querySelector('.gwb-grade-card h2')?.textContent.trim();
      showMessage(`Select a grade for ${targetName || 'every target'} before submitting.`, 'warning');
      return;
    }
    const action = event.submitter?.value || 'save_close';
    const clickedButton = event.submitter;
    const submission = window.SubmissionGuard.acquire(workbenchForm, {
      submitter: clickedButton,
      controls: submitButtons,
      busyLabel: 'Saving…',
      overlay: submitOverlay,
      overlayMessage: submitOverlayMessage,
      message: action === 'save_next'
        ? 'Saving grades and loading the next case…'
        : 'Saving grades and closing the workbench…'
    });
    if (!submission) return;
    submitting = true;
    window.clearTimeout(draftTimer);
    showMessage('Saving grades…', 'info');
    clearInterval(heartbeatTimer);
    try {
      const body = {
        action,
        idempotency_key: submissionIdempotencyKey,
        configuration_fingerprint: fingerprint,
        package_revision: config.packageRevision,
        observations: collectObservations()
      };
      const result = await api(`/api/grading/workbench/sessions/${sessionUuid}/submit`, {
        method: 'POST', body: JSON.stringify(body)
      });
      showMessage(
        action === 'save_next' ? 'Grades saved. Opening the next case…' : 'Grades saved.',
        'success'
      );
      if (action === 'save_next' && result.next_workbench?.workbench) {
        const nextUuid = result.next_workbench.workbench.lease?.session_uuid;
        const nextUrl = config.workbenchUrlTemplate && nextUuid
          ? config.workbenchUrlTemplate.replace('{uuid}', encodeURIComponent(nextUuid))
          : result.next_workbench.workbench_url;
        window.setTimeout(() => window.location.assign(nextUrl), 450);
      } else {
        if (action === 'save_next') {
          showMessage('Grades saved. No additional eligible case is available.', 'success');
        }
        window.setTimeout(() => window.location.assign(config.dashboardUrl), 900);
      }
    } catch (error) {
      submitting = false;
      submission.release();
      if (error.transient || error.code === 'network_error') {
        submissionOutcomeUnknown = true;
        updateSubmissionControls();
        showSubmissionOutcomeUnknown();
        return;
      }
      updateSubmissionControls();
      showMessage(error.message, 'danger');
      if (error.reloadRequired) {
        reloadForConfigurationChange(error.message);
      } else {
        heartbeatTimer = startHeartbeat();
      }
    }
  });

  root.querySelector('[data-release-workbench]').addEventListener('click', async () => {
    try {
      await api(`/api/grading/workbench/sessions/${sessionUuid}/release`, {method: 'POST', body: '{}'});
      window.location.assign(config.dashboardUrl);
    } catch (error) { showMessage(error.message, 'danger'); }
  });

  const status = root.querySelector('[data-lease-status]');
  const absoluteExpiry = new Date(config.absoluteExpiresAt);
  function updateStatus() {
    const minutes = Math.max(0, Math.ceil((absoluteExpiry - new Date()) / 60000));
    status.querySelector('.gwb-full').textContent = `${minutes} min maximum remaining`;
    status.querySelector('[data-lease-short]').textContent = `${minutes}m`;
  }
  updateStatus();
  setInterval(updateStatus, 30000);
  function startHeartbeat() {
    return window.setInterval(() => {
      if (submitting || document.hidden) return;
      api(`/api/grading/workbench/sessions/${sessionUuid}/heartbeat`, {method: 'POST', body: '{}'})
        .then(result => {
          if (result.lease?.configuration_refreshed) {
            reloadForConfigurationChange('Grading options changed. Reloading this package with the current choices…');
          }
        })
        .catch(error => {
          if (error.reloadRequired) {
            reloadForConfigurationChange(error.message);
          } else {
            showMessage(error.message, 'danger');
          }
        });
    }, Number(config.heartbeatIntervalSeconds) * 1000);
  }
  let heartbeatTimer = startHeartbeat();
  // Phones and tablets suspend background tabs, so push any pending draft to the
  // server the moment the page is hidden rather than waiting for the debounce.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) flushDraft().catch(() => undefined);
  });
})();
