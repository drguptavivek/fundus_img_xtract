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

  // 🎨 Toggle a CSS filter class on the current image
  function toggleFilter(pswp, filterClass) {
    const img = getSlideImgEl(pswp);
    if (!img) {
      console.log('[PSWP] No image element found to toggle filter');
      return;
    }

    if (!filterClass) {
      // clear all
      img.classList.remove(
        'pswp-img-filter-greenmono',
        'pswp-img-filter-greenboost',
        'pswp-img-filter-bluemono',
        'pswp-img-filter-gray',
        'pswp-img-filter-contrast'
      );
      if (pswp.currSlide?.data) pswp.currSlide.data._filterClass = '';
      console.log('[PSWP] Cleared all filters');
      return;
    }

    const active = img.classList.toggle(filterClass);
    // remove others
    [
      'pswp-img-filter-greenmono',
      'pswp-img-filter-greenboost',
      'pswp-img-filter-bluemono',
      'pswp-img-filter-gray',
      'pswp-img-filter-contrast'
    ].forEach(cls => { if (cls !== filterClass) img.classList.remove(cls); });

    if (pswp.currSlide?.data) pswp.currSlide.data._filterClass = active ? filterClass : '';
    console.log(active ? '[PSWP] Activated filter:' : '[PSWP] Deactivated filter:', filterClass);
  }

  function focusPswpRoot(pswp) {
    try { pswp?.element?.focus(); } catch (_) { }
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

  // 📦 Launch PhotoSwipe
  window.openPswpGallery = async function (galleryId, index) {
    const galleryEl = document.getElementById(galleryId);
    if (!galleryEl) return;
    if (!window.PhotoSwipeLightbox || !window.PhotoSwipe) {
      console.error('[PSWP] PhotoSwipe scripts not loaded');
      return;
    }
    await ensureNaturalSizes(galleryEl);
    if (lightbox) { try { lightbox.destroy(); } catch (_) { } lightbox = null; }

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

    // PDFs as HTML
    lightbox.addFilter('itemData', (item) => {
      if (item.element?.dataset?.pswpType === 'html') {
        item.type = 'html';
        item.html = item.element.dataset.pswpHtml;
      } else {
        item.type = 'image';
      }
      return item;
    });

    // UI buttons
    lightbox.on('uiRegister', function () {
      const pswp = lightbox.pswp;
      const mkBtn = (name, label, filterClass) => {
        pswp.ui.registerElement({
          name, order: 30, isButton: true, tagName: 'button',
          html: label, appendTo: 'bar',
          onClick: (event, el, pswpInstance) => {
            console.log('[PSWP] Button clicked:', name);
            toggleFilter(pswpInstance, filterClass);
            focusPswpRoot(pswpInstance);
          }
        });
      };
      mkBtn('filter-redfree', 'R', 'pswp-img-filter-greenmono');
      mkBtn('filter-greenboost', 'G', 'pswp-img-filter-greenboost');
      mkBtn('filter-bluemono', 'B', 'pswp-img-filter-bluemono');
      mkBtn('filter-gray', 'Y', 'pswp-img-filter-gray');
      mkBtn('filter-contrast', 'H', 'pswp-img-filter-contrast');
      mkBtn('filter-clear', 'C', '');

      pswp.ui.registerElement({
        name: 'custom-caption',
        order: 9, // just after counter
        isButton: false,
        appendTo: 'root',
        onInit: (el, pswp) => {
          el.classList.add('pswp__custom-caption');
          pswp.on('change', () => {
            const currSlide = pswp.currSlide;
            let caption = '';
            if (currSlide?.data?.element) {
              caption = currSlide.data.element.getAttribute('title') || '';
            }
            el.innerHTML = caption;
          });
        }
      });


      // 🔍 Zoom slider
     pswp.ui.registerElement({
  name: 'zoom-slider',
  order: 40,
  isButton: false,
  appendTo: 'bar',
  html: '<input type="range" min="0.1" max="4" step="0.1" value="1" class="pswp__zoom-slider" aria-label="Zoom">',
  onInit: (el, pswp) => {
    const slider = el.querySelector('input');

    // ✅ Allow the slider's native drag; just stop the event from reaching PSWP.
    const stopOnly = (e) => {
      e.stopPropagation();                // do NOT call preventDefault here
    };
    ['pointerdown','pointermove','pointerup',
     'touchstart','touchmove','touchend',
     'mousedown','mousemove','mouseup','click']
      .forEach(evt => slider.addEventListener(evt, stopOnly, { capture: true }));

    // Only the wheel should be fully swallowed to avoid wheel-zoom under the slider
    slider.addEventListener('wheel', (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, { capture: true, passive: false });

    // Change zoom when slider moves
    slider.addEventListener('input', () => {
      const z = parseFloat(slider.value);
      if (pswp.currSlide) {
        pswp.currSlide.zoomTo(z, {
          x: pswp.viewportSize.x / 2,
          y: pswp.viewportSize.y / 2
        }, true);
      }
    });

    // Sync slider when zoom changes via pinch/wheel/dblclick
    pswp.on('zoomPanUpdate', () => {
      if (pswp.currSlide) {
        slider.value = pswp.currSlide.currZoomLevel.toFixed(2);
      }
    });
  }
});

    });

    // Reapply on slide change
    lightbox.on('change', () => {
      const pswp = lightbox.pswp;
      const f = pswp?.currSlide?.data?._filterClass || '';
      if (f) toggleFilter(pswp, f); else toggleFilter(pswp, '');
      focusPswpRoot(pswp);
    });

    // Keyboard bindings
    lightbox.on('open', () => {
      const pswp = lightbox.pswp;
      focusPswpRoot(pswp);
      const handler = (e) => {
        const key = (e.key || '').toLowerCase();
        if (!['r', 'g', 'b', 'y', 'h', 'c'].includes(key)) return;
        e.preventDefault(); e.stopPropagation();
        switch (key) {
          case 'r': return toggleFilter(pswp, 'pswp-img-filter-greenmono');
          case 'g': return toggleFilter(pswp, 'pswp-img-filter-greenboost');
          case 'b': return toggleFilter(pswp, 'pswp-img-filter-bluemono');
          case 'y': return toggleFilter(pswp, 'pswp-img-filter-gray');
          case 'h': return toggleFilter(pswp, 'pswp-img-filter-contrast');
          case 'c': return toggleFilter(pswp, '');
        }
      };
      window.addEventListener('keydown', handler, { capture: true });
      pswp.on('destroy', () => window.removeEventListener('keydown', handler, { capture: true }));
    });

    lightbox.init();
    const links = Array.from(galleryEl.querySelectorAll('a'));
    let firstImageIndex = links.findIndex(a => (a.dataset.pswpType || 'image') === 'image');
    if (firstImageIndex === -1) firstImageIndex = 0;
    lightbox.loadAndOpen(typeof index === 'number' ? index : firstImageIndex);
  };
})();
