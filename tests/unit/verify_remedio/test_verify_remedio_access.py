from models import DiabeticRetinopathyReport, EncounterFile, PatientEncounters, Project
from tests.helpers.test_factories import TestDataFactory
from verify_remedio.access import classical_verification_files, classical_verification_rows


def test_legacy_verification_scope_excludes_project_rows_with_same_lab(
    db_session,
    core_test_data,
    hosp_a_data_manager,
):
    lab = db_session.merge(core_test_data["lab_a1"])
    classical = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id, patient_id="CLASSICAL_VERIFY"
    )
    project = Project(title="Verification project", code="VERIFY_SCOPE", active=True)
    db_session.add(project)
    db_session.flush()
    project_encounter = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id, patient_id="PROJECT_VERIFY"
    )
    project_encounter.project_id = project.id
    db_session.commit()

    actor = db_session.merge(hosp_a_data_manager)
    visible_ids = {
        row[0]
        for row in classical_verification_rows(
            db_session, db_session.query(PatientEncounters.id), actor
        ).all()
    }

    assert classical.id in visible_ids
    assert project_encounter.id not in visible_ids


def test_legacy_verification_scope_denies_missing_lineage(
    db_session,
    hosp_a_data_manager,
):
    encounter = PatientEncounters(
        name="Missing lab", patient_id="MISSING_LAB", capture_date="2026-08-30"
    )
    db_session.add(encounter)
    db_session.commit()

    actor = db_session.merge(hosp_a_data_manager)
    visible_ids = {
        row[0]
        for row in classical_verification_rows(
            db_session, db_session.query(PatientEncounters.id), actor
        ).all()
    }

    assert encounter.id not in visible_ids


def test_admin_bypass_still_requires_classical_parent_lineage(
    db_session,
    core_test_data,
    admin_user,
):
    lab = db_session.merge(core_test_data["lab_a1"])
    project = Project(title="Admin project", code="VERIFY_ADMIN_PROJECT", active=True)
    db_session.add(project)
    db_session.flush()
    project_encounter = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id, patient_id="ADMIN_PROJECT_VERIFY"
    )
    project_encounter.project_id = project.id
    malformed_encounter = PatientEncounters(
        name="No lineage", patient_id="ADMIN_MISSING_LAB", capture_date="2026-08-30"
    )
    db_session.add(malformed_encounter)
    db_session.commit()

    visible_ids = {
        row[0]
        for row in classical_verification_rows(
            db_session,
            db_session.query(PatientEncounters.id),
            db_session.merge(admin_user),
        ).all()
    }

    assert project_encounter.id not in visible_ids
    assert malformed_encounter.id not in visible_ids


def test_child_scope_requires_parent_and_child_lineage_to_match(
    db_session,
    core_test_data,
    admin_user,
):
    lab = db_session.merge(core_test_data["lab_a1"])
    other_lab = db_session.merge(core_test_data["lab_b1"])
    project = Project(title="Malformed child project", code="VERIFY_CHILD_PROJECT", active=True)
    db_session.add(project)
    db_session.flush()
    parent = TestDataFactory.create_patient_encounter(
        db_session, lab_unit_id=lab.id, patient_id="CHILD_LINEAGE_VERIFY"
    )
    valid = EncounterFile(
        patient_encounter_id=parent.id,
        filename="valid.jpg",
        file_type="image",
        lab_unit_id=lab.id,
        hospital_id=lab.hospital_id,
    )
    wrong_hospital = EncounterFile(
        patient_encounter_id=parent.id,
        filename="wrong-hospital.jpg",
        file_type="image",
        lab_unit_id=lab.id,
        hospital_id=other_lab.hospital_id,
    )
    project_child = EncounterFile(
        patient_encounter_id=parent.id,
        filename="project-child.jpg",
        file_type="image",
        lab_unit_id=lab.id,
        hospital_id=lab.hospital_id,
        project_id=project.id,
    )
    db_session.add_all([valid, wrong_hospital, project_child])
    db_session.commit()

    visible_ids = {
        row.id
        for row in classical_verification_files(
            db_session,
            db_session.query(EncounterFile),
            db_session.merge(admin_user),
        )
        .filter(EncounterFile.patient_encounter_id == parent.id)
        .all()
    }

    assert visible_ids == {valid.id}


def test_scoped_detail_dates_exclude_other_hospital(
    db_session,
    core_test_data,
    hosp_a_data_manager,
):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    encounter_a = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=lab_a.id,
        patient_id="DATE_SCOPE_A",
        capture_date="2026-08-30",
    )
    encounter_b = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=lab_b.id,
        patient_id="DATE_SCOPE_B",
        capture_date="2026-08-31",
    )
    db_session.add_all(
            [
                DiabeticRetinopathyReport(
                    patient_encounter_id=encounter_a.id,
                    result="No DR",
                ),
                DiabeticRetinopathyReport(
                    patient_encounter_id=encounter_b.id,
                    result="No DR",
                ),
        ]
    )
    db_session.commit()

    actor = db_session.merge(hosp_a_data_manager)
    date_rows = (
        classical_verification_rows(
            db_session,
            db_session.query(PatientEncounters.capture_date_dt),
            actor,
        )
        .join(
            DiabeticRetinopathyReport,
            DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id,
        )
        .filter(PatientEncounters.capture_date_dt.isnot(None))
        .distinct()
        .all()
    )

    assert {row[0] for row in date_rows} == {encounter_a.capture_date_dt}
