// static/js/pswp-init.js
(function () {
  let lightbox = null;

  function getSlideImgEl(pswp) {
    const slide = pswp?.currSlide;
    if (!slide) return null;

    // Try known locations
    let img =
      slide?.content?.element ||
      slide?.holderElement?.querySelector('img.pswp__img') ||
      slide?.holderElement?.querySelector('img');

    // DEBUG
    console.log('[PSWP] getSlideImgEl →', img);
    return img;
  }

  function applyFilter(pswp, filterClass) {
  console.log('[PSWP] applyFilter called →', filterClass);

  const img = getSlideImgEl(pswp);
  if (!img) {
    console.warn('[PSWP] No image element found to apply filter');
    return;
  }

  img.classList.remove(
    'pswp-img-filter-greenmono',
    'pswp-img-filter-greenboost',
    'pswp-img-filter-bluemono',
    'pswp-img-filter-gray',
    'pswp-img-filter-contrast'
  );

  if (filterClass) img.classList.add(filterClass);

  if (pswp.currSlide.data) {
    pswp.currSlide.data._filterClass = filterClass || '';
  }

  console.log('[PSWP] Applied filter class:', filterClass);
}


  async function ensureNaturalSizes(galleryEl) {
    const anchors = Array.from(galleryEl.querySelectorAll('a'));
    await Promise.all(anchors.map(a => {
      const type = (a.dataset.pswpType || 'image').toLowerCase();
      if (type !== 'image') return Promise.resolve();
      if (a.dataset.pswpWidth && a.dataset.pswpHeight) return Promise.resolve();

      const src = a.getAttribute('href');
      if (!src) return Promise.resolve();

      return new Promise((res) => {
        const img = new Image();
        img.onload = () => {
          console.log('[PSWP] Loaded size:', src, img.naturalWidth, img.naturalHeight);
          a.dataset.pswpWidth = img.naturalWidth || 1200;
          a.dataset.pswpHeight = img.naturalHeight || 900;
          res();
        };
        img.onerror = () => {
          console.warn('[PSWP] Failed to load image:', src);
          a.dataset.pswpWidth = 1200;
          a.dataset.pswpHeight = 900;
          res();
        };
        img.src = src;
      });
    }));
  }

  window.openPswpGallery = async function (galleryId, index) {
    console.log('[PSWP] openPswpGallery →', galleryId, index);

    const galleryEl = document.getElementById(galleryId);
    if (!galleryEl) {
      console.warn('[PSWP] Gallery not found:', galleryId);
      return;
    }

    if (!window.PhotoSwipeLightbox || !window.PhotoSwipe) {
      console.error('[PSWP] PhotoSwipe scripts not loaded before pswp-init.js');
      return;
    }

    await ensureNaturalSizes(galleryEl);

    if (lightbox) {
      try {
        console.log('[PSWP] Destroying existing lightbox instance');
        lightbox.destroy();
      } catch (e) {
        console.warn('[PSWP] Failed to destroy previous instance:', e);
      }
      lightbox = null;
    }

    lightbox = new PhotoSwipeLightbox({
      gallery: '#' + galleryId,
      children: 'a',
      pswpModule: () => PhotoSwipe,
      initialZoomLevel: 'fit',
      secondaryZoomLevel: 2,
      maxZoomLevel: 8,
      wheelToZoom: true,
      bgOpacity: 0.9,
      padding: { top: 16, bottom: 48, left: 16, right: 16 },
      clickToCloseNonZoomable: true
    });
    // Expose for manual debugging
  window.getSlideImgEl = getSlideImgEl;
  window.pswpLightbox = lightbox;


    lightbox.addFilter('itemData', (item) => {
      const el = item.element;
      const type = el?.dataset?.pswpType;

      if (type === 'html') {
        item.type = 'html';
        item.html = el.dataset.pswpHtml;
      } else {
        item.type = 'image';  // ✅ Force image type if not HTML
      }

      return item;
    });

    lightbox.on('change', () => {
      const pswp = lightbox.pswp;
      const f = pswp?.currSlide?.data?._filterClass || '';
      console.log('[PSWP] Slide changed → reapplying filter:', f);
      applyFilter(pswp, f);
    });

    lightbox.on('uiRegister', function () {
      const pswp = lightbox.pswp;

      // Ensure top-bar z-index stays above overlays
      try {
        pswp?.ui?.registerElement({
          name: 'zfix',
          order: 1,
          isButton: false,
          appendTo: 'bar',
          onInit: (el) => {
            const bar = el.closest('.pswp__top-bar');
            if (bar) bar.style.zIndex = '200';
            console.log('[PSWP] Set z-index for top bar');
          }
        });
      } catch (_) {}

      const mkBtn = (name, label, filterClass) => {
        pswp?.ui?.registerElement({
          name,
          order: 30,
          isButton: true,
          tagName: 'button',
          html: label,
          appendTo: 'bar',
          onClick: (event, el, pswpInstance) => {
            console.log('[PSWP] Filter button clicked:', name);
            applyFilter(pswpInstance, filterClass);
            document.querySelectorAll('.pswp__button--filter-redfree, .pswp__button--filter-greenboost, ...')
              .forEach(btn => btn.classList.remove('active'));
            el.classList.add('active');

          }
        });
      };

      mkBtn('filter-redfree',    'R', 'pswp-img-filter-greenmono');
      mkBtn('filter-greenboost', 'G', 'pswp-img-filter-greenboost');
      mkBtn('filter-bluemono',   'B', 'pswp-img-filter-bluemono');
      mkBtn('filter-gray',       'Y', 'pswp-img-filter-gray');
      mkBtn('filter-contrast',   'H', 'pswp-img-filter-contrast');
      mkBtn('filter-clear',      'C', '');
    });

    lightbox.on('open', () => {
      const pswp = lightbox.pswp;

      const handler = (e) => {
        const key = (e.key || '').toLowerCase();
        console.log('[PSWP] Key pressed:', key);

        if (!pswp || pswp.isDestroying) return;

        switch (key) {
          case 'r': return applyFilter(pswp, 'pswp-img-filter-greenmono');
          case 'g': return applyFilter(pswp, 'pswp-img-filter-greenboost');
          case 'b': return applyFilter(pswp, 'pswp-img-filter-bluemono');
          case 'y': return applyFilter(pswp, 'pswp-img-filter-gray');
          case 'h': return applyFilter(pswp, 'pswp-img-filter-contrast');
          case 'c': return applyFilter(pswp, '');
        }
      };

      document.addEventListener('keydown', handler);
      pswp.on('destroy', () => {
        console.log('[PSWP] destroy → removing keyboard handler');
        document.removeEventListener('keydown', handler);
      });
    });

    console.log('[PSWP] Initializing lightbox');
    lightbox.init();

    // Auto-start with first image slide (not PDF)
    const links = Array.from(galleryEl.querySelectorAll('a'));
    let firstImageIndex = links.findIndex(a => (a.dataset.pswpType || 'image') === 'image');
    if (firstImageIndex === -1) firstImageIndex = 0;

    console.log('[PSWP] Opening gallery at index:', typeof index === 'number' ? index : firstImageIndex);
    lightbox.loadAndOpen(typeof index === 'number' ? index : firstImageIndex);
  };
})();
