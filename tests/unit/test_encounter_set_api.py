import os
import pytest
import jwt
import io
from flask import url_for
from api.encounter_set import generate_mobile_token
from models import PatientEncounters, EncounterSetImage

# We need the secret for decoding in tests
JWT_SECRET = os.environ.get("JWT_SECRET", "test-secret-key-at-least-32-chars-long-!!!")
JWT_ALGORITHM = "HS256"

def test_generate_token():
    """Test JWT token generation for mobile devices."""
    token = generate_mobile_token(hospital_id=1, lab_unit_id=1, allowed_diseases=[1, 2])
    data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    
    assert data["hospital_id"] == 1
    assert data["lab_unit_id"] == 1
    assert data["allowed_diseases"] == [1, 2]

def test_upload_without_token(client):
    """Test that upload fails without a token."""
    response = client.post('/api/v1/encounter-set/upload')
    assert response.status_code == 401

def test_upload_with_invalid_token(client):
    """Test that upload fails with an invalid token."""
    response = client.post(
        '/api/v1/encounter-set/upload',
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401

def test_upload_new_encounter(client, db_session, app):
    """Test uploading an image and creating a new encounter."""
    with app.app_context():
        token = generate_mobile_token(hospital_id=1, lab_unit_id=1, allowed_diseases=[1])
        
        data = {
            'patient_id': 'PAT123',
            'patient_name': 'John Doe',
            'spatial_position': '5',
            'file': (io.BytesIO(b"fake image data"), 'test.jpg')
        }
        
        response = client.post(
            '/api/v1/encounter-set/upload',
            data=data,
            headers={"Authorization": f"Bearer {token}"},
            content_type='multipart/form-data'
        )
        
        assert response.status_code == 201
        res_data = response.get_json()
        assert res_data["message"] == "Image uploaded successfully"
        assert "encounter_id" in res_data
        assert "image_uuid" in res_data
        
        # Verify DB - use the same session that app used (via mock)
        from db_transaction_manager import get_db_session
        with get_db_session() as session:
            session.expire_all()
            encounter = session.get(PatientEncounters, res_data["encounter_id"])
            assert encounter is not None
            assert encounter.patient_id == 'PAT123'
            assert encounter.is_set_based is True

            # Query set image
            set_image = session.query(EncounterSetImage).filter_by(uuid=res_data["image_uuid"]).first()

            assert set_image is not None, f"EncounterSetImage with uuid {res_data['image_uuid']} not found"
            assert set_image.spatial_position == 5
            assert set_image.patient_encounter_id == encounter.id
