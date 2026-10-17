from types import SimpleNamespace

from project_export import stage_ocr


def _att(uuid, dr_status, gl_status):
    return {
        "attachment_uuid": uuid, "report_type": "aiReport", "camera_type": "FOP", "filename": None,
        "ocr": {
            "dr_report": {"diabetic_retinopathy_report_id": 7, "promotion_status": dr_status},
            "glaucoma_report": {"glaucoma_report_id": 9, "promotion_status": gl_status},
        },
    }


def test_duplicate_pdfs_dropped_and_reports_link_to_primary_pdf(monkeypatch):
    found = {1: {
        "dr": [{"id": 7, "uuid": "dr-7", "result": "ok"}],
        "glaucoma": [{"id": 9, "uuid": "gl-9", "result": "ok"}],
        "attachments": [
            _att("a1", "created_clinical_report", "created_clinical_report"),
            _att("a2", "not_promoted_duplicate", "not_promoted_duplicate"),
        ],
    }}
    monkeypatch.setattr(stage_ocr, "_load_encounter_ocr_reports", lambda *_: found)
    ctx = SimpleNamespace(db=None, scope=None, encounters=[SimpleNamespace(id=1, uuid="enc")])

    built = stage_ocr.build(ctx)

    assert [r["document_uuid"] for r in built["report_documents"]] == ["a1"]
    assert built["report_documents"][0]["camera_type"] == "FOP"
    assert [(r["report_uuid"], r["document_uuid"]) for r in built["ocr_reports"]] == [("dr-7", "a1"), ("gl-9", "a1")]


def test_ai_comment_fields_parsed():
    from project_export.stage_grading import _ai_comment_fields

    text = "AI probability: 0.5144\nPrediction ID: x\nPredicted class: 0\nPredicted class name: Glaucoma Absent\nExternal request ID:"
    assert _ai_comment_fields(text) == {"ai_probability": 0.5144, "ai_predicted_class_name": "Glaucoma Absent"}
    assert _ai_comment_fields("looks fine") == {"ai_probability": None, "ai_predicted_class_name": None}
