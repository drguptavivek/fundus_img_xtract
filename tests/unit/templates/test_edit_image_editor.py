from pathlib import Path


def test_editor_crop_contract_is_rectangular_and_uses_clean_base():
    """Crop remains a single rectangular selection and never clips an oval."""
    script = Path("static/js/edit_image.js").read_text(encoding="utf-8")

    assert "ctx.ellipse(" not in script
    assert "ctx.strokeRect(x, y, width, height)" in script
    assert script.count("cropBase.getContext('2d').drawImage(canvas, 0, 0)") == 1
    assert "Snapshot base once per interaction" not in script
    assert "cropped.getContext('2d').drawImage(" in script
    assert "canvas.width = cropped.width" in script
