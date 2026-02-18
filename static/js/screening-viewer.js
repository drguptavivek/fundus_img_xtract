// static/js/screening-viewer.js
(function () {
  function initViewer(root) {
    if (!root || root.dataset.svInitialized === "1") return;
    root.dataset.svInitialized = "1";

    const main = root.querySelector(".sv-main");
    const mainImg = root.querySelector(".sv-main-img");
    const prevBtn = root.querySelector(".sv-prev");
    const nextBtn = root.querySelector(".sv-next");
    const fullBtn = root.querySelector(".sv-full");
    const counter = root.querySelector(".sv-counter");
    const thumbLinks = Array.from(root.querySelectorAll(".sv-thumb-link"));

    if (!main || !mainImg) return;

    const items = thumbLinks.map((link, idx) => {
      const thumb = link.querySelector("img");
      const thumbUrl = thumb?.getAttribute("src") || "";
      const fullUrl = thumb?.getAttribute("data-full-url") || thumbUrl;
      return {
        index: idx,
        fullUrl,
        label: link.getAttribute("title") || thumb?.getAttribute("alt") || "",
      };
    }).filter((item) => item.fullUrl);

    if (!items.length) {
      const initial = mainImg.getAttribute("src");
      if (!initial) return;
      items.push({ index: 0, fullUrl: initial, label: mainImg.getAttribute("alt") || "" });
    }

    let index = parseInt(mainImg.dataset.index || "0", 10) || 0;
    if (index >= items.length) index = 0;

    function setCounter(i) {
      if (counter) counter.textContent = `${i + 1} / ${items.length}`;
    }

    function setActive(i) {
      index = (i + items.length) % items.length;
      const nextSrc = items[index].fullUrl;
      const currentSrc = mainImg.currentSrc || mainImg.src || "";
      if (nextSrc && currentSrc !== nextSrc) {
        mainImg.src = nextSrc;
      }
      mainImg.alt = items[index].label;
      mainImg.dataset.index = String(index);
      thumbLinks.forEach((t) => t.classList.remove("active"));
      if (thumbLinks[index]) thumbLinks[index].classList.add("active");
      setCounter(index);
    }

    prevBtn?.addEventListener("click", () => setActive(index - 1));
    nextBtn?.addEventListener("click", () => setActive(index + 1));
    thumbLinks.forEach((link, i) => link.addEventListener("click", () => setActive(i)));

    main.tabIndex = 0;
    main.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") setActive(index - 1);
      else if (e.key === "ArrowRight") setActive(index + 1);
      else if (e.key?.toLowerCase() === "f") toggleFullscreen();
      else if (e.key === "Escape") exitFullscreen();
    });

    function isFullscreen() {
      return document.fullscreenElement === main;
    }
    function exitFullscreen() {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    }
    function toggleFullscreen() {
      if (!isFullscreen()) main.requestFullscreen?.().catch(() => {});
      else exitFullscreen();
    }
    fullBtn?.addEventListener("click", toggleFullscreen);
    main.addEventListener("click", () => main.focus());

    setActive(index);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".sv-viewer-root").forEach(initViewer);
  });
})();
