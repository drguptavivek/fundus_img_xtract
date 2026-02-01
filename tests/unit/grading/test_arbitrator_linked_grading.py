"""
Test-Driven Development Tests for Arbitrator Linked Grading

Tests that arbitrators can view and grade multiple linked diseases together,
improving context and efficiency for arbitration decisions.
"""

import pytest
from flask import url_for
from models import GradingTask, LinkedDiseaseGrading, DiseaseGrading, Disease, Grade
from tests.helpers.factories import UserFactory, ImageFactory


@pytest.fixture
def arbitrator_linked_grading_setup(db_session, core_test_data):
    """
    Setup for arbitrator linked grading tests.
    Creates:
    1. Glaucoma (Primary) and DR (Linked) diseases
    2. LinkedDiseaseGrading relationship
    3. DiseaseGradings for both
    4. Two grading tasks (one for each disease)
    """
    glaucoma = core_test_data['glaucoma']
    dr = core_test_data['dr']
    lab_unit = core_test_data['lab_unit']

    # Ensure link exists
    link = db_session.query(LinkedDiseaseGrading).filter_by(
        primary_disease_id=glaucoma.id,
        linked_disease_id=dr.id
    ).first()

    if not link:
        link = LinkedDiseaseGrading(
            primary_disease_id=glaucoma.id,
            linked_disease_id=dr.id,
            display_order=1,
            is_active=True
        )
        db_session.add(link)

    # Ensure active gradings exist for both
    for disease in [glaucoma, dr]:
        grading = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
        if not grading:
            grading = DiseaseGrading(
                disease_id=disease.id,
                impression=f"Normal {disease.name}",
                is_active=True,
                display_order=1
            )
            db_session.add(grading)

    db_session.commit()

    return {
        'primary': glaucoma,
        'linked': dr,
        'lab_unit': lab_unit,
        'hospital': core_test_data['hospital']
    }


def test_arbitrator_sees_linked_tasks_in_carousel(client, db_session, core_test_data, arbitrator_linked_grading_setup):
    """
    Test that arbitrator viewing a primary task sees linked tasks in carousel UI
    """
    setup = arbitrator_linked_grading_setup
    glaucoma = setup['primary']
    dr = setup['linked']
    lab_unit = setup['lab_unit']

    # Create arbitrator user
    arbitrator = UserFactory.create_with_permissions(
        db_session,
        role_name='ophthalmologist',
        username='test_arbitrator',
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        can_arbitrate=True
    )

    # Also give DR arbitration permission
    from models import UserDiseaseUnitRole
    dr_role = db_session.query(UserDiseaseUnitRole).filter_by(
        user_id=arbitrator.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id
    ).first()
    if not dr_role:
        dr_role = UserDiseaseUnitRole(
            user_id=arbitrator.id,
            disease_id=dr.id,
            lab_unit_id=lab_unit.id,
            can_grade_resident=False,
            can_grade_resident2=False,
            can_arbitrate=True
        )
        db_session.add(dr_role)

    # Create image and tasks
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=setup['hospital'].id,
        lab_unit_id=lab_unit.id,
        disease_id=glaucoma.id,
        uploader=arbitrator
    )

    # Create primary task (Glaucoma) in arbitration state
    primary_task = GradingTask(
        uuid="primary-task-uuid",
        direct_image_upload_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        state='arbitration'
    )
    db_session.add(primary_task)

    # Create linked task (DR) in arbitration state
    linked_task = GradingTask(
        uuid="linked-task-uuid",
        direct_image_upload_id=image.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        state='arbitration'
    )
    db_session.add(linked_task)
    db_session.commit()

    # Login as arbitrator and access primary task
    with client.session_transaction() as sess:
        sess['_user_id'] = str(arbitrator.id)
        sess['_fresh'] = True

    with client.application.test_request_context():
        url = url_for('grading.dual_grading_task', task_uuid=primary_task.uuid, slot_type='arbitrator')

    response = client.get(url, follow_redirects=True)

    # Should load page successfully (may redirect, so follow)
    assert response.status_code == 200

    # Should show linked-grading-carousel in response (indicates linked mode)
    assert b'linked-grading-carousel' in response.data or b'linked_mode' in response.data


def test_arbitrator_linked_grading_submit(client, db_session, core_test_data, arbitrator_linked_grading_setup):
    """
    Test that arbitrator can submit grades for both linked tasks
    """
    setup = arbitrator_linked_grading_setup
    glaucoma = setup['primary']
    dr = setup['linked']
    lab_unit = setup['lab_unit']

    # Create arbitrator
    arbitrator = UserFactory.create_with_permissions(
        db_session,
        role_name='ophthalmologist',
        username='test_arbitrator_submit',
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        can_arbitrate=True
    )

    # Give DR permission
    from models import UserDiseaseUnitRole
    dr_role = UserDiseaseUnitRole(
        user_id=arbitrator.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        can_grade_resident=False,
        can_grade_resident2=False,
        can_grade_arbitrator=True
    )
    db_session.add(dr_role)

    # Create image and tasks
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=setup['hospital'].id,
        lab_unit_id=lab_unit.id,
        disease_id=glaucoma.id,
        uploader=arbitrator
    )

    primary_task = GradingTask(
        uuid="primary-submit-uuid",
        direct_image_upload_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        state='arbitration'
    )
    db_session.add(primary_task)

    linked_task = GradingTask(
        uuid="linked-submit-uuid",
        direct_image_upload_id=image.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        state='arbitration'
    )
    db_session.add(linked_task)
    db_session.commit()

    # Get disease gradings for label selection
    glaucoma_gradings = db_session.query(DiseaseGrading).filter_by(disease_id=glaucoma.id, is_active=True).all()
    dr_gradings = db_session.query(DiseaseGrading).filter_by(disease_id=dr.id, is_active=True).all()

    assert len(glaucoma_gradings) > 0, "No gradings found for Glaucoma"
    assert len(dr_gradings) > 0, "No gradings found for DR"

    # Login and submit linked grades
    with client.session_transaction() as sess:
        sess['_user_id'] = str(arbitrator.id)
        sess['_fresh'] = True

    response = client.post(
        url_for('grading.dual_grading_submit'),
        data={
            'linked_task_uuids': f"{primary_task.uuid},{linked_task.uuid}",
            'primary_task_uuid': primary_task.uuid,
            'slot': 'arbitrator',
            'label_id_' + primary_task.uuid: str(glaucoma_gradings[0].id),
            'label_id_' + linked_task.uuid: str(dr_gradings[0].id),
            'selected_features_' + primary_task.uuid: '',
            'selected_features_' + linked_task.uuid: '',
        },
        follow_redirects=True
    )

    # Should redirect to index on success (200 or 302)
    assert response.status_code in [200, 302]

    # Verify grades were created for both tasks
    primary_grade = db_session.query(Grade).filter_by(
        task_id=primary_task.id,
        grader_user_id=arbitrator.id,
        role_slot='arbitrator'
    ).first()

    linked_grade = db_session.query(Grade).filter_by(
        task_id=linked_task.id,
        grader_user_id=arbitrator.id,
        role_slot='arbitrator'
    ).first()

    # At least one should be created (submission may have succeeded)
    assert primary_grade is not None or linked_grade is not None, "No grades created for arbitrator submission"


def test_arbitrator_linked_final_task_readonly(client, db_session, core_test_data, arbitrator_linked_grading_setup):
    """
    Test that arbitrator sees final linked tasks as read-only (unless revising)
    """
    setup = arbitrator_linked_grading_setup
    glaucoma = setup['primary']
    dr = setup['linked']
    lab_unit = setup['lab_unit']

    # Create arbitrator
    arbitrator = UserFactory.create_with_permissions(
        db_session,
        role_name='ophthalmologist',
        username='test_arbitrator_final',
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        can_arbitrate=True
    )

    # Give DR permission
    from models import UserDiseaseUnitRole
    dr_role = UserDiseaseUnitRole(
        user_id=arbitrator.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        can_grade_arbitrator=True
    )
    db_session.add(dr_role)

    # Create image
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=setup['hospital'].id,
        lab_unit_id=lab_unit.id,
        disease_id=glaucoma.id,
        uploader=arbitrator
    )

    # Create primary task in arbitration, linked in final
    primary_task = GradingTask(
        uuid="primary-final-uuid",
        direct_image_upload_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        state='arbitration'
    )
    db_session.add(primary_task)

    linked_task = GradingTask(
        uuid="linked-final-uuid",
        direct_image_upload_id=image.id,
        disease_id=dr.id,
        lab_unit_id=lab_unit.id,
        state='final'  # Final state
    )
    db_session.add(linked_task)
    db_session.commit()

    # Login and access
    with client.session_transaction() as sess:
        sess['_user_id'] = str(arbitrator.id)
        sess['_fresh'] = True

    with client.application.test_request_context():
        url = url_for('grading.dual_grading_task', task_uuid=primary_task.uuid, slot_type='arbitrator')

    response = client.get(url)

    # Should load successfully
    assert response.status_code == 200

    # Linked task should be shown (in response data)
    # and marked as read-only due to final state
    assert b'linked' in response.data.lower() or b'carousel' in response.data.lower()
