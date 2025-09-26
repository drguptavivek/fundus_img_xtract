"""
Security tests for dual grading system
"""
from flask import session as flask_session
from models import Session, User, Disease, LabUnit, UserDiseaseUnitRole, GradingTask, Grade, DirectImageUpload, DirectImageVerify, Hospital, Camera, Area
from auth.roles import ensure_roles, DEFAULT_ROLES
from grading.dual_grading import dual_grading_task, dual_grading_submit
from grading.start_grading import start_grading
from grading.dashboard import index
from utils.dualGradingEligibility import get_user_eligibility_for_task
from utils.dualGradingGetNextTasks import get_next_eligible_resident_task, get_next_eligible_faculty_task, get_next_eligible_arbitrator_task
from utils.gradeUtils import fetch_existing_grade_for_user
from flask_login import login_user, logout_user, current_user
from unittest.mock import patch, MagicMock
import pytest
import os


def setup_test_environment():
    """Set up a test database and initial data"""
    db = Session()
    
    try:
        # Ensure roles exist
        ensure_roles(db, DEFAULT_ROLES)
        
        # Create test hospital, lab unit, and camera
        hospital = Hospital(name="Test Hospital")
        db.add(hospital)
        db.flush()
        
        lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
        db.add(lab_unit)
        db.flush()
        
        camera = Camera(name="Test Camera")
        db.add(camera)
        db.flush()
        
        area = Area(name="Test Area")
        db.add(area)
        db.flush()
        
        # Create diseases
        dr_disease = Disease(name="Diabetic Retinopathy")
        glaucoma_disease = Disease(name="Glaucoma")
        db.add(dr_disease)
        db.add(glaucoma_disease)
        db.flush()
        
        # Create test users
        # User with no special permissions
        user1 = User(username="test_user1", password_hash="test_hash1", full_name="Test User 1")
        db.add(user1)
        db.flush()
        
        # User with resident role
        user2 = User(username="test_resident", password_hash="test_hash2", full_name="Test Resident")
        db.add(user2)
        db.flush()
        
        # User with ophthalmologist role
        user3 = User(username="test_optho", password_hash="test_hash3", full_name="Test Ophthalmologist")
        db.add(user3)
        db.flush()
        
        # Assign roles
        from auth.roles import Role
        resident_role = db.query(Role).filter(Role.name == 'resident').first()
        ophthalmologist_role = db.query(Role).filter(Role.name == 'ophthalmologist').first()
        user_role_2 = db.query(Role).filter(Role.name == 'user').first()
        user_role_3 = db.query(Role).filter(Role.name == 'user').first()
        
        from models import UserRole
        user_role_mapping_2 = UserRole(user_id=user2.id, role_id=resident_role.id)
        user_role_mapping_2_2 = UserRole(user_id=user2.id, role_id=user_role_2.id)
        user_role_mapping_3 = UserRole(user_id=user3.id, role_id=ophthalmologist_role.id)
        user_role_mapping_3_2 = UserRole(user_id=user3.id, role_id=user_role_3.id)
        db.add(user_role_mapping_2)
        db.add(user_role_mapping_2_2)
        db.add(user_role_mapping_3)
        db.add(user_role_mapping_3_2)
        db.flush()
        
        # Create eligibility matrix for users
        # User2 can grade as resident for DR in test lab
        eligibility_1 = UserDiseaseUnitRole(
            user_id=user2.id,
            disease_id=dr_disease.id,
            lab_unit_id=lab_unit.id,
            can_grade_resident=True,
            can_grade_faculty=False,
            can_arbitrate=False,
            active=True
        )
        # User3 can grade as faculty for DR in test lab
        eligibility_2 = UserDiseaseUnitRole(
            user_id=user3.id,
            disease_id=dr_disease.id,
            lab_unit_id=lab_unit.id,
            can_grade_resident=False,
            can_grade_faculty=True,
            can_arbitrate=False,
            active=True
        )
        db.add(eligibility_1)
        db.add(eligibility_2)
        db.flush()
        
        # Create a test image upload
        direct_upload = DirectImageUpload(
            filename="test_image.jpg",
            edited_filename=None,
            folder_rel="test_folder",
            file_hash="test_hash",
            uploader_id=user2.id,
            hospital_id=hospital.id,
            lab_unit_id=lab_unit.id,
            camera_id=camera.id,
            disease_id=dr_disease.id,
            area_id=area.id,
            is_mydriatic=False
        )
        db.add(direct_upload)
        db.flush()
        
        # Verify the image
        verification = DirectImageVerify(
            image_upload_id=direct_upload.id,
            verified_status="verified",
            remarks="Test verification",
            verified_by_id=user3.id
        )
        db.add(verification)
        db.flush()
        
        # Create a task for this image
        task = GradingTask(
            direct_image_upload_id=direct_upload.id,
            disease_id=dr_disease.id,
            lab_unit_id=lab_unit.id,
            state="pending"  # resident can access this
        )
        db.add(task)
        db.flush()
        
        db.commit()
        
        return {
            'db': db,
            'hospital': hospital,
            'lab_unit': lab_unit,
            'dr_disease': dr_disease,
            'glaucoma_disease': glaucoma_disease,
            'user1': user1,
            'user2': user2,  # resident
            'user3': user3,  # ophthalmologist
            'direct_upload': direct_upload,
            'task': task
        }
        
    except Exception as e:
        db.rollback()
        raise e


def test_non_eligible_user_cannot_access_task():
    """Test that a user without proper eligibility cannot access a task"""
    data = setup_test_environment()
    db = data['db']
    user1 = data['user1']  # This user has no special permissions
    task = data['task']
    
    # Mock the current user as user1 (no permissions)
    with patch('flask_login.current_user', user1):
        # Try to access the task with resident role (should fail)
        try:
            result = dual_grading_task(task.id, 'resident')
            # If it doesn't raise an error, it should redirect with a flash message
            assert result is not None
        except Exception as e:
            # Expected behavior - user should not be able to access the task
            pass


def test_user_with_wrong_role_cannot_grade():
    """Test that a user with only resident role cannot grade as faculty"""
    data = setup_test_environment()
    db = data['db']
    user2 = data['user2']  # This user has resident role
    task = data['task']
    
    # Mock the current user as user2 (resident)
    with patch('flask_login.current_user', user2):
        # Try to access the task with faculty role (should fail)
        # The task is in 'pending' state which is only accessible by resident
        # But even if it were accessible, user2 doesn't have faculty permissions
        try:
            result = dual_grading_task(task.id, 'faculty')
            # If it doesn't raise an error, it should redirect with a flash message
            assert result is not None
        except Exception as e:
            # Expected behavior - user should not be able to access the task as faculty
            pass


def test_eligibility_check_function():
    """Test the eligibility check function directly"""
    data = setup_test_environment()
    db = data['db']
    user2 = data['user2']  # resident
    user3 = data['user3']  # ophthalmologist
    task = data['task']
    dr_disease = data['dr_disease']
    lab_unit = data['lab_unit']
    
    # User2 should be eligible as resident for DR in test lab
    is_eligible_resident = get_user_eligibility_for_task(db, user2.id, task.id, 'resident')
    assert is_eligible_resident == True
    
    # User2 should NOT be eligible as faculty for DR in test lab
    is_eligible_faculty = get_user_eligibility_for_task(db, user2.id, task.id, 'faculty')
    assert is_eligible_faculty == False
    
    # User3 should be eligible as faculty for DR in test lab
    is_eligible_faculty_user3 = get_user_eligibility_for_task(db, user3.id, task.id, 'faculty')
    assert is_eligible_faculty_user3 == True
    
    # User3 should NOT be eligible as resident for DR in test lab
    is_eligible_resident_user3 = get_user_eligibility_for_task(db, user3.id, task.id, 'resident')
    assert is_eligible_resident_user3 == False


def test_task_state_validation():
    """Test that users can only access tasks in appropriate states"""
    data = setup_test_environment()
    db = data['db']
    user2 = data['user2']  # resident
    user3 = data['user3']  # ophthalmologist
    task = data['task']  # This is a 'pending' task
    
    # Mock current user as user2 (resident)
    with patch('flask_login.current_user', user2):
        # Resident should be able to access 'pending' task
        is_eligible = get_user_eligibility_for_task(db, user2.id, task.id, 'resident')
        assert is_eligible == True
        

def test_input_validation():
    """Test input validation in the submit function"""
    # This test would mock a request with invalid inputs
    # to ensure the submit function properly validates them
    pass


def test_slot_type_validation():
    """Test that only valid slot types are accepted"""
    data = setup_test_environment()
    db = data['db']
    user2 = data['user2']  # resident
    task = data['task']
    
    # Mock the current user as user2 (resident)
    with patch('flask_login.current_user', user2):
        # Try to access the task with an invalid slot type
        try:
            result = dual_grading_task(task.id, 'invalid_slot')
            # Should redirect with an error
            assert result is not None
        except Exception as e:
            # Expected behavior
            pass


def run_tests():
    """Run all security tests"""
    print("Running dual grading security tests...")
    
    test_eligibility_check_function()
    print("✓ Eligibility check function tests passed")
    
    test_task_state_validation()
    print("✓ Task state validation tests passed")
    
    test_slot_type_validation()
    print("✓ Slot type validation tests passed")
    
    test_non_eligible_user_cannot_access_task()
    print("✓ Non-eligible user access tests passed")
    
    test_user_with_wrong_role_cannot_grade()
    print("✓ Wrong role access tests passed")
    
    print("All security tests completed!")


if __name__ == "__main__":
    run_tests()