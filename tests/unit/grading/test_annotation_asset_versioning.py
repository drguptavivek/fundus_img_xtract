from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates" / "grading"
STATIC_JS_DIR = Path(__file__).resolve().parents[3] / "static" / "js"


def test_html_grader_annotation_assets_are_cache_busted() -> None:
    expected_assets = {
        "dual_grading_task.html": (
            "feature-geometry-colors.js",
            "feature-geometry-draft.js",
            "feature-geometry-editor.js",
            "linked-grading-task.js",
            "dual-grading-task.js",
        ),
        "intra_grading_task.html": (
            "feature-geometry-colors.js",
            "feature-geometry-draft.js",
            "feature-geometry-editor.js",
            "dual-grading-task.js",
        ),
        "regrade_task_detail.html": (
            "feature-geometry-colors.js",
            "feature-geometry-draft.js",
            "feature-geometry-editor.js",
            "dual-grading-task.js",
        ),
        "_fullscreen_grading_workbench.html": (
            "feature-geometry-colors.js",
            "feature-geometry-draft.js",
            "feature-geometry-editor.js",
        ),
    }

    for template_name, asset_names in expected_assets.items():
        template = (TEMPLATES_DIR / template_name).read_text()
        for asset_name in asset_names:
            asset_call = template.split(f"filename='js/{asset_name}'", maxsplit=1)[1]
            assert "v=" in asset_call.split("}}", maxsplit=1)[0], (
                f"{asset_name} is not versioned in {template_name}"
            )


def test_linked_grader_editor_falls_back_to_shared_viewer() -> None:
    editor = (STATIC_JS_DIR / "feature-geometry-editor.js").read_text()

    assert 'panel?.querySelector(".imggr-viewer-root")' in editor
    assert '|| document.querySelector(".imggr-viewer-root")' in editor
    assert 'candidate.canvas.style.display = candidate === ctx ? "block" : "none"' in editor


def test_package_workbench_starts_annotation_editor_in_pan_mode() -> None:
    editor = (STATIC_JS_DIR / "feature-geometry-editor.js").read_text()

    assert 'document.getElementById("grading-workbench") ? MODES.PAN : MODES.ROI' in editor
