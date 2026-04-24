'use strict';

(function() {
  const root = document.getElementById('datasetScreenRoot');
  if (!root) {
    return;
  }

  const datasetUuid = root.dataset.datasetUuid || '';
  const galleryUrl = root.dataset.galleryUrl || '';
  const listUrl = root.dataset.listUrl || '';
  const detailUrl = root.dataset.detailUrl || '';
  const defaultSort = root.dataset.defaultSort || 'task_asc';
  const defaultPiiFilter = root.dataset.defaultPiiFilter || 'all';
  const defaultColorFilter = root.dataset.defaultColorFilter || 'all';

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
  const piiFilterSelect = document.getElementById('piiFilterSelect');
  const colorFilterSelect = document.getElementById('colorFilterSelect');

  let pendingGalleryImageUuid = null;
  let lastGalleryThumb = null;

  const thumbQueue = [];
  let thumbInFlight = 0;
  const maxThumbConcurrent = 2;

  const cacheKey = datasetUuid ? `datasetOcrStatusCache:${datasetUuid}` : 'datasetOcrStatusCache';
  const selectedThumbKey = datasetUuid ? `datasetScreenSelectedThumb:${datasetUuid}` : 'datasetScreenSelectedThumb';
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

  const saveSelectedThumb = function(imageUuid) {
    if (!imageUuid) {
      return;
    }
    try {
      localStorage.setItem(selectedThumbKey, imageUuid);
    } catch (err) {}
  };

  const getSelectedThumb = function() {
    try {
      return localStorage.getItem(selectedThumbKey);
    } catch (err) {
      return null;
    }
  };

  const clearSelectedThumb = function() {
    try {
      localStorage.removeItem(selectedThumbKey);
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

  const getCsrfToken = function() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };

  const formatMetadataSummary = function(data) {
    if (!data) {
      return 'Metadata pending';
    }
    const parts = [];
    if (data.width && data.height) {
      parts.push(`${data.width}x${data.height}`);
    }
    if (data.is_grayscale !== null && data.is_grayscale !== undefined) {
      parts.push(data.is_grayscale ? 'Grayscale' : 'Color');
    }
    if (data.avg_luminance !== null && data.avg_luminance !== undefined) {
      parts.push(`Avg ${data.avg_luminance.toFixed(1)}`);
    }
    if (data.max_luminance !== null && data.max_luminance !== undefined) {
      parts.push(`Max ${data.max_luminance.toFixed(1)}`);
    }
    if (data.exif_present) {
      parts.push('EXIF');
    }
    if (data.iptc_present) {
      parts.push('IPTC');
    }
    if (data.size_ok === false) {
      parts.push('Below 1024×768');
    }
    return parts.join(' • ') || 'Metadata pending';
  };

  document.addEventListener('click', function(evt) {
    const btn = evt.target.closest('.metadata-extract-btn');
    if (!btn) {
      return;
    }
    evt.preventDefault();
    const imageUuid = btn.getAttribute('data-image-uuid');
    const variant = btn.getAttribute('data-variant') || 'orig';
    const statusEl = document.getElementById('metadataStatus');
    const summaryEl = document.getElementById('metadataSummary');
    if (!imageUuid) {
      return;
    }
    btn.disabled = true;
    if (statusEl) {
      statusEl.textContent = 'Extracting...';
    }
    fetch(`/api/image-metadata/${encodeURIComponent(imageUuid)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        variant: variant,
        include_raw: false,
        force: false
      })
    })
      .then(function(res) { return res.json(); })
      .then(function(payload) {
        if (payload && payload.success) {
          if (summaryEl) {
            summaryEl.textContent = formatMetadataSummary(payload.data);
          }
          if (statusEl) {
            statusEl.textContent = 'Updated';
          }
        } else if (statusEl) {
          statusEl.textContent = 'Failed';
        }
      })
      .catch(function() {
        if (statusEl) {
          statusEl.textContent = 'Failed';
        }
      })
      .finally(function() {
        btn.disabled = false;
        window.setTimeout(function() {
          if (statusEl) {
            statusEl.textContent = '';
          }
        }, 2000);
      });
  });

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

  const setManualPiiStatus = function(imageUuid, status) {
    if (!imageUuid || !status) {
      return;
    }
    setOcrChecking(imageUuid);
    const meta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = meta ? meta.getAttribute('content') : '';
    fetch('/api/ocr/pii/override', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ image_uuid: imageUuid, pii_status: status })
    })
      .then(function(response) { return response.json(); })
      .then(function(payload) {
        const data = payload && payload.data ? payload.data : null;
        if (!data || !data.status) {
          ocrStatusCache[imageUuid] = { status: 'error' };
          updateOcrBadges(imageUuid, 'error');
          updateOcrSummary();
          return;
        }
        const detail = 'Manual override';
        ocrStatusCache[imageUuid] = { status: data.status, detail: detail, source: 'manual' };
        updateOcrBadges(imageUuid, data.status, detail);
        updateOcrSummary();
        saveCacheToStorage();
      })
      .catch(function() {
        ocrStatusCache[imageUuid] = { status: 'error' };
        updateOcrBadges(imageUuid, 'error');
        updateOcrSummary();
      });
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
      const currentPii = (piiFilterSelect && piiFilterSelect.value) ? piiFilterSelect.value : defaultPiiFilter;
      const currentColor = (colorFilterSelect && colorFilterSelect.value) ? colorFilterSelect.value : defaultColorFilter;
      if (currentPii) {
        url.searchParams.set('pii_filter', currentPii);
      }
      if (currentColor) {
        url.searchParams.set('color_filter', currentColor);
      }
      const view = url.searchParams.get('view') || 'list';
      if (view === 'gallery') {
        const page = url.searchParams.get('page') || '1';
        url.searchParams.set('page', page);
        url.hash = '#screen-images';
        window.history.replaceState({ view: 'gallery' }, '', url.toString());
        if (window.htmx && galleryUrl) {
          window.htmx.ajax('GET', galleryUrl + '?page=' + page + '&view=gallery&sort=' + value + '&pii_filter=' + currentPii + '&color_filter=' + currentColor, '#datasetScreenGalleryView');
        }
        return;
      }
      url.hash = '#screen-images';
      window.location.href = url.toString();
    });
  }

  const refreshScreenView = function() {
      const piiValue = (piiFilterSelect && piiFilterSelect.value) ? piiFilterSelect.value : defaultPiiFilter;
      const colorValue = (colorFilterSelect && colorFilterSelect.value) ? colorFilterSelect.value : defaultColorFilter;
      const url = new URL(window.location);
      url.searchParams.set('pii_filter', piiValue);
      url.searchParams.set('color_filter', colorValue);
      url.searchParams.set('page', '1');
      const view = url.searchParams.get('view') || 'list';
      const sort = url.searchParams.get('sort') || defaultSort;
      url.hash = '#screen-images';
      if (view === 'gallery') {
        window.history.replaceState({ view: 'gallery' }, '', url.toString());
        if (window.htmx && galleryUrl) {
          window.htmx.ajax('GET', galleryUrl + '?page=1&view=gallery&sort=' + sort + '&pii_filter=' + piiValue + '&color_filter=' + colorValue, '#datasetScreenGalleryView');
        }
        return;
      }
      window.history.replaceState({ view: 'list' }, '', url.toString());
      if (window.htmx && listUrl) {
        window.htmx.ajax('GET', listUrl + '?page=1&view=list&sort=' + sort + '&pii_filter=' + piiValue + '&color_filter=' + colorValue, '#datasetScreenListView');
      } else {
        window.location.href = url.toString();
      }
  };

  if (piiFilterSelect) {
    piiFilterSelect.addEventListener('change', refreshScreenView);
  }

  if (colorFilterSelect) {
    colorFilterSelect.addEventListener('change', refreshScreenView);
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
    if (view === 'gallery') {
      const thumbs = Array.from(document.querySelectorAll('.dataset-screen-thumb'))
        .filter(function(thumb) { return thumb.offsetParent !== null; });
      if (!thumbs.length) {
        return;
      }
      const selectedUuid = params.get('image_uuid') || getSelectedThumb();
      let currentIndex = thumbs.findIndex(function(thumb) {
        return (thumb.dataset.imageUuid || '') === selectedUuid || thumb.classList.contains('is-active');
      });
      if (currentIndex < 0) {
        currentIndex = event.key === 'ArrowDown' ? -1 : thumbs.length;
      }
      const nextIndex = event.key === 'ArrowDown' ? currentIndex + 1 : currentIndex - 1;
      if (nextIndex < 0 || nextIndex >= thumbs.length) {
        return;
      }
      event.preventDefault();
      const nextThumb = thumbs[nextIndex];
      const link = nextThumb ? nextThumb.querySelector('[data-gallery-open]') : null;
      if (link) {
        if (window.htmx) {
          window.htmx.trigger(link, 'click');
        } else {
          link.click();
        }
      }
      nextThumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      return;
    }
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
    document.querySelectorAll('.dataset-screen-thumb.is-active').forEach(function(el) {
      el.classList.remove('is-active');
    });
    const thumb = galleryLink.closest('.dataset-screen-thumb');
    if (thumb) {
      thumb.classList.add('is-active');
      saveSelectedThumb(thumb.dataset.imageUuid || '');
    }
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
    const button = event.target.closest('.ocr-manual-clear-btn');
    if (!button) {
      return;
    }
    const imageUuid = button.getAttribute('data-image-uuid');
    setManualPiiStatus(imageUuid, 'clear');
  });

  document.body.addEventListener('click', function(event) {
    const button = event.target.closest('.ocr-manual-detected-btn');
    if (!button) {
      return;
    }
    const imageUuid = button.getAttribute('data-image-uuid');
    setManualPiiStatus(imageUuid, 'detected');
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
  const applyScreenFilter = function() {
    const screenList = document.getElementById('datasetScreenList');
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
    const piiFilter = params.get('pii_filter') || defaultPiiFilter;
    const colorFilter = params.get('color_filter') || defaultColorFilter;
    if (sortSelect) {
      sortSelect.value = sort;
    }
    if (piiFilterSelect) {
      piiFilterSelect.value = piiFilter;
    }
    if (colorFilterSelect) {
      colorFilterSelect.value = colorFilter;
    }
    if (view === 'gallery') {
      showGalleryView();
      if (galleryButton && window.htmx && galleryUrl) {
        window.htmx.ajax('GET', galleryUrl + '?page=' + page + '&view=gallery&sort=' + sort + '&pii_filter=' + piiFilter + '&color_filter=' + colorFilter, '#datasetScreenGalleryView');
      }
      const imageUuid = params.get('image_uuid');
      if (imageUuid) {
        const viewerTarget = document.querySelector('[data-gallery-open][href*="' + imageUuid + '"]');
        if (viewerTarget) {
          showGalleryWithViewer();
          if (window.htmx) {
            window.htmx.trigger(viewerTarget, 'click');
          } else {
            viewerTarget.click();
          }
        } else {
          pendingGalleryImageUuid = imageUuid;
        }
      } else {
        const stored = getSelectedThumb();
        if (stored) {
          const storedThumb = document.querySelector('.dataset-screen-thumb[data-image-uuid="' + stored + '"]');
          if (storedThumb) {
            storedThumb.classList.add('is-active');
          }
        }
      }
    } else {
      showListView();
      pruneOcrCache(document);
      saveCacheToStorage();
    }
    const imageUuid = params.get('image_uuid');
    if (!imageUuid || view === 'gallery') {
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
    if (target.id === 'datasetScreenGalleryView' || target.id === 'datasetScreenViewer') {
      const params = new URL(window.location).searchParams;
      const imageUuid = params.get('image_uuid') || getSelectedThumb();
      if (imageUuid) {
        document.querySelectorAll('.dataset-screen-thumb.is-active').forEach(function(el) {
          el.classList.remove('is-active');
        });
        const activeThumb = document.querySelector('.dataset-screen-thumb[data-image-uuid="' + imageUuid + '"]');
        if (activeThumb) {
          activeThumb.classList.add('is-active');
        }
      }
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
