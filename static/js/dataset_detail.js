'use strict';

(function() {
  const root = document.getElementById('datasetScreenRoot');
  if (!root) {
    return;
  }

  const datasetUuid = root.dataset.datasetUuid || '';
  const galleryUrl = root.dataset.galleryUrl || '';
  const detailUrl = root.dataset.detailUrl || '';
  const defaultSort = root.dataset.defaultSort || 'task_asc';

  const listView = document.getElementById('datasetScreenListView');
  const galleryView = document.getElementById('datasetScreenGalleryView');
  const listButton = document.getElementById('screenViewList');
  const galleryButton = document.getElementById('screenViewGallery');
  const filterGroup = document.getElementById('screenFilterGroup');
  const viewerColumn = document.getElementById('datasetScreenViewerColumn');
  const listColumn = document.getElementById('datasetScreenListColumn');
  const sortSelect = document.getElementById('screenSortSelect');
  const refreshPiiBtn = document.getElementById('refreshPiiStatusBtn');
  const ocrCountBadge = document.getElementById('ocrDetectedCount');

  let pendingGalleryImageUuid = null;
  let lastGalleryThumb = null;

  const thumbQueue = [];
  let thumbInFlight = 0;
  const maxThumbConcurrent = 2;

  const cacheKey = datasetUuid ? `datasetOcrStatusCache:${datasetUuid}` : 'datasetOcrStatusCache';
  const ocrStatusCache = {};

  const updateOcrSummary = function() {
    if (!ocrCountBadge) {
      return;
    }
    const detectedCount = Object.values(ocrStatusCache).filter(function(entry) {
      return entry && entry.status === 'detected';
    }).length;
    ocrCountBadge.textContent = String(detectedCount);
  };

  const updateOcrBadges = function(imageUuid, status, detail) {
    if (!imageUuid) {
      return;
    }
    const badges = document.querySelectorAll('[data-image-uuid="' + imageUuid + '"]' + '.ocr-list-badge, ' +
      '[data-image-uuid="' + imageUuid + '"]' + '.ocr-thumb-badge, ' +
      '[data-image-uuid="' + imageUuid + '"]' + '.ocr-viewer-badge');
    badges.forEach(function(badge) {
      const isThumb = badge.classList.contains('ocr-thumb-badge');
      const isViewer = badge.classList.contains('ocr-viewer-badge');
      const baseClass = isThumb
        ? 'badge rounded-pill ocr-thumb-badge ms-1'
        : (isViewer ? 'badge rounded-pill ocr-viewer-badge' : 'badge rounded-pill ocr-list-badge');
      if (status === 'detected') {
        badge.dataset.ocrLoaded = 'true';
        badge.textContent = 'PII detected';
        badge.className = baseClass + ' bg-danger';
        if (detail) {
          badge.setAttribute('title', detail);
        }
        return;
      }
      if (status === 'clear') {
        badge.dataset.ocrLoaded = 'true';
        badge.textContent = 'No PII';
        badge.className = baseClass + ' bg-success';
        if (detail) {
          badge.setAttribute('title', detail);
        }
        return;
      }
      if (status === 'pending') {
        delete badge.dataset.ocrLoaded;
        badge.textContent = 'Pending';
        badge.className = baseClass + ' bg-secondary';
        badge.setAttribute('title', 'Pending OCR check');
        return;
      }
      delete badge.dataset.ocrLoaded;
      badge.textContent = 'OCR unavailable';
      badge.className = baseClass + ' bg-warning text-dark';
      badge.setAttribute('title', 'OCR unavailable');
    });
  };

  const setOcrChecking = function(imageUuid) {
    if (!imageUuid) {
      return;
    }
    const badges = document.querySelectorAll('[data-image-uuid="' + imageUuid + '"]' + '.ocr-list-badge, ' +
      '[data-image-uuid="' + imageUuid + '"]' + '.ocr-thumb-badge, ' +
      '[data-image-uuid="' + imageUuid + '"]' + '.ocr-viewer-badge');
    badges.forEach(function(badge) {
      const isThumb = badge.classList.contains('ocr-thumb-badge');
      const isViewer = badge.classList.contains('ocr-viewer-badge');
      const baseClass = isThumb
        ? 'badge rounded-pill ocr-thumb-badge ms-1'
        : (isViewer ? 'badge rounded-pill ocr-viewer-badge' : 'badge rounded-pill ocr-list-badge');
      badge.textContent = 'Checking...';
      badge.className = baseClass + ' bg-secondary';
    });
  };

  const loadCacheFromStorage = function() {
    try {
      const raw = localStorage.getItem(cacheKey);
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw);
      Object.keys(parsed || {}).forEach(function(uuid) {
        ocrStatusCache[uuid] = parsed[uuid];
      });
    } catch (err) {}
  };

  const saveCacheToStorage = function() {
    try {
      localStorage.setItem(cacheKey, JSON.stringify(ocrStatusCache));
    } catch (err) {}
  };

  const applyCachedOcrStatus = function(scopeRoot) {
    const scope = scopeRoot || document;
    const badges = scope.querySelectorAll('[data-image-uuid].ocr-list-badge, [data-image-uuid].ocr-thumb-badge, [data-image-uuid].ocr-viewer-badge');
    badges.forEach(function(badge) {
      const imageUuid = badge.getAttribute('data-image-uuid');
      if (!imageUuid) {
        return;
      }
      const cached = ocrStatusCache[imageUuid];
      if (cached) {
        updateOcrBadges(imageUuid, cached.status, cached.detail);
      }
    });
  };

  const pruneOcrCache = function(scopeRoot) {
    const scope = scopeRoot || document;
    const badges = scope.querySelectorAll('[data-image-uuid].ocr-list-badge, [data-image-uuid].ocr-thumb-badge, [data-image-uuid].ocr-viewer-badge');
    const allowed = new Set(Array.from(badges).map(function(badge) {
      return badge.getAttribute('data-image-uuid');
    }).filter(Boolean));
    Object.keys(ocrStatusCache).forEach(function(uuid) {
      if (!allowed.has(uuid)) {
        delete ocrStatusCache[uuid];
      }
    });
  };

  const fetchOcrStatusBatch = function(scopeRoot, forceRefresh, onlyUuids) {
    const scope = scopeRoot || document;
    const badges = scope.querySelectorAll('[data-image-uuid].ocr-list-badge, [data-image-uuid].ocr-thumb-badge, [data-image-uuid].ocr-viewer-badge');
    let imageUuids = Array.from(badges)
      .map(function(badge) { return badge.getAttribute('data-image-uuid'); });
    if (Array.isArray(onlyUuids) && onlyUuids.length) {
      imageUuids = onlyUuids;
    }
    imageUuids = imageUuids.filter(function(uuid, index, arr) {
      if (!uuid) {
        return false;
      }
      if (arr.indexOf(uuid) !== index) {
        return false;
      }
      if (forceRefresh) {
        return true;
      }
      return !ocrStatusCache[uuid];
    });
    if (!imageUuids.length) {
      return;
    }
    const meta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = meta ? meta.getAttribute('content') : '';
    fetch('/api/ocr/pii/batch', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ image_uuids: imageUuids })
    })
      .then(function(response) { return response.json(); })
      .then(function(payload) {
        const data = payload && payload.data ? payload.data : {};
        Object.keys(data).forEach(function(uuid) {
          const entry = data[uuid];
          if (!entry || !entry.status) {
            return;
          }
          let detail = entry.status === 'pending' ? 'Pending OCR check' : null;
          if (entry.source === 'manual') {
            detail = detail ? detail + ' (Manual override)' : 'Manual override';
          }
          ocrStatusCache[uuid] = { status: entry.status, detail: detail, source: entry.source || 'auto' };
          updateOcrBadges(uuid, entry.status, detail);
        });
        saveCacheToStorage();
        updateOcrSummary();
      })
      .catch(function() {});
  };

  const triggerOcrForUuid = function(imageUuid) {
    if (!imageUuid) {
      return;
    }
    const badge = document.querySelector('[data-image-uuid="' + imageUuid + '"]' + '.ocr-list-badge, ' +
      '[data-image-uuid="' + imageUuid + '"]' + '.ocr-thumb-badge');
    if (badge && badge.dataset.ocrLoaded === 'true') {
      return;
    }
    setOcrChecking(imageUuid);
    fetch('/api/ocr/pii/' + encodeURIComponent(imageUuid), {
      headers: { 'Accept': 'application/json' }
    })
      .then(function(response) { return response.json(); })
      .then(function(payload) {
        const data = payload && payload.data ? payload.data : null;
        if (!data || data.status === 'error') {
          ocrStatusCache[imageUuid] = { status: 'error' };
          updateOcrBadges(imageUuid, 'error');
          updateOcrSummary();
          return;
        }
        let detail = 'Valid detections: ' + (data.valid_detections || 0) +
          ', pattern matches: ' + (data.pattern_matches || 0);
        if (data.source === 'manual') {
          detail = detail + ' (Manual override)';
        }
        const status = data.status === 'detected' ? 'detected' : 'clear';
        ocrStatusCache[imageUuid] = { status: status, detail: detail, source: data.source || 'auto' };
        updateOcrBadges(imageUuid, status, detail);
        updateOcrSummary();
        saveCacheToStorage();
      })
      .catch(function() {
        ocrStatusCache[imageUuid] = { status: 'error' };
        updateOcrBadges(imageUuid, 'error');
        updateOcrSummary();
      });
  };

  const forceOcrForUuid = function(imageUuid) {
    if (!imageUuid) {
      return;
    }
    delete ocrStatusCache[imageUuid];
    setOcrChecking(imageUuid);
    fetch('/api/ocr/pii/' + encodeURIComponent(imageUuid) + '?refresh=1', {
      headers: { 'Accept': 'application/json' }
    })
      .then(function(response) { return response.json(); })
      .then(function(payload) {
        const data = payload && payload.data ? payload.data : null;
        if (!data || data.status === 'error') {
          ocrStatusCache[imageUuid] = { status: 'error' };
          updateOcrBadges(imageUuid, 'error');
          updateOcrSummary();
          saveCacheToStorage();
          return;
        }
        let detail = 'Valid detections: ' + (data.valid_detections || 0) +
          ', pattern matches: ' + (data.pattern_matches || 0);
        const status = data.status === 'detected' ? 'detected' : 'clear';
        ocrStatusCache[imageUuid] = { status: status, detail: detail, source: data.source || 'auto' };
        updateOcrBadges(imageUuid, status, detail);
        updateOcrSummary();
        saveCacheToStorage();
      })
      .catch(function() {
        ocrStatusCache[imageUuid] = { status: 'error' };
        updateOcrBadges(imageUuid, 'error');
        updateOcrSummary();
      });
  };

  const refreshOcrForUuid = function(imageUuid) {
    if (!imageUuid) {
      return;
    }
    fetchOcrStatusBatch(document, true, [imageUuid]);
  };

  const pumpThumbQueue = function() {
    while (thumbInFlight < maxThumbConcurrent && thumbQueue.length) {
      const img = thumbQueue.shift();
      if (!img || !img.dataset || !img.dataset.src) {
        continue;
      }
      thumbInFlight += 1;
      const src = img.dataset.src;
      const container = img.closest('.dataset-screen-thumb');
      if (container) {
        container.classList.add('is-loading');
        const status = container.querySelector('.thumb-status');
        if (status) {
          status.textContent = 'Loading...';
        }
      }
      const finish = function(isError) {
        thumbInFlight = Math.max(0, thumbInFlight - 1);
        if (container) {
          container.classList.remove('is-loading');
          if (isError) {
            container.classList.add('is-error');
            const status = container.querySelector('.thumb-status');
            if (status) {
              status.textContent = 'Thumbnail unavailable (rate limit or missing).';
            }
          } else {
            container.classList.remove('is-error');
          }
        }
        pumpThumbQueue();
      };
      img.addEventListener('load', function() {
        finish(false);
      }, { once: true });
      img.addEventListener('error', function() {
        finish(true);
      }, { once: true });
      img.src = src;
      img.removeAttribute('data-src');
    }
  };

  const enqueueThumb = function(img) {
    if (!img || !img.dataset || !img.dataset.src) {
      return;
    }
    if (img.dataset.thumbQueued === 'true') {
      return;
    }
    img.dataset.thumbQueued = 'true';
    thumbQueue.push(img);
    pumpThumbQueue();
  };

  const initThumbLazy = function(scopeRoot) {
    if (!scopeRoot) {
      return;
    }
    const images = Array.from(scopeRoot.querySelectorAll('img.dataset-screen-thumb-img[data-src]'));
    if (!images.length) {
      return;
    }
    const eagerCount = 6;
    images.slice(0, eagerCount).forEach(enqueueThumb);
    if (!window.IntersectionObserver) {
      images.slice(eagerCount).forEach(enqueueThumb);
      return;
    }
    const observer = new IntersectionObserver(function(entries, obs) {
      entries.forEach(function(entry) {
        if (!entry.isIntersecting) {
          return;
        }
        const img = entry.target;
        enqueueThumb(img);
        obs.unobserve(img);
      });
    }, { rootMargin: '400px' });
    images.slice(eagerCount).forEach(function(img) {
      observer.observe(img);
    });
  };

  const showListView = function() {
    if (listView) {
      listView.classList.remove('d-none');
    }
    if (galleryView) {
      galleryView.classList.add('d-none');
    }
    if (filterGroup) {
      filterGroup.classList.remove('d-none');
    }
    if (viewerColumn) {
      viewerColumn.classList.remove('d-none');
      viewerColumn.classList.remove('col-lg-5');
      viewerColumn.classList.add('col-lg-8');
    }
    if (listColumn) {
      listColumn.classList.remove('col-12');
      listColumn.classList.add('col-lg-4');
      listColumn.classList.remove('col-lg-7');
      listColumn.classList.remove('col-lg-6');
      listColumn.classList.remove('col-lg-5');
    }
  };

  const showGalleryView = function() {
    if (listView) {
      listView.classList.add('d-none');
    }
    if (galleryView) {
      galleryView.classList.remove('d-none');
    }
    if (filterGroup) {
      filterGroup.classList.add('d-none');
    }
    if (viewerColumn) {
      viewerColumn.classList.add('d-none');
      viewerColumn.classList.remove('col-lg-5');
      viewerColumn.classList.add('col-lg-8');
    }
    if (listColumn) {
      listColumn.classList.remove('col-lg-4');
      listColumn.classList.add('col-12');
      listColumn.classList.remove('col-lg-7');
      listColumn.classList.remove('col-lg-6');
      listColumn.classList.remove('col-lg-5');
    }
  };

  const showGalleryWithViewer = function() {
    if (listView) {
      listView.classList.add('d-none');
    }
    if (galleryView) {
      galleryView.classList.remove('d-none');
    }
    if (filterGroup) {
      filterGroup.classList.add('d-none');
    }
    if (viewerColumn) {
      viewerColumn.classList.remove('d-none');
      viewerColumn.classList.remove('col-lg-8');
      viewerColumn.classList.add('col-lg-7');
    }
    if (listColumn) {
      listColumn.classList.remove('col-12');
      listColumn.classList.remove('col-lg-4');
      listColumn.classList.add('col-lg-5');
      listColumn.classList.remove('col-lg-7');
      listColumn.classList.remove('col-lg-6');
    }
  };

  if (listButton) {
    listButton.addEventListener('click', function() {
      showListView();
      const url = new URL(window.location);
      url.searchParams.set('view', 'list');
      url.searchParams.delete('page');
      url.hash = '#screen-images';
      window.history.replaceState({ view: 'list' }, '', url.toString());
    });
  }

  if (galleryButton) {
    galleryButton.addEventListener('click', function() {
      showGalleryView();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', function() {
      const value = sortSelect.value || 'task_asc';
      const url = new URL(window.location);
      url.searchParams.set('sort', value);
      const view = url.searchParams.get('view') || 'list';
      if (view === 'gallery') {
        const page = url.searchParams.get('page') || '1';
        url.searchParams.set('page', page);
        url.hash = '#screen-images';
        window.history.replaceState({ view: 'gallery' }, '', url.toString());
        if (window.htmx && galleryUrl) {
          window.htmx.ajax('GET', galleryUrl + '?page=' + page + '&view=gallery&sort=' + value, '#datasetScreenGalleryView');
        }
        return;
      }
      url.hash = '#screen-images';
      window.location.href = url.toString();
    });
  }

  if (refreshPiiBtn) {
    refreshPiiBtn.addEventListener('click', function() {
      fetchOcrStatusBatch(document, true);
    });
  }

  document.body.addEventListener('click', function(event) {
    const row = event.target.closest('.dataset-screen-row');
    if (!row) {
      return;
    }
    document.querySelectorAll('.dataset-screen-row.active').forEach(function(el) {
      el.classList.remove('active');
    });
    row.classList.add('active');
    const imageUuid = row.dataset.imageUuid || '';
    if (imageUuid) {
      const url = new URL(window.location);
      url.searchParams.set('image_uuid', imageUuid);
      url.hash = '#screen-images';
      window.history.replaceState({ image_uuid: imageUuid }, '', url.toString());
    }
    triggerOcrForUuid(imageUuid);
  });

  document.addEventListener('keydown', function(event) {
    if (!event.key || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) {
      return;
    }
    const activeElement = document.activeElement;
    if (activeElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(activeElement.tagName)) {
      return;
    }
    const params = new URL(window.location).searchParams;
    const view = params.get('view') || 'list';
    if (view !== 'list') {
      return;
    }
    const rows = Array.from(document.querySelectorAll('.dataset-screen-row'))
      .filter(function(row) { return row.offsetParent !== null; });
    if (!rows.length) {
      return;
    }
    const currentIndex = rows.findIndex(function(row) {
      return row.classList.contains('active');
    });
    let nextIndex = 0;
    if (currentIndex >= 0) {
      nextIndex = event.key === 'ArrowDown' ? currentIndex + 1 : currentIndex - 1;
    } else {
      nextIndex = event.key === 'ArrowDown' ? 0 : rows.length - 1;
    }
    if (nextIndex < 0 || nextIndex >= rows.length) {
      return;
    }
    event.preventDefault();
    const targetRow = rows[nextIndex];
    if (window.htmx) {
      window.htmx.trigger(targetRow, 'click');
    } else {
      targetRow.click();
    }
    targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  document.body.addEventListener('click', function(event) {
    const galleryLink = event.target.closest('[data-gallery-open]');
    if (!galleryLink) {
      return;
    }
    showGalleryWithViewer();
    document.querySelectorAll('[data-gallery-open].active').forEach(function(el) {
      el.classList.remove('active');
    });
    galleryLink.classList.add('active');
    lastGalleryThumb = galleryLink;
    const viewer = document.getElementById('datasetScreenViewer');
    if (viewer) {
      viewer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    const href = galleryLink.getAttribute('href') || '';
    const match = href.match(/image_uuid=([^&#]+)/);
    const container = galleryLink.closest('.dataset-screen-thumb');
    const fallbackUuid = container ? (container.dataset.imageUuid || '') : '';
    const imageUuid = match ? decodeURIComponent(match[1]) : fallbackUuid;
    triggerOcrForUuid(imageUuid);
  });

  document.body.addEventListener('click', function(event) {
    const button = event.target.closest('.ocr-redetect-btn');
    if (!button) {
      return;
    }
    const imageUuid = button.getAttribute('data-image-uuid');
    forceOcrForUuid(imageUuid);
  });

  document.body.addEventListener('click', function(event) {
    const button = event.target.closest('.ocr-refresh-btn');
    if (!button) {
      return;
    }
    const imageUuid = button.getAttribute('data-image-uuid');
    refreshOcrForUuid(imageUuid);
  });

  document.body.addEventListener('click', function(event) {
    const closeBtn = event.target.closest('[data-gallery-close]');
    if (!closeBtn) {
      return;
    }
    const viewer = document.getElementById('datasetScreenViewer');
    if (viewer) {
      viewer.innerHTML = '<div class="alert alert-info mb-0">Select an image to review and exclude.</div>';
    }
    const params = new URL(window.location).searchParams;
    if (params.get('view') === 'gallery') {
      const url = new URL(window.location);
      url.searchParams.delete('image_uuid');
      url.hash = '#screen-images';
      window.history.replaceState({ view: 'gallery' }, '', url.toString());
      showGalleryView();
      const targetThumb = lastGalleryThumb || document.querySelector('[data-gallery-open].active');
      if (targetThumb) {
        targetThumb.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });

  document.body.addEventListener('click', function(event) {
    const trigger = event.target.closest('[data-edit-url]');
    if (!trigger) {
      return;
    }
    const modal = document.getElementById('datasetEditConfirmModal');
    const link = document.getElementById('datasetEditConfirmLink');
    if (modal && link) {
      modal.dataset.editUrl = trigger.dataset.editUrl || '';
      link.href = trigger.dataset.editUrl || '#';
    }
  });

  document.body.addEventListener('click', function(event) {
    const link = event.target.closest('#datasetEditConfirmLink');
    if (!link) {
      return;
    }
    const modal = document.getElementById('datasetEditConfirmModal');
    const editUrl = (modal && modal.dataset.editUrl) ? modal.dataset.editUrl : link.href;
    if (editUrl) {
      window.open(editUrl, '_blank', 'noopener');
    }
  });

  const filterInputs = document.querySelectorAll('input[name="screenFilter"]');
  const screenList = document.getElementById('datasetScreenList');
  const applyScreenFilter = function() {
    if (!screenList) {
      return;
    }
    const active = document.querySelector('input[name="screenFilter"]:checked');
    const mode = active ? active.value : 'all';
    screenList.querySelectorAll('.dataset-screen-row').forEach(function(row) {
      const excluded = row.dataset.excluded === 'true';
      if (mode === 'all') {
        row.style.display = '';
      } else if (mode === 'excluded') {
        row.style.display = excluded ? '' : 'none';
      } else {
        row.style.display = excluded ? 'none' : '';
      }
    });
    try {
      localStorage.setItem('datasetScreenFilter', mode);
    } catch (err) {}
  };

  filterInputs.forEach(function(input) {
    input.addEventListener('change', applyScreenFilter);
  });

  try {
    const savedFilter = localStorage.getItem('datasetScreenFilter');
    if (savedFilter) {
      const savedInput = document.querySelector('input[name="screenFilter"][value="' + savedFilter + '"]');
      if (savedInput) {
        savedInput.checked = true;
      }
    }
  } catch (err) {}

  const syncFromUrl = function() {
    const params = new URL(window.location).searchParams;
    const view = params.get('view') || 'list';
    const page = params.get('page') || '1';
    const sort = params.get('sort') || defaultSort;
    if (sortSelect) {
      sortSelect.value = sort;
    }
    if (view === 'gallery') {
      showGalleryView();
      if (galleryButton && window.htmx && galleryUrl) {
        window.htmx.ajax('GET', galleryUrl + '?page=' + page + '&view=gallery&sort=' + sort, '#datasetScreenGalleryView');
      }
    } else {
      showListView();
      pruneOcrCache(document);
      saveCacheToStorage();
    }
    const imageUuid = params.get('image_uuid');
    if (!imageUuid) {
      return;
    }
    if (view === 'gallery') {
      pendingGalleryImageUuid = imageUuid;
      return;
    }
    const target = document.querySelector('.dataset-screen-row[data-image-uuid="' + imageUuid + '"]');
    if (target) {
      if (window.htmx) {
        window.htmx.trigger(target, 'click');
      } else {
        target.click();
      }
    }
  };

  document.body.addEventListener('htmx:afterSwap', function(event) {
    const target = event.target;
    if (!target) {
      return;
    }
    applyCachedOcrStatus(target);
    fetchOcrStatusBatch(target);
    if (target.id === 'datasetScreenGalleryView' || (target.id && target.id.startsWith('datasetScreenThumb-'))) {
      initThumbLazy(target);
    }
    if (target.id === 'datasetScreenListView') {
      applyScreenFilter();
      pruneOcrCache(target);
      saveCacheToStorage();
    }
    if (target.id === 'datasetScreenGalleryView' && pendingGalleryImageUuid) {
      const pending = pendingGalleryImageUuid;
      pendingGalleryImageUuid = null;
      const galleryTarget = document.querySelector('[data-gallery-open][href*="' + pending + '"]');
      if (galleryTarget) {
        showGalleryWithViewer();
        if (window.htmx) {
          window.htmx.trigger(galleryTarget, 'click');
        } else {
          galleryTarget.click();
        }
      }
    }
  });

  document.body.addEventListener('datasetAddMore', function(event) {
    const detail = event.detail || {};
    const imageUuid = detail.image_uuid;
    if (!imageUuid) {
      return;
    }
    const countAll = document.getElementById('screenCountAll');
    const countIncluded = document.getElementById('screenCountIncluded');
    if (countAll) {
      countAll.textContent = String(parseInt(countAll.textContent || '0', 10) + 1);
    }
    if (countIncluded) {
      countIncluded.textContent = String(parseInt(countIncluded.textContent || '0', 10) + 1);
    }
    const row = document.querySelector('.dataset-screen-row[data-image-uuid="' + imageUuid + '"]');
    if (!row) {
      return;
    }
    if (window.htmx) {
      window.htmx.process(row);
    }
    document.querySelectorAll('.dataset-screen-row.active').forEach(function(el) {
      el.classList.remove('active');
    });
    row.classList.add('active');
    row.classList.add('is-new');
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(function() {
      row.classList.remove('is-new');
    }, 2500);
    if (window.htmx) {
      window.htmx.trigger(row, 'click');
    } else {
      row.click();
    }
    applyScreenFilter();
  });

  const setGalleryNavDisabled = function(disabled) {
    document.querySelectorAll('.dataset-screen-pager-btn').forEach(function(btn) {
      if (disabled) {
        btn.classList.add('disabled');
        btn.setAttribute('aria-disabled', 'true');
      } else if (!btn.dataset.forceDisabled) {
        btn.classList.remove('disabled');
        btn.removeAttribute('aria-disabled');
      }
    });
  };

  document.body.addEventListener('htmx:beforeRequest', function(event) {
    if (event.target && event.target.id === 'datasetScreenGalleryView') {
      setGalleryNavDisabled(true);
    }
  });

  document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.target && event.target.id === 'datasetScreenGalleryView') {
      setGalleryNavDisabled(false);
    }
  });

  loadCacheFromStorage();
  applyCachedOcrStatus(document);
  applyScreenFilter();
  syncFromUrl();
  initThumbLazy(document);
  fetchOcrStatusBatch(document, true);
  updateOcrSummary();

  window.addEventListener('load', function() {
    fetchOcrStatusBatch(document, true);
  });
})();
