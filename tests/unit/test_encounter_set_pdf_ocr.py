from pathlib import Path
from types import SimpleNamespace

from models import AMDReport, DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned, PatientEncounters
from process_pdfs import process_pdf_for_ocr
from services.encounter_referral_suggestion import derive_referral_suggestion_from_attachment_metadata


class _FakePdf:
    def insert_pdf(self, *_args, **_kwargs):
        return None

    def save(self, path):
        Path(path).write_bytes(b"%PDF-1.4\n%split\n")

    def close(self):
        return None


def test_process_pdf_for_ocr_promotes_unique_dr_and_glaucoma_reports(db_session, tmp_path, monkeypatch):
    import process_pdfs

    monkeypatch.setattr(process_pdfs, "DR_PDF_DIR", tmp_path / "dr")
    monkeypatch.setattr(process_pdfs, "GLAUCOMA_PDF_DIR", tmp_path / "glaucoma")
    monkeypatch.setattr(process_pdfs.fitz, "open", lambda *_args, **_kwargs: _FakePdf())

    def fake_ocr(_path):
        return (1, 2, "DR result", "DR qualitative", "GL result", "0.72", "0.61", "GL qualitative")

    monkeypatch.setitem(
        __import__("sys").modules,
        "ocr_extraction",
        SimpleNamespace(find_report_pages_by_coords_with_grid=fake_ocr),
    )

    encounter = PatientEncounters(
        name="Test Patient",
        patient_id="MRN1",
        capture_date="2026-05-30",
        is_set_based=True,
    )
    db_session.add(encounter)
    db_session.flush()

    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%source\n")

    result = process_pdf_for_ocr(
        db_session,
        pdf_path=pdf_path,
        patient_encounter=encounter,
        upload_date_str="2026_05_30",
    )
    db_session.commit()

    dr_report = db_session.query(DiabeticRetinopathyReport).one()
    glaucoma_report = db_session.query(GlaucomaReport).one()
    cleaned = db_session.query(GlaucomaResultsCleaned).one()

    assert result["dr_report"]["promotion_status"] == "created_clinical_report"
    assert result["dr_report"]["diabetic_retinopathy_report_id"] == dr_report.id
    assert result["dr_report"]["dr_data"] == {
        "result": "DR result",
        "qualitative_result": "DR qualitative",
    }
    assert result["glaucoma_report"]["promotion_status"] == "created_clinical_report"
    assert result["glaucoma_report"]["glaucoma_report_id"] == glaucoma_report.id
    assert result["glaucoma_report"]["glaucoma_results_cleaned_id"] == cleaned.id
    assert cleaned.vcdr_right_num == 0.72
    assert cleaned.vcdr_left_num == 0.61

    second_pdf_path = tmp_path / "report-duplicate.pdf"
    second_pdf_path.write_bytes(b"%PDF-1.4\n%source\n")
    duplicate_result = process_pdf_for_ocr(
        db_session,
        pdf_path=second_pdf_path,
        patient_encounter=encounter,
        upload_date_str="2026_05_30",
    )
    db_session.commit()

    assert duplicate_result["dr_report"]["promotion_status"] == "not_promoted_duplicate"
    assert duplicate_result["dr_report"]["diabetic_retinopathy_report_id"] == dr_report.id
    assert duplicate_result["glaucoma_report"]["promotion_status"] == "not_promoted_duplicate"
    assert duplicate_result["glaucoma_report"]["glaucoma_report_id"] == glaucoma_report.id
    assert db_session.query(DiabeticRetinopathyReport).count() == 1
    assert db_session.query(GlaucomaReport).count() == 1
    assert db_session.query(GlaucomaResultsCleaned).count() == 1


def test_process_pdf_for_ocr_promotes_dr_amd_and_glaucoma_reports(db_session, tmp_path, monkeypatch):
    import process_pdfs

    monkeypatch.setattr(process_pdfs, "DR_PDF_DIR", tmp_path / "dr")
    monkeypatch.setattr(process_pdfs, "GLAUCOMA_PDF_DIR", tmp_path / "glaucoma")
    monkeypatch.setattr(process_pdfs.fitz, "open", lambda *_args, **_kwargs: _FakePdf())

    def fake_ocr(_path):
        return (
            1,
            2,
            "No signs of DR detected.",
            "Warning: Images insufficient for accurate DR and AMD screening",
            "Signs of AMD detected. Examples of lesions are highlighted.",
            "Warning: Images insufficient for accurate DR and AMD screening",
            "Disc Suspect (High vCDR) - Referral suggested for further evaluation",
            "VCDR - 0.76 (Borderline High)",
            "VCDR - 0.00",
            "Warning: Quality insufficient for full, accurate interpretation.",
        )

    monkeypatch.setitem(
        __import__("sys").modules,
        "ocr_extraction",
        SimpleNamespace(find_report_pages_by_coords_with_grid=fake_ocr),
    )

    encounter = PatientEncounters(
        name="DR AMD Patient",
        patient_id="MRN-AMD",
        capture_date="2026-07-01",
        is_set_based=True,
    )
    db_session.add(encounter)
    db_session.flush()

    pdf_path = tmp_path / "dr-amd-glaucoma.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%source\n")

    result = process_pdf_for_ocr(
        db_session,
        pdf_path=pdf_path,
        patient_encounter=encounter,
        upload_date_str="2026_07_01",
    )
    db_session.commit()

    amd_report = db_session.query(AMDReport).one()
    dr_report = db_session.query(DiabeticRetinopathyReport).one()
    assert result["dr_report"]["dr_data"]["result"] == "No signs of DR detected."
    assert result["dr_report"]["report_file_name"] == dr_report.report_file_name
    assert result["amd_report"]["promotion_status"] == "created_clinical_report"
    assert result["amd_report"]["amd_report_id"] == amd_report.id
    assert result["amd_report"]["report_file_name"] == dr_report.report_file_name
    assert result["amd_report"]["amd_data"] == {
        "result": "Signs of AMD detected. Examples of lesions are highlighted.",
        "qualitative_result": "Warning: Images insufficient for accurate DR and AMD screening",
    }
    assert amd_report.result == "Signs of AMD detected. Examples of lesions are highlighted."
    assert amd_report.report_file_name == dr_report.report_file_name
    assert len(list((tmp_path / "dr" / "2026_07_01").glob("*.pdf"))) == 1
    assert derive_referral_suggestion_from_attachment_metadata([{"ocr": result}]) == "yes"
