import json
from pathlib import Path

from flask import current_app


WORKBENCH_ENTRY = "frontend/grading-workbench/main.tsx"


def get_workbench_assets() -> dict[str, object]:
    manifest_path = (
        Path(current_app.static_folder or "static")
        / "grading-workbench"
        / ".vite"
        / "manifest.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest[WORKBENCH_ENTRY]
        script = entry["file"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("The grading workbench frontend has not been built.") from exc

    styles = entry.get("css", [])
    if not isinstance(styles, list) or not all(isinstance(item, str) for item in styles):
        raise RuntimeError("The grading workbench asset manifest is invalid.")

    return {
        "script": f"grading-workbench/{script}",
        "styles": [f"grading-workbench/{item}" for item in styles],
    }
