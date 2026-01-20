import pytest

from models import DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned
from tests.helpers.test_factories import TestDataFactory


@pytest.mark.usefixtures("seed_test_database")
def test_verify_remedio_list_shows_encounter(
    auth_client,
    hospital_data,
    hosp_a_data_manager,
    db_session,
):
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
        patient_id="VERIFY_COMBINED_PATIENT",
    )
    db_session.commit()

    user = db_session.merge(hosp_a_data_manager)
    client = auth_client(user)
    response = client.get("/verify_remedio/list")

    assert response.status_code == 200
    assert "VERIFY_COMBINED_PATIENT" in response.data.decode()


@pytest.mark.usefixtures("seed_test_database")
def test_verify_remedio_detail_creates_cleaned_rows(
    auth_client,
    hospital_data,
    hosp_a_data_manager,
    db_session,
):
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
        patient_id="VERIFY_DETAIL_PATIENT",
    )
    dr_report = DiabeticRetinopathyReport(
        patient_encounter_id=encounter.id,
        result="Mild DR",
        qualitative_result="Mild findings",
        report_file_name="dr_report.pdf",
    )
    glaucoma_report = GlaucomaReport(
        patient_encounter_id=encounter.id,
        vcdr_right="0.65",
        vcdr_left="0.45",
        result="Glaucoma Suspect",
        qualitative_result="High risk",
        report_file_name="gl_report.pdf",
    )
    db_session.add_all([dr_report, glaucoma_report])
    db_session.commit()

    user = db_session.merge(hosp_a_data_manager)
    client = auth_client(user)
    response = client.get(f"/verify_remedio/detail/{encounter.id}")

    assert response.status_code == 200
    content = response.data.decode()
    assert "Mild DR" in content
    assert "0.65" in content

    cleaned = (
        db_session.query(GlaucomaResultsCleaned)
        .filter(GlaucomaResultsCleaned.glaucoma_report_id == glaucoma_report.id)
        .first()
    )
    assert cleaned is not None
