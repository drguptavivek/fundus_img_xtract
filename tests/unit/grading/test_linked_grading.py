
import pytest
from flask import url_for
from models import GradingTask, LinkedDiseaseGrading, DiseaseGrading, Disease
from tests.helpers.factories import UserFactory, ImageFactory

@pytest.fixture
def linked_grading_setup(db_session, core_test_data):
    """
    Setup for linked grading tests.
    Creates:
    1. Glaucoma (Primary) and DR (Linked) diseases
    2. LinkedDiseaseGrading relationship
    3. DiseaseGradings for both
    """
    glaucoma = core_test_data['glaucoma']
    dr = core_test_data['dr']
    
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
    
    # Ensure active gradings exist for both (needed for task generation)
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
    return {'primary': glaucoma, 'linked': dr}


def test_linked_grading_eligibility_trap(client, db_session, core_test_data, linked_grading_setup):
    """
    Reproduction of fundus_img_xtract-3wu:
    User eligible for Primary but NOT Linked should be able to access Primary,
    but currently gets redirected.
    """
    glaucoma = linked_grading_setup['primary']
    dr = linked_grading_setup['linked']
    lab_unit = core_test_data['lab_unit']
    
    # 1. Create User eligible ONLY for Glaucoma
    user = UserFactory.create_with_permissions(
        db_session,
        role_name='resident',
        username='test_partial_eligibility',
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        can_grade_resident=True
    )
    # Explicitly deny DR permission (default is denied, but making sure)
    # The factory only adds one permission, so they don't have DR permission.
    
    # 2. Create Image and Primary Task
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=core_test_data['hospital'].id,
        lab_unit_id=lab_unit.id,
        disease_id=glaucoma.id,
        uploader=user
    )
    
    task = GradingTask(
        uuid="task-uuid-123",
        direct_image_upload_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        state='pending'
    )
    db_session.add(task)
    db_session.commit()
    
    # 3. Login and Access Task
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
        
    response = client.get(url_for('grading.dual_grading_task', task_uuid=task.uuid, slot_type='resident'))
    
    # 4. Assert Failure (Current Behavior)
    # Expectation: Redirected to index with error message
    assert response.status_code == 302
    assert response.location == url_for('grading.index', _external=False) or \
           response.location.endswith(url_for('grading.index'))
           
    # Check flash message
    with client.session_transaction() as sess:
        flash_messages = dict(sess['_flashes']).values()
        # The exact message from dual_grading.py:
        # flash("You are not eligible to grade this task as the selected role.", "danger")
        assert any("not eligible" in msg for msg in str(list(flash_messages)))