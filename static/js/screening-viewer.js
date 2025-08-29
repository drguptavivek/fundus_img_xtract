// static/js/screening-viewer.js
(function () {
  function initViewer(root) {
    const main = root.querySelector('.sv-main');
    const mainImg = root.querySelector('.sv-main-img');
    const prevBtn = root.querySelector('.sv-prev');
    const nextBtn = root.querySelector('.sv-next');
    const fullBtn = root.querySelector('.sv-full');
    const counter = root.querySelector('.sv-counter');
    const thumbLinks = Array.from(root.querySelectorAll('.sv-thumb-link'));

    // Build URL list; fallback to main image if no thumbnails present
    let urls = thumbLinks.map(a => a.querySelector('img')?.src).filter(Boolean);
    if ((!urls.length) && mainImg && mainImg.getAttribute('src')) {
      urls = [mainImg.getAttribute('src')];
    }
    if (!urls.length || !mainImg) return;

    let index = parseInt(mainImg.dataset.index || '0', 10) || 0;

    function setCounter(i) {
      if (counter) counter.textContent = `${i + 1} / ${urls.length}`;
    }

    function prefetch(i) {
      const n = (i + 1) % urls.length;
      const p = (i - 1 + urls.length) % urls.length;
      [n, p].forEach(k => {
        const img = new Image();
        img.src = urls[k];
      });
    }

    function setActive(i) {
      index = (i + urls.length) % urls.length; // wrap-around
      mainImg.src = urls[index];
      mainImg.alt = thumbLinks[index]?.title || '';
      mainImg.dataset.index = String(index);
      thumbLinks.forEach(t => t.classList.remove('active'));
      if (thumbLinks[index]) thumbLinks[index].classList.add('active');
      setCounter(index);
      prefetch(index);
    }

    // Events
    prevBtn?.addEventListener('click', () => setActive(index - 1));
    nextBtn?.addEventListener('click', () => setActive(index + 1));
    thumbLinks.forEach((a, i) => a.addEventListener('click', () => setActive(i)));

    // Keyboard arrows when viewer focused
    main.tabIndex = 0;
    main.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') setActive(index - 1);
      else if (e.key === 'ArrowRight') setActive(index + 1);
      else if (e.key?.toLowerCase() === 'f') toggleFullscreen();
      else if (e.key === 'Escape') exitFullscreen();
    });

    // Fullscreen (Fullscreen API)
    function isFullscreen() {
      return document.fullscreenElement === main;
    }
    function exitFullscreen() {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    }
    function toggleFullscreen() {
      if (!isFullscreen()) {
        main.requestFullscreen?.().catch(() => {});
      } else {
        exitFullscreen();
      }
    }
    fullBtn?.addEventListener('click', toggleFullscreen);
    // Click on main image focuses viewer for keyboard
    main.addEventListener('click', () => main.focus());

    // Init
    setActive(index);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sv-viewer-root').forEach(initViewer);
  });
})();

(function () {
  function initViewer(root) {
    const main = root.querySelector('.sv-main');
    const mainImg = root.querySelector('.sv-main-img');
    const prevBtn = root.querySelector('.sv-prev');
    const nextBtn = root.querySelector('.sv-next');
    const fullBtn = root.querySelector('.sv-full');
    const counter = root.querySelector('.sv-counter');
    const thumbsWrap = root.querySelector('.sv-thumbs');
    const thumbLinks = Array.from(root.querySelectorAll('.sv-thumb-link'));

    let urls = thumbLinks.map(a => a.querySelector('img')?.src).filter(Boolean);
    if ((!urls.length) && mainImg && mainImg.getAttribute('src')) {
      urls = [mainImg.getAttribute('src')];
    }
    if (!urls.length || !mainImg) return;

    let index = parseInt(mainImg.dataset.index || '0', 10) || 0;


    function setCounter(i) {
      if (counter) counter.textContent = `${i + 1} / ${urls.length}`;
    }
    function prefetch(i) {
      const n = (i + 1) % urls.length, p = (i - 1 + urls.length) % urls.length;
      [n, p].forEach(k => { const im = new Image(); im.src = urls[k]; });
    }
    function setActive(i) {
      index = (i + urls.length) % urls.length;
      mainImg.src = urls[index];
      mainImg.alt = thumbLinks[index]?.title || '';
      mainImg.dataset.index = String(index);
      thumbLinks.forEach(t => t.classList.remove('active'));
      if (thumbLinks[index]) thumbLinks[index].classList.add('active');
      setCounter(index);
      prefetch(index);
      // after image swaps, ensure height still fits
      // (in case the new image has very different aspect)

    }

    prevBtn?.addEventListener('click', () => setActive(index - 1));
    nextBtn?.addEventListener('click', () => setActive(index + 1));
    thumbLinks.forEach((a, i) => a.addEventListener('click', () => setActive(i)));

    // Keyboard arrows when viewer focused
    main.tabIndex = 0;
    main.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') setActive(index - 1);
      else if (e.key === 'ArrowRight') setActive(index + 1);
      else if (e.key?.toLowerCase() === 'f') toggleFullscreen();
      else if (e.key === 'Escape') exitFullscreen();
    });

    // Fullscreen (optional)
    function isFullscreen() { return document.fullscreenElement === main; }
    function exitFullscreen() { if (document.fullscreenElement) document.exitFullscreen().catch(()=>{}); }
    function toggleFullscreen() { isFullscreen() ? exitFullscreen() : main.requestFullscreen?.().catch(()=>{}); }
    fullBtn?.addEventListener('click', toggleFullscreen);

    // Init
    setActive(index);

  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sv-viewer-root').forEach(initViewer);
  });
})();


// static/js/screening-viewer.js
(function () {
  function initViewer(root) {
    const main = root.querySelector('.sv-main');
    const mainImg = root.querySelector('.sv-main-img');
    const prevBtn = root.querySelector('.sv-prev');
    const nextBtn = root.querySelector('.sv-next');
    const counter = root.querySelector('.sv-counter');
    const filebarName = root.querySelector('.sv-filebar-name');   // 👈 NEW
    const thumbLinks = Array.from(root.querySelectorAll('.sv-thumb-link'));

    let urls = thumbLinks.map(a => a.querySelector('img')?.src).filter(Boolean);
    let names = thumbLinks.map(a => a.title || a.querySelector('img')?.getAttribute('alt') || ''); // 👈 NEW
    if ((!urls.length) && mainImg && mainImg.getAttribute('src')) {
      urls = [mainImg.getAttribute('src')];
      names = [mainImg.getAttribute('alt') || ''];
    }
    if (!urls.length || !mainImg) return;

    let index = parseInt(mainImg.dataset.index || '0', 10) || 0;

    function setCounter(i) { if (counter) counter.textContent = `${i + 1} / ${urls.length}`; }

    function setActive(i) {
      index = (i + urls.length) % urls.length;
      mainImg.src = urls[index];
      mainImg.alt = names[index] || '';
      mainImg.dataset.index = String(index);
      thumbLinks.forEach(t => t.classList.remove('active'));
      if (thumbLinks[index]) thumbLinks[index].classList.add('active');
      setCounter(index);

      // 👇 NEW: update filename text
      if (filebarName) filebarName.textContent = names[index] || mainImg.alt || '';
    }

    prevBtn?.addEventListener('click', () => setActive(index - 1));
    nextBtn?.addEventListener('click', () => setActive(index + 1));
    thumbLinks.forEach((a, i) => a.addEventListener('click', () => setActive(i)));

    // Focus for keyboard nav if you use it
    main.tabIndex = 0;

    // Init
    setActive(index);
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.sv-viewer-root').forEach(initViewer);
  });
})();
