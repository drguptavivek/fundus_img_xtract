// static/js/pswp-init.js
(function () {
  let lightbox = null;

  // 🔍 Get the current image element on the slide
  function getSlideImgEl(pswp) {
    const slide = pswp?.currSlide;
    if (!slide) return null;

    const img =
      slide?.content?.element ||
      slide?.holderElement?.querySelector('img.pswp__img') ||
      slide?.holderElement?.querySelector('img');

    console.log('[PSWP] getSlideImgEl →', img);
    return img;
  }

  // 🎨 Apply a CSS filter class to the current image
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

  // 📐 Measure image sizes to preload into PhotoSwipe
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
          a.dataset.pswpWidth = img.naturalWidth || 1200;
          a.dataset.pswpHeight = img.naturalHeight || 900;
          res();
        };
        img.onerror = () => {
          a.dataset.pswpWidth = 1200;
          a.dataset.pswpHeight = 900;
          res();
        };
        img.src = src;
      });
    }));
  }

// 🎨 Toggle a CSS filter class on the current image
function toggleFilter(pswp, filterClass) {
  console.log('[PSWP] toggleFilter called →', filterClass);

  const img = getSlideImgEl(pswp);
  if (!img) {
    console.warn('[PSWP] No image element found to toggle filter');
    return;
  }

  // If "clear" button (filterClass === ''), remove all filters
  if (!filterClass) {
    img.classList.remove(
      'pswp-img-filter-greenmono',
      'pswp-img-filter-greenboost',
      'pswp-img-filter-bluemono',
      'pswp-img-filter-gray',
      'pswp-img-filter-contrast'
    );
    if (pswp.currSlide.data) {
      pswp.currSlide.data._filterClass = '';
    }
    console.log('[PSWP] Cleared all filters');
    return;
  }

  // Toggle the selected filter class
  const active = img.classList.toggle(filterClass);

  // If we just activated this filter, remove all others to avoid overlap
  if (active) {
    [
      'pswp-img-filter-greenmono',
      'pswp-img-filter-greenboost',
      'pswp-img-filter-bluemono',
      'pswp-img-filter-gray',
      'pswp-img-filter-contrast'
    ].forEach(cls => {
      if (cls !== filterClass) img.classList.remove(cls);
    });
    if (pswp.currSlide.data) {
      pswp.currSlide.data._filterClass = filterClass;
    }
    console.log('[PSWP] Activated filter:', filterClass);
  } else {
    if (pswp.currSlide.data) {
      pswp.currSlide.data._filterClass = '';
    }
    console.log('[PSWP] Deactivated filter:', filterClass);
  }
}



  // 📦 Launch the PhotoSwipe viewer
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

    // 🌍 Expose globally for manual testing
    window.pswpLightbox = lightbox;
    window.getSlideImgEl = getSlideImgEl;

    // 🔧 Mark PDFs as html and all others as image
    lightbox.addFilter('itemData', (item) => {
      const el = item.element;
      const type = el?.dataset?.pswpType;

      if (type === 'html') {
        item.type = 'html';
        item.html = el.dataset.pswpHtml;
      } else {
        item.type = 'image';
      }

      return item;
    });

    // 🎯 On slide change, reapply remembered filter
    lightbox.on('change', () => {
      const pswp = lightbox.pswp;
      const f = pswp?.currSlide?.data?._filterClass || '';
      console.log('[PSWP] Slide changed → reapplying filter:', f);
      applyFilter(pswp, f);
    });

    // 🧰 Register filter buttons in the top bar
    lightbox.on('uiRegister', function () {
      const pswp = lightbox.pswp;

      // z-index fix
      pswp.ui.registerElement({
        name: 'zfix',
        order: 1,
        isButton: false,
        appendTo: 'bar',
        onInit: (el) => {
          const bar = el.closest('.pswp__top-bar');
          if (bar) bar.style.zIndex = '200';
        }
      });

      const mkBtn = (name, label, filterClass) => {
        pswp.ui.registerElement({
          name,
          order: 30,
          isButton: true,
          tagName: 'button',
          html: label,
          appendTo: 'bar',
          onClick: (event, el, pswpInstance) => {
            console.log('[PSWP] Filter button clicked:', name);
            toggleFilter(pswpInstance, filterClass);
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

    // 🎹 Keyboard shortcuts
    lightbox.on('open', () => {
      const pswp = lightbox.pswp;

      const handler = (e) => {
        const key = (e.key || '').toLowerCase();
        console.log('[PSWP] Key pressed:', key);

        switch (key) {
          case 'r': return toggleFilter(pswp, 'pswp-img-filter-greenmono');
          case 'g': return toggleFilter(pswp, 'pswp-img-filter-greenboost');
          case 'b': return toggleFilter(pswp, 'pswp-img-filter-bluemono');
          case 'y': return toggleFilter(pswp, 'pswp-img-filter-gray');
          case 'h': return toggleFilter(pswp, 'pswp-img-filter-contrast');
          case 'c': return toggleFilter(pswp, '');
        }
      };

      document.addEventListener('keydown', handler);
      pswp.on('destroy', () => {
        document.removeEventListener('keydown', handler);
      });
    });

    console.log('[PSWP] Initializing lightbox');
    lightbox.init();

    // 🧭 Start at first image (not a PDF)
    const links = Array.from(galleryEl.querySelectorAll('a'));
    let firstImageIndex = links.findIndex(a => (a.dataset.pswpType || 'image') === 'image');
    if (firstImageIndex === -1) firstImageIndex = 0;

    console.log('[PSWP] Opening gallery at index:', typeof index === 'number' ? index : firstImageIndex);
    lightbox.loadAndOpen(typeof index === 'number' ? index : firstImageIndex);
  };
})();
