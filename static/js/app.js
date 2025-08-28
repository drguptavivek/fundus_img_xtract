
document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('flash-toasts');

  function setToastTopOffset() {
    const nav = document.querySelector('.navbar');
    const h = nav ? nav.offsetHeight : 56;   // default Bootstrap navbar ≈56px
    // add a small gap (8px) below the navbar
    container.style.setProperty('--toast-top', (h + 8) + 'px');
  }

  // set on load, on resize, and after navbar collapse toggles
  setToastTopOffset();
  window.addEventListener('resize', setToastTopOffset);
  document.querySelector('.navbar-toggler')?.addEventListener('click', () => {
    setTimeout(setToastTopOffset, 250);  // let the collapse animation finish
  });

  // auto-show any flashed toasts
  document.querySelectorAll('#flash-toasts .toast').forEach(function (el) {
    try { new bootstrap.Toast(el).show(); } catch (e) {}
  });
});
