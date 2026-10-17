"""ocr stage: OCR-extracted DR / AMD / glaucoma results and imported Remidio report documents.

Reuses the sync inventory loader so the export and the sync API agree on what each report row means.
"""
from __future__ import annotations

from project_sync.inventory import _load_encounter_ocr_reports

from .schema import OCR_REPORTS
from .tables import BuildContext, _json

_DISEASE = {"dr": ("dr_report", "DR"), "amd": ("amd_report", "AMD"), "glaucoma": ("glaucoma_report", "Glaucoma")}
_JSON_COLUMNS = {"ocr"}
_RENAMES = {"id": None, "uuid": "report_uuid", "attachment_uuid": "report_uuid", "filename": None}


def _row(encounter_uuid: str, source: str, disease: str | None, item: dict) -> dict:
    row = {name: None for name in OCR_REPORTS.column_names}
    row.update({"encounter_uuid": encounter_uuid, "source": source, "disease": disease})
    for key, value in item.items():
        target = _RENAMES.get(key, key)
        if target in row:
            row[target] = _json(value) if target in _JSON_COLUMNS else value
    if source == "attachment":
        row["report_file_name"] = item.get("filename")  # already None unless the lab has an identifiers grant
    return row


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    reports = _load_encounter_ocr_reports(ctx.db, ctx.scope, ctx.encounters)
    rows = []
    for encounter in ctx.encounters:
        found = reports.get(encounter.id) or {}
        for key, (source, disease) in _DISEASE.items():
            rows.extend(_row(encounter.uuid, source, disease, item) for item in found.get(key, []))
        rows.extend(_row(encounter.uuid, "attachment", None, item) for item in found.get("attachments", []))
    return {"ocr_reports": rows}
