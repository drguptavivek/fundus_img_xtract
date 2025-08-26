// static/js/pswp-init.js
(function () {
  let lightbox = null;

  function getSlideImgEl(pswp) {
    const slide = pswp?.currSlide;
    if (!slide || slide.type !== 'image') return null;
    // PhotoSwipe v5 exposes the rendered element via slide.content.element
    return slide.content?.element || slide.holderElement?.querySelector('img, .pswp__img');
  }

  function applyFilter(pswp, filterClass) {
    const img = getSlideImgEl(pswp);
    if (!img) return;
    // Clear all filter classes (include blue!)
    img.classList.remove(
      'pswp-img-filter-greenmono',
      'pswp-img-filter-greenboost',
      'pswp-img-filter-bluemono',
      'pswp-img-filter-gray',
      'pswp-img-filter-contrast'
    );
    if (filterClass) img.classList.add(filterClass);
    // Persist on slide metadata
    if (pswp?.currSlide?.data) {
      pswp.currSlide.data._filterClass = filterClass || '';
    }
    // Debug:
    // console.log('[PSWP] applyFilter ->', filterClass);
  }

  async function ensureNaturalSizes(galleryEl) {
    const anchors = Array.from(galleryEl.querySelectorAll('a'));
    await Promise.all(anchors.map(a => {
      const type = (a.dataset.pswpType || 'image').toLowerCase();
      if (type !== 'image') return Promise.resolve();
      if (a.dataset.pswpWidth && a.dataset.pswpHeight) return Promise.resolve();
      const src = a.getAttribute('href'); if (!src) return Promise.resolve();

      return new Promise((res) => {
        const img = new Image();
        img.onload = () => {
          a.dataset.pswpWidth = img.naturalWidth || 1200;
          a.dataset.pswpHeight = img.naturalHeight || 900;
          res();
        };
        img.onerror = () => { a.dataset.pswpWidth = 1200; a.dataset.pswpHeight = 900; res(); };
        img.src = src;
      });
    }));
  }

  // Expose for your "View files" button
  window.openPswpGallery = async function (galleryId, index) {
    const galleryEl = document.getElementById(galleryId);
    if (!galleryEl) return;

    if (!window.PhotoSwipeLightbox || !window.PhotoSwipe) {
      console.error('[PSWP] PhotoSwipe scripts not loaded before pswp-init.js');
      return;
    }

    await ensureNaturalSizes(galleryEl);

    // Destroy previous instance if any
    if (lightbox) { try { lightbox.destroy(); } catch (_) {} lightbox = null; }

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

    // PDFs via HTML slides
    lightbox.addFilter('itemData', (item) => {
      if (item.element && item.element.dataset.pswpType === 'html') {
        item.type = 'html';
        item.html = item.element.dataset.pswpHtml;
      }
      return item;
    });

    lightbox.on('uiRegister', function () {
      // Caption registration (leave as you already have)

      // Make sure top bar stays above any overlays
      try {
        lightbox.pswp.ui.registerElement({
          name: 'zfix',
          order: 1,
          isButton: false,
          appendTo: 'bar',
          onInit: (el, pswp) => {
            const bar = el.closest('.pswp__top-bar');
            if (bar) bar.style.zIndex = '200';
          }
        });
      } catch (_) {}

      // Helper to register a visible button in top toolbar
      const mkBtn = (name, label, filterClass) => {
        lightbox.pswp.ui.registerElement({
          name,
          order: 30,              // after default buttons
          isButton: true,
          tagName: 'button',
          html: label,            // visible label ("R","G",...)
          appendTo: 'bar',        // top toolbar
          // IMPORTANT: (event, el, pswp)
          onClick: (event, el, pswp) => {
            if (pswp?.currSlide?.type !== 'image') return;
            applyFilter(pswp, filterClass);
          }
        });
      };

      mkBtn('filter-redfree',    'R', 'pswp-img-filter-greenmono');    // Red-free (green mono)
      mkBtn('filter-greenboost', 'G', 'pswp-img-filter-greenboost');   // Green emphasis
      mkBtn('filter-bluemono',   'B', 'pswp-img-filter-bluemono');     // Blue mono
      mkBtn('filter-gray',       'Y', 'pswp-img-filter-gray');         // Grayscale
      mkBtn('filter-contrast',   'H', 'pswp-img-filter-contrast');     // High contrast
      mkBtn('filter-clear',      'C', '');                             // Clear
    });

    // Reapply remembered filter when slide changes
    lightbox.on('change', () => {
      const pswp = lightbox.pswp;
      const f = pswp?.currSlide?.data?._filterClass || '';
      applyFilter(pswp, f);
    });

    // Keyboard shortcuts (R/G/B/Y/H/C)
    lightbox.on('afterInit', () => {
      const pswp = lightbox.pswp;
      const handler = (e) => {
        if (!pswp || pswp.isDestroying || pswp.currSlide?.type !== 'image') return;
        switch ((e.key || '').toLowerCase()) {
          case 'r': return applyFilter(pswp, 'pswp-img-filter-greenmono');
          case 'g': return applyFilter(pswp, 'pswp-img-filter-greenboost');
          case 'b': return applyFilter(pswp, 'pswp-img-filter-bluemono');
          case 'y': return applyFilter(pswp, 'pswp-img-filter-gray');
          case 'h': return applyFilter(pswp, 'pswp-img-filter-contrast');
          case 'c': return applyFilter(pswp, '');
        }
      };
      document.addEventListener('keydown', handler);
      pswp.on('destroy', () => document.removeEventListener('keydown', handler));
    });

    lightbox.init();
    lightbox.loadAndOpen(typeof index === 'number' ? index : 0);
  };
})();
