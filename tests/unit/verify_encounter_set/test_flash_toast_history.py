from pathlib import Path


def test_flash_toasts_are_removed_before_browser_history_restore():
    script = Path("static/js/flash-toasts.js").read_text(encoding="utf-8")

    assert "window.addEventListener('pagehide', clearRenderedFlashToasts)" in script
    assert "if (event.persisted) clearRenderedFlashToasts()" in script
    assert "el.addEventListener('hidden.bs.toast'" in script
