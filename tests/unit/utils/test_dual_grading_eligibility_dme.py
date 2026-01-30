from models import Disease, GradingTask, LinkedDiseaseGrading
from tests.helpers.factories import CoreEntityFactory, UserFactory
from tests.helpers.test_factories import TestDataFactory
from utils.dualGradingEligibility import get_user_eligibility_for_task


def test_dme_eligibility_uses_dr_permissions(db_session, core_test_data):
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

    user = UserFactory.create_with_permissions(
        db_session,
        role_name='resident',
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        can_grade_resident=True,
    )

    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab_unit.id)
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab_unit.id,
    )

    task = GradingTask(
        encounter_file_id=encounter_file.id,
        disease_id=dme.id,
        lab_unit_id=lab_unit.id,
        state='pending',
    )
    db_session.add(task)
    db_session.flush()

    assert get_user_eligibility_for_task(db_session, user.id, task.id, 'resident') is True
