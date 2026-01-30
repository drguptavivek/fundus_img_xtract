from models import Disease, GradingTask, LinkedDiseaseGrading
from services.taskCreationServices import create_or_get_task
from tests.helpers.factories import CoreEntityFactory
from tests.helpers.test_factories import TestDataFactory


def test_create_or_get_task_creates_dme_for_dr(db_session, core_test_data):
    dr = core_test_data['dr']
    lab_unit = core_test_data['lab_unit']

    dme = db_session.query(Disease).filter_by(name='DME').first()
    if dme is None:
        dme = CoreEntityFactory.create_disease(db_session, name='DME')
        db_session.flush()

    existing_link = db_session.query(LinkedDiseaseGrading).filter_by(
        primary_disease_id=dr.id,
        linked_disease_id=dme.id,
    ).first()
    if existing_link is None:
        db_session.add(LinkedDiseaseGrading(primary_disease_id=dr.id, linked_disease_id=dme.id, display_order=1))
        db_session.flush()

    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab_unit.id)
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab_unit.id,
    )

    task = create_or_get_task(
        db_session,
        kind='encounter',
        image_id=encounter_file.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
    )

    assert task.disease_id == dr.id

    dme_task = (
        db_session.query(GradingTask)
        .filter_by(encounter_file_id=encounter_file.id, disease_id=dme.id)
        .first()
    )

    assert dme_task is not None
