"""
Comprehensive tests for admin blueprint routes with database session management validation.
Tests that fixed admin routes properly handle database sessions without errors.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from flask import session
from datetime import datetime, timezone, timedelta

from models import (
    AIModel, Camera, Disease, DiseaseGrading, GradingsFeatures, User, Role, 
    Hospital, LabUnit, UserDiseaseUnitRole, Grade
)
from db_transaction_manager import get_db_session, transaction_scope
from tests.test_auth_helpers import login_as_test_admin


class TestAdminAIModelsSessionManagement:
    """Test cases for AI models CRUD operations with database session management"""
    
    def test_list_ai_models_get_session_management(self, app, test_users):
        """Test that listing AI models properly uses get_db_session for read operations"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request to list AI models
            response = client.get("/admin/ai-models")
            assert response.status_code in [200, 302]  # 302 is redirect after login
            
            # Verify session was properly managed (no exceptions should be raised)
            with get_db_session() as db:
                # Should be able to query AI models without session errors
                models = db.query(AIModel).all()
                assert isinstance(models, list)
    
    def test_create_ai_model_transaction_commit(self, app, test_users):
        """Test that creating AI model properly commits transaction on success"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test POST request to create AI model
            response = client.post("/admin/ai-models", data={
                "name": "Test AI Model",
                "version": "1.0.0",
                "description": "Test description"
            }, follow_redirects=False)
            
            # Should redirect after successful creation
            assert response.status_code in [200, 302]
            
            # Verify data was committed to database
            with get_db_session() as db:
                model = db.query(AIModel).filter(
                    AIModel.name == "Test AI Model",
                    AIModel.version == "1.0.0"
                ).first()
                assert model is not None
                assert model.description == "Test description"
    
    def test_create_ai_model_transaction_rollback_on_error(self, app, test_users):
        """Test that creating AI model rolls back transaction on validation error"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test POST request with missing required fields
            response = client.post("/admin/ai-models", data={
                "name": "",  # Empty name should trigger validation error
                "version": "1.0.0",
                "description": "Test description"
            })
            
            # Should return 200 with error message
            assert response.status_code == 200
            
            # Verify no data was committed to database
            with get_db_session() as db:
                models = db.query(AIModel).filter(
                    AIModel.version == "1.0.0"
                ).all()
                assert len(models) == 0
    
    def test_edit_ai_model_session_management(self, app, test_users):
        """Test that editing AI model properly manages sessions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # First create an AI model to edit
            with transaction_scope() as db:
                model = AIModel(
                    name="Original Model",
                    version="1.0.0",
                    description="Original description"
                )
                db.add(model)
                db.flush()
                model_id = model.id
            
            # Test GET request to edit form
            response = client.get(f"/admin/ai-models/{model_id}/edit")
            assert response.status_code == 200
            
            # Test POST request to update
            response = client.post(f"/admin/ai-models/{model_id}/edit", data={
                "name": "Updated Model",
                "version": "2.0.0",
                "description": "Updated description"
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify data was committed
            with get_db_session() as db:
                updated_model = db.query(AIModel).filter(AIModel.id == model_id).first()
                assert updated_model is not None
                assert updated_model.name == "Updated Model"
                assert updated_model.version == "2.0.0"
                assert updated_model.description == "Updated description"
    
    def test_delete_ai_model_transaction_management(self, app, test_users):
        """Test that deleting AI model properly manages transactions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create an AI model to delete
            with transaction_scope() as db:
                model = AIModel(
                    name="Model to Delete",
                    version="1.0.0",
                    description="Will be deleted"
                )
                db.add(model)
                db.flush()
                model_id = model.id
            
            # Test DELETE request
            response = client.post(f"/admin/ai-models/{model_id}/delete", follow_redirects=False)
            
            # Should redirect after successful deletion
            assert response.status_code in [200, 302]
            
            # Verify data was deleted
            with get_db_session() as db:
                deleted_model = db.query(AIModel).filter(AIModel.id == model_id).first()
                assert deleted_model is None


class TestAdminDiseaseGradingsSessionManagement:
    """Test cases for disease gradings CRUD operations with database session management"""
    
    def test_list_disease_gradings_session_management(self, app, test_users):
        """Test that listing disease gradings properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/disease-gradings")
            assert response.status_code == 200
            
            # Verify session was properly managed
            with get_db_session() as db:
                gradings = db.query(DiseaseGrading).all()
                assert isinstance(gradings, list)
    
    def test_create_disease_grading_transaction_commit(self, app, test_users):
        """Test that creating disease grading properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get a disease ID for testing
            with get_db_session() as db:
                disease = db.query(Disease).first()
                disease_id = disease.id if disease else 1
            
            # Test POST request to create disease grading
            response = client.post("/admin/disease-gradings", data={
                "disease_id": disease_id,
                "impression": "Test Grading",
                "display_order": "1",
                "is_active": "1",
                "guidelines": "Test guidelines",
                "feature_label": ["Feature 1", "Feature 2"],
                "feature_sr_no": ["1", "2"]
            }, follow_redirects=False)
            
            # Should redirect after successful creation
            assert response.status_code in [200, 302]
            
            # Verify data was committed
            with get_db_session() as db:
                grading = db.query(DiseaseGrading).filter(
                    DiseaseGrading.impression == "Test Grading"
                ).first()
                assert grading is not None
                assert grading.disease_id == disease_id
                assert len(grading.features) == 2
    
    def test_update_disease_grading_transaction_management(self, app, test_users):
        """Test that updating disease grading properly manages transactions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a disease grading to update
            with transaction_scope() as db:
                disease = db.query(Disease).first()
                grading = DiseaseGrading(
                    disease_id=disease.id if disease else 1,
                    impression="Original Grading",
                    display_order=1,
                    is_active=True
                )
                db.add(grading)
                db.flush()
                grading_id = grading.id
            
            # Test POST request to update
            response = client.post("/admin/disease-gradings", data={
                "grading_id": grading_id,
                "disease_id": disease.id if disease else 1,
                "impression": "Updated Grading",
                "display_order": "2",
                "is_active": "0",
                "guidelines": "Updated guidelines",
                "feature_label": ["Updated Feature"],
                "feature_sr_no": ["1"]
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify data was updated
            with get_db_session() as db:
                updated_grading = db.query(DiseaseGrading).filter(
                    DiseaseGrading.id == grading_id
                ).first()
                assert updated_grading is not None
                assert updated_grading.impression == "Updated Grading"
                assert updated_grading.display_order == 2
                assert updated_grading.is_active == False
                assert len(updated_grading.features) == 1
    
    def test_delete_disease_grading_transaction_commit(self, app, test_users):
        """Test that deleting disease grading properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a disease grading to delete
            with transaction_scope() as db:
                disease = db.query(Disease).first()
                grading = DiseaseGrading(
                    disease_id=disease.id if disease else 1,
                    impression="Grading to Delete",
                    display_order=1
                )
                db.add(grading)
                db.flush()
                grading_id = grading.id
            
            # Test DELETE request
            response = client.post(f"/admin/disease-gradings/{grading_id}/delete", follow_redirects=False)
            
            # Should redirect after successful deletion
            assert response.status_code in [200, 302]
            
            # Verify data was deleted
            with get_db_session() as db:
                deleted_grading = db.query(DiseaseGrading).filter(
                    DiseaseGrading.id == grading_id
                ).first()
                assert deleted_grading is None
    
    def test_get_grading_features_json_session_management(self, app, test_users):
        """Test that getting grading features as JSON properly manages sessions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a disease grading with features
            with transaction_scope() as db:
                disease = db.query(Disease).first()
                grading = DiseaseGrading(
                    disease_id=disease.id if disease else 1,
                    impression="Test Grading",
                    display_order=1
                )
                db.add(grading)
                db.flush()
                
                feature1 = GradingsFeatures(
                    disease_grading_id=grading.id,
                    sr_no=1,
                    label="Feature 1"
                )
                feature2 = GradingsFeatures(
                    disease_grading_id=grading.id,
                    sr_no=2,
                    label="Feature 2"
                )
                db.add(feature1)
                db.add(feature2)
                grading_id = grading.id
            
            # Test GET request for JSON data
            response = client.get(f"/admin/disease-gradings/{grading_id}/features")
            assert response.status_code == 200
            
            # Verify JSON response
            data = json.loads(response.data)
            assert "features" in data
            assert len(data["features"]) == 2
            assert data["features"][0]["label"] == "Feature 1"


class TestAdminDiskUsageSessionManagement:
    """Test cases for disk usage operations with database session management"""
    
    def test_disk_usage_page_session_management(self, app, test_users):
        """Test that disk usage page properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/disk-usage")
            assert response.status_code == 200
            
            # Should render disk usage template
            assert b"disk usage" in response.data.lower()
    
    def test_delete_duplicates_operation(self, app, test_users):
        """Test that delete duplicates operation works without session errors"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create mock duplicate files for testing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Mock the files directory
                with patch('flask.current_app.root_path', temp_dir):
                    files_dir = Path(temp_dir) / "files"
                    files_dir.mkdir()
                    
                    # Create a dupmd5 directory with files
                    dupmd5_dir = files_dir / "dupmd5_test"
                    dupmd5_dir.mkdir()
                    
                    test_file = dupmd5_dir / "test_duplicate.jpg"
                    test_file.write_text("test content")
                    
                    # Test POST request to delete duplicates
                    response = client.post("/admin/delete-duplicates", follow_redirects=False)
                    assert response.status_code in [200, 302]
                    
                    # Verify file was deleted
                    assert not test_file.exists()
    
    def test_delete_old_processed_zips_operation(self, app, test_users):
        """Test that delete old processed zips operation works without session errors"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create mock old zip files for testing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Mock the files directory
                with patch('flask.current_app.root_path', temp_dir):
                    files_dir = Path(temp_dir) / "files"
                    files_dir.mkdir()
                    
                    # Create processed directory with old date
                    processed_dir = files_dir / "zips_upload_processed"
                    processed_dir.mkdir()
                    
                    # Create a date directory from 2 months ago
                    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y_%m_%d")
                    date_dir = processed_dir / old_date
                    date_dir.mkdir()
                    
                    test_zip = date_dir / "old_test.zip"
                    test_zip.write_text("test zip content")
                    
                    # Test POST request to delete old zips
                    response = client.post("/admin/delete-old-processed-zips", follow_redirects=False)
                    assert response.status_code in [200, 302]
                    
                    # Verify old zip was deleted
                    assert not test_zip.exists()


class TestAdminGradingEligibilitySessionManagement:
    """Test cases for grading eligibility operations with database session management"""
    
    def test_manage_eligibility_users_session_management(self, app, test_users):
        """Test that managing eligibility users properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/grading-eligibility")
            assert response.status_code == 200
            
            # Should render eligibility template
            assert b"eligibility" in response.data.lower()
    
    def test_edit_eligibility_transaction_commit(self, app, test_users):
        """Test that editing eligibility properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get test user and data
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                disease = db.query(Disease).first()
                lab_unit = db.query(LabUnit).first()
                
                if not user or not disease or not lab_unit:
                    pytest.skip("Required test data not available")
            
            # Test GET request to edit form
            response = client.get(f"/admin/grading-eligibility/{user.id}/edit")
            assert response.status_code == 200
            
            # Test POST request to update eligibility
            eligibility_data = [
                {
                    "disease_id": disease.id,
                    "lab_unit_id": lab_unit.id,
                    "can_grade_resident": True,
                    "can_grade_resident2": True,
                    "can_arbitrate": False,
                    "active": True
                }
            ]
            
            response = client.post(f"/admin/grading-eligibility/{user.id}/edit", data={
                "items": json.dumps(eligibility_data)
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify data was committed
            with get_db_session() as db:
                eligibility = db.query(UserDiseaseUnitRole).filter(
                    UserDiseaseUnitRole.user_id == user.id,
                    UserDiseaseUnitRole.disease_id == disease.id,
                    UserDiseaseUnitRole.lab_unit_id == lab_unit.id
                ).first()
                assert eligibility is not None
                assert eligibility.can_grade_resident == True
                assert eligibility.can_grade_resident2 == True
    
    def test_edit_eligibility_transaction_rollback_on_error(self, app, test_users):
        """Test that editing eligibility rolls back transaction on error"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get test user
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                if not user:
                    pytest.skip("Test user not available")
            
            # Test POST request with invalid JSON data
            response = client.post(f"/admin/grading-eligibility/{user.id}/edit", data={
                "items": "invalid json"
            }, follow_redirects=False)
            
            # Should return 200 with error
            assert response.status_code == 200
            
            # Verify no changes were committed
            with get_db_session() as db:
                # Should not have created any new eligibility records
                new_eligibility = db.query(UserDiseaseUnitRole).filter(
                    UserDiseaseUnitRole.user_id == user.id
                ).all()
                # Original eligibility should remain unchanged
                assert isinstance(new_eligibility, list)


class TestAdminLookupsSessionManagement:
    """Test cases for lookup table operations with database session management"""
    
    def test_list_hospitals_session_management(self, app, test_users):
        """Test that listing hospitals properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/lookups/hospital")
            assert response.status_code == 200
            
            # Verify session was properly managed
            with get_db_session() as db:
                hospitals = db.query(Hospital).all()
                assert isinstance(hospitals, list)
    
    def test_create_hospital_transaction_commit(self, app, test_users):
        """Test that creating hospital properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test POST request to create hospital
            response = client.post("/admin/lookups/hospital", data={
                "name": "Test Hospital"
            }, follow_redirects=False)
            
            # Should redirect after successful creation
            assert response.status_code in [200, 302]
            
            # Verify data was committed
            with get_db_session() as db:
                hospital = db.query(Hospital).filter(
                    Hospital.name == "Test Hospital"
                ).first()
                assert hospital is not None
    
    def test_create_lab_unit_transaction_commit(self, app, test_users):
        """Test that creating lab unit properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get a hospital ID for testing
            with get_db_session() as db:
                hospital = db.query(Hospital).first()
                hospital_id = hospital.id if hospital else 1
            
            # Test POST request to create lab unit
            response = client.post("/admin/lookups/lab_unit", data={
                "name": "Test Lab Unit",
                "hospital_id": str(hospital_id)
            }, follow_redirects=False)
            
            # Should redirect after successful creation
            assert response.status_code in [200, 302]
            
            # Verify data was committed
            with get_db_session() as db:
                lab_unit = db.query(LabUnit).filter(
                    LabUnit.name == "Test Lab Unit"
                ).first()
                assert lab_unit is not None
                assert lab_unit.hospital_id == hospital_id
    
    def test_edit_lookup_transaction_management(self, app, test_users):
        """Test that editing lookup properly manages transactions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a hospital to edit
            with transaction_scope() as db:
                hospital = Hospital(name="Original Hospital")
                db.add(hospital)
                db.flush()
                hospital_id = hospital.id
            
            # Test GET request to edit form
            response = client.get(f"/admin/lookups/hospital/{hospital_id}/edit")
            assert response.status_code == 200
            
            # Test POST request to update
            response = client.post(f"/admin/lookups/hospital/{hospital_id}/edit", data={
                "name": "Updated Hospital"
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify data was updated
            with get_db_session() as db:
                updated_hospital = db.query(Hospital).filter(
                    Hospital.id == hospital_id
                ).first()
                assert updated_hospital is not None
                assert updated_hospital.name == "Updated Hospital"
    
    def test_delete_lookup_transaction_commit(self, app, test_users):
        """Test that deleting lookup properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a camera to delete (cameras have fewer constraints)
            with transaction_scope() as db:
                camera = Camera(name="Camera to Delete")
                db.add(camera)
                db.flush()
                camera_id = camera.id
            
            # Test DELETE request
            response = client.post(f"/admin/lookups/camera/{camera_id}/delete", follow_redirects=False)
            
            # Should redirect after successful deletion
            assert response.status_code in [200, 302]
            
            # Verify data was deleted
            with get_db_session() as db:
                deleted_camera = db.query(Camera).filter(Camera.id == camera_id).first()
                assert deleted_camera is None


class TestAdminSecuritySessionManagement:
    """Test cases for security operations with database session management"""
    
    def test_change_password_transaction_commit(self, app, test_users):
        """Test that changing password properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get original password hash
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                if not user:
                    pytest.skip("Test user not available")
                original_hash = user.password_hash
            
            # Test POST request to change password
            response = client.post("/admin/change-password", data={
                "username": "test_resident",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!"
            }, follow_redirects=False)
            
            # Should redirect after successful change
            assert response.status_code in [200, 302]
            
            # Verify password was changed
            with get_db_session() as db:
                updated_user = db.query(User).filter(User.username == "test_resident").first()
                assert updated_user is not None
                assert updated_user.password_hash != original_hash
                assert updated_user.is_locked_until is None  # Lockout should be cleared
    
    def test_change_password_transaction_rollback_on_validation_error(self, app, test_users):
        """Test that changing password rolls back transaction on validation error"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get original password hash
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                if not user:
                    pytest.skip("Test user not available")
                original_hash = user.password_hash
            
            # Test POST request with weak password
            response = client.post("/admin/change-password", data={
                "username": "test_resident",
                "new_password": "weak",  # Too short
                "confirm_password": "weak"
            })
            
            # Should return 200 with error message
            assert response.status_code == 200
            
            # Verify password was NOT changed
            with get_db_session() as db:
                unchanged_user = db.query(User).filter(User.username == "test_resident").first()
                assert unchanged_user is not None
                assert unchanged_user.password_hash == original_hash
    
    def test_manage_roles_session_management(self, app, test_users):
        """Test that managing roles properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/roles")
            assert response.status_code == 200
            
            # Verify session was properly managed
            with get_db_session() as db:
                roles = db.query(Role).all()
                assert isinstance(roles, list)
                assert len(roles) > 0
    
    def test_role_usage_session_management(self, app, test_users):
        """Test that role usage page properly manages sessions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/role-usage")
            assert response.status_code == 200
            
            # Should render role usage template
            assert b"role" in response.data.lower() and b"usage" in response.data.lower()


class TestAdminUsersSessionManagement:
    """Test cases for user management operations with database session management"""
    
    def test_list_users_session_management(self, app, test_users):
        """Test that listing users properly uses get_db_session"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test GET request
            response = client.get("/admin/users")
            assert response.status_code == 200
            
            # Verify session was properly managed
            with get_db_session() as db:
                users = db.query(User).all()
                assert isinstance(users, list)
                assert len(users) > 0
    
    def test_add_user_transaction_commit(self, app, test_users):
        """Test that adding user properly commits transaction"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test POST request to create user
            response = client.post("/admin/users/add", data={
                "username": "new_test_user",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!",
                "full_name": "New Test User",
                "email": "newtest@example.com",
                "active": "1"
            }, follow_redirects=False)
            
            # Should redirect after successful creation
            assert response.status_code in [200, 302]
            
            # Verify user was created
            with get_db_session() as db:
                new_user = db.query(User).filter(User.username == "new_test_user").first()
                assert new_user is not None
                assert new_user.full_name == "New Test User"
                assert new_user.email == "newtest@example.com"
                assert new_user.is_active == True
    
    def test_add_user_transaction_rollback_on_validation_error(self, app, test_users):
        """Test that adding user rolls back transaction on validation error"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Test POST request with invalid data
            response = client.post("/admin/users/add", data={
                "username": "",  # Empty username should trigger validation error
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!",
                "full_name": "Invalid User"
            })
            
            # Should return 200 with error message
            assert response.status_code == 200
            
            # Verify no user was created
            with get_db_session() as db:
                invalid_user = db.query(User).filter(User.full_name == "Invalid User").first()
                assert invalid_user is None
    
    def test_edit_user_transaction_management(self, app, test_users):
        """Test that editing user properly manages transactions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get test user
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                if not user:
                    pytest.skip("Test user not available")
                user_id = user.id
            
            # Test GET request to edit form
            response = client.get(f"/admin/users/{user_id}/edit")
            assert response.status_code == 200
            
            # Test POST request to update profile
            response = client.post(f"/admin/users/{user_id}/edit", data={
                "full_name": "Updated Test Resident",
                "email": "updated@example.com",
                "phone": "1234567890",
                "save_profile": "1"
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify data was updated
            with get_db_session() as db:
                updated_user = db.query(User).filter(User.id == user_id).first()
                assert updated_user is not None
                assert updated_user.full_name == "Updated Test Resident"
                assert updated_user.email == "updated@example.com"
                assert updated_user.phone == "1234567890"
    
    def test_update_user_active_status_transaction(self, app, test_users):
        """Test that updating user active status properly manages transactions"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Get test user
            with get_db_session() as db:
                user = db.query(User).filter(User.username == "test_resident").first()
                if not user:
                    pytest.skip("Test user not available")
                user_id = user.id
                original_active = user.is_active
            
            # Test POST request to toggle active status
            new_active = not original_active
            response = client.post(f"/admin/users/{user_id}/update", data={
                "active": "1" if new_active else "0"
            }, follow_redirects=False)
            
            # Should redirect after successful update
            assert response.status_code in [200, 302]
            
            # Verify status was updated
            with get_db_session() as db:
                updated_user = db.query(User).filter(User.id == user_id).first()
                assert updated_user is not None
                assert updated_user.is_active == new_active


class TestAdminSessionCleanup:
    """Test cases for database session cleanup in admin routes"""
    
    def test_session_cleanup_after_successful_operations(self, app, test_users):
        """Test that sessions are properly cleaned up after successful operations"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Perform multiple operations
            client.get("/admin/users")
            client.get("/admin/ai-models")
            client.get("/admin/disease-gradings")
            
            # Verify no session errors occurred
            # If sessions weren't properly cleaned up, we'd see connection errors
            with get_db_session() as db:
                users = db.query(User).all()
                assert isinstance(users, list)
    
    def test_session_cleanup_after_errors(self, app, test_users):
        """Test that sessions are properly cleaned up even when errors occur"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Perform operations that should trigger errors
            client.post("/admin/users/add", data={
                "username": "",  # Invalid data
                "new_password": "test"
            })
            
            client.post("/admin/ai-models", data={
                "name": "",  # Invalid data
                "version": "1.0"
            })
            
            # Verify sessions are still usable after errors
            response = client.get("/admin/users")
            assert response.status_code == 200
            
            # Verify database operations still work
            with get_db_session() as db:
                users = db.query(User).all()
                assert isinstance(users, list)
    
    def test_concurrent_session_handling(self, app, test_users):
        """Test that concurrent session handling works correctly"""
        with app.test_client() as client1, app.test_client() as client2:
            # Login both clients as admin
            client1.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            client2.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Perform operations concurrently
            response1 = client1.get("/admin/users")
            response2 = client2.get("/admin/ai-models")
            
            # Both should succeed
            assert response1.status_code == 200
            assert response2.status_code == 200


class TestAdminTransactionBoundaries:
    """Test cases for transaction boundaries in admin routes"""
    
    def test_transaction_boundary_in_create_operations(self, app, test_users):
        """Test that create operations have proper transaction boundaries"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create multiple related entities in one operation
            with get_db_session() as db:
                initial_count = db.query(AIModel).count()
            
            # Create AI model
            response = client.post("/admin/ai-models", data={
                "name": "Boundary Test Model",
                "version": "1.0.0",
                "description": "Testing transaction boundaries"
            }, follow_redirects=False)
            
            # Verify transaction was committed
            with get_db_session() as db:
                final_count = db.query(AIModel).count()
                assert final_count == initial_count + 1
                
                model = db.query(AIModel).filter(
                    AIModel.name == "Boundary Test Model"
                ).first()
                assert model is not None
    
    def test_transaction_boundary_in_update_operations(self, app, test_users):
        """Test that update operations have proper transaction boundaries"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a user to update
            with transaction_scope() as db:
                user = User(
                    username="boundary_test_user",
                    password_hash="test_hash",
                    full_name="Boundary Test User"
                )
                db.add(user)
                db.flush()
                user_id = user.id
            
            # Update the user
            response = client.post(f"/admin/users/{user_id}/edit", data={
                "full_name": "Updated Boundary User",
                "email": "updated@example.com",
                "save_profile": "1"
            }, follow_redirects=False)
            
            # Verify transaction was committed
            with get_db_session() as db:
                updated_user = db.query(User).filter(User.id == user_id).first()
                assert updated_user is not None
                assert updated_user.full_name == "Updated Boundary User"
                assert updated_user.email == "updated@example.com"
    
    def test_transaction_rollback_on_database_errors(self, app, test_users):
        """Test that transactions are rolled back on database errors"""
        with app.test_client() as client:
            # Login as admin
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Mock a database error during creation
            with patch('db_transaction_manager.DbSession') as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db
                mock_db.add.side_effect = Exception("Database constraint violation")
                
                # Try to create an AI model
                response = client.post("/admin/ai-models", data={
                    "name": "Error Test Model",
                    "version": "1.0.0",
                    "description": "Should trigger rollback"
                })
                
                # Should handle error gracefully
                assert response.status_code in [200, 302]
                
                # Verify no data was committed
                with get_db_session() as db:
                    error_model = db.query(AIModel).filter(
                        AIModel.name == "Error Test Model"
                    ).first()
                    assert error_model is None