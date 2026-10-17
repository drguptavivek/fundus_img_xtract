"""ocr stage: OCR-extracted DR / AMD / glaucoma results (`ocr_reports`) and the primary Remidio report PDFs
with their API JSON (`report_documents`).

Reuses the sync inventory loader so the export and the sync API agree on what each report row means.
"""
from __future__ import annotations

from project_sync.inventory import _load_encounter_ocr_reports

from .schema import OCR_REPORTS, REPORT_DOCUMENTS
from .tables import BuildContext, _json, _source_paths

_DISEASE = {"dr": ("dr_report", "DR"), "amd": ("amd_report", "AMD"), "glaucoma": ("glaucoma_report", "Glaucoma")}
_SUB_REPORTS = (("dr", "dr_report", "diabetic_retinopathy_report_id"), ("amd", "amd_report", "amd_report_id"),
                ("glaucoma", "glaucoma_report", "glaucoma_report_id"))
_DUPLICATE = "not_promoted_duplicate"
_CREATED = "created_clinical_report"


def _row(table, values: dict, renames: dict) -> dict:
    row = {name: None for name in table.column_names}
    for key, value in values.items():
        target = renames.get(key, key)
        if target in row:
            row[target] = _json(value) if target == "ocr" else value
    return row


def _promotions(item: dict) -> list[tuple[str, int | None, str | None]]:
    """(disease key, canonical report id, promotion status) for each report detected in a PDF's OCR block."""
    ocr = item.get("ocr") if isinstance(item.get("ocr"), dict) else {}
    return [
        (key, sub.get(id_key), sub.get("promotion_status"))
        for key, sub_key, id_key in _SUB_REPORTS
        if isinstance(sub := ocr.get(sub_key), dict)
    ]


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    reports = _load_encounter_ocr_reports(ctx.db, ctx.scope, ctx.encounters)
    ocr_rows, document_rows = [], []
    source_paths = _source_paths(ctx.db, ctx.scope)
    for encounter in ctx.encounters:
        found = reports.get(encounter.id) or {}
        # Promotion status decides which PDFs count: one whose every report was a duplicate is dropped.
        created = {}  # (disease key, canonical report id) -> primary document uuid
        for item in found.get("attachments", []):
            promos = _promotions(item)
            if promos and all(status == _DUPLICATE for *_, status in promos):
                continue
            for key, report_id, status in promos:
                if status == _CREATED and report_id is not None:
                    created[(key, report_id)] = item["attachment_uuid"]
            document_rows.append(_row(
                REPORT_DOCUMENTS,
                {**item, "encounter_uuid": encounter.uuid, "source_path": source_paths.get(encounter.id, "other")},
                {"attachment_uuid": "document_uuid", "filename": "report_file_name"},
            ))
        for key, (source, disease) in _DISEASE.items():
            for item in found.get(key, []):
                ocr_rows.append(_row(
                    OCR_REPORTS,
                    {**item, "encounter_uuid": encounter.uuid, "source": source, "disease": disease,
                     "source_path": source_paths.get(encounter.id, "other"),
                     "document_uuid": created.get((key, item.get("id")))},
                    {"id": None, "uuid": "report_uuid"},
                ))
    return {"ocr_reports": ocr_rows, "report_documents": document_rows}
