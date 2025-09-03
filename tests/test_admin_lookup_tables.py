import pytest
from flask import url_for
from models import User, Role, Hospital, LabUnit, Camera, Disease, Area, Session
from sqlalchemy import select


class TestAdminLookupRoutes:
    """Test cases for admin lookup tables routes."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        """Set up test data."""
        with Session() as db:
            # Create admin role and user
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            
            # Create a hospital for lab unit tests
            hospital = Hospital(name='Test Hospital')
            db.add(hospital)
            db.commit()
            
            self.admin_user_id = admin_user.id
            self.hospital_id = hospital.id

    def test_list_lookup_tables_requires_admin_role(self, client):
        """Test that lookup table routes require admin role."""
        response = client.get('/admin/hospital')
        # Should redirect to login or show unauthorized
        assert response.status_code in [302, 403]

    def test_list_hospitals_get(self, client, auth_client):
        """Test getting the hospitals list page."""
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/hospital')
        assert response.status_code == 200
        assert b'Hospital' in response.data

    def test_create_hospital_post_success(self, client, auth_client):
        """Test successfully creating a hospital."""
        auth_client.login('admin', 'password')
        
        # Create a new hospital
        response = client.post('/admin/hospital', data={
            'name': 'New Hospital'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'added successfully' in response.data
        
        # Check that hospital was added to database
        with Session() as db:
            hospital = db.execute(
                select(Hospital).where(Hospital.name == 'New Hospital')
            ).scalar_one_or_none()
            assert hospital is not None
            assert hospital.name == 'New Hospital'

    def test_create_hospital_post_duplicate(self, client, auth_client):
        """Test creating a duplicate hospital."""
        # Create a hospital first
        with Session() as db:
            hospital = Hospital(name='Existing Hospital')
            db.add(hospital)
            db.commit()
        
        auth_client.login('admin', 'password')
        
        # Try to create duplicate hospital
        response = client.post('/admin/hospital', data={
            'name': 'Existing Hospital'
        })
        
        assert response.status_code == 200
        assert b'already exists' in response.data

    def test_create_hospital_post_empty_name(self, client, auth_client):
        """Test creating a hospital with empty name."""
        auth_client.login('admin', 'password')
        
        # Try to create hospital with empty name
        response = client.post('/admin/hospital', data={
            'name': ''
        })
        
        assert response.status_code == 302  # Redirect due to flash message
        # Follow redirect to see the error message
        response = client.get(response.location)
        assert b'Name is required' in response.data

    def test_list_lab_units_get(self, client, auth_client):
        """Test getting the lab units list page."""
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/lab_unit')
        assert response.status_code == 200
        assert b'Lab Unit' in response.data

    def test_create_lab_unit_post_success(self, client, auth_client):
        """Test successfully creating a lab unit."""
        auth_client.login('admin', 'password')
        
        # Create a new lab unit
        response = client.post('/admin/lab_unit', data={
            'name': 'New Lab Unit',
            'hospital_id': self.hospital_id
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'added successfully' in response.data
        
        # Check that lab unit was added to database
        with Session() as db:
            lab_unit = db.execute(
                select(LabUnit).where(LabUnit.name == 'New Lab Unit')
            ).scalar_one_or_none()
            assert lab_unit is not None
            assert lab_unit.name == 'New Lab Unit'
            assert lab_unit.hospital_id == self.hospital_id

    def test_create_lab_unit_post_missing_hospital(self, client, auth_client):
        """Test creating a lab unit without specifying hospital."""
        auth_client.login('admin', 'password')
        
        # Try to create lab unit without hospital
        response = client.post('/admin/lab_unit', data={
            'name': 'New Lab Unit'
            # No hospital_id
        })
        
        assert response.status_code == 302  # Redirect due to flash message
        # Follow redirect to see the error message
        response = client.get(response.location)
        assert b'Hospital is required' in response.data

    def test_edit_hospital_get(self, client, auth_client):
        """Test getting the edit hospital form."""
        # Create a hospital
        with Session() as db:
            hospital = Hospital(name='Test Hospital')
            db.add(hospital)
            db.commit()
            hospital_id = hospital.id
        
        auth_client.login('admin', 'password')
        
        response = client.get(f'/admin/hospital/{hospital_id}/edit')
        assert response.status_code == 200
        assert b'Edit Hospital' in response.data
        assert b'Test Hospital' in response.data

    def test_edit_hospital_post(self, client, auth_client):
        """Test editing a hospital."""
        # Create a hospital
        with Session() as db:
            hospital = Hospital(name='Test Hospital')
            db.add(hospital)
            db.commit()
            hospital_id = hospital.id
        
        auth_client.login('admin', 'password')
        
        # Edit the hospital
        response = client.post(f'/admin/hospital/{hospital_id}/edit', data={
            'name': 'Updated Hospital'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'updated' in response.data
        
        # Check that hospital was updated in database
        with Session() as db:
            hospital = db.get(Hospital, hospital_id)
            assert hospital.name == 'Updated Hospital'

    def test_delete_hospital_post(self, client, auth_client):
        """Test deleting a hospital."""
        # Create a hospital
        with Session() as db:
            hospital = Hospital(name='Test Hospital')
            db.add(hospital)
            db.commit()
            hospital_id = hospital.id
        
        auth_client.login('admin', 'password')
        
        # Delete the hospital
        response = client.post(f'/admin/hospital/{hospital_id}/delete', follow_redirects=True)
        
        assert response.status_code == 200
        assert b'deleted' in response.data
        
        # Check that hospital was deleted from database
        with Session() as db:
            hospital = db.get(Hospital, hospital_id)
            assert hospital is None

    # Similar tests for other lookup tables (Camera, Disease, Area)
    def test_list_cameras_get(self, client, auth_client):
        """Test getting the cameras list page."""
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/camera')
        assert response.status_code == 200
        assert b'Camera' in response.data

    def test_list_diseases_get(self, client, auth_client):
        """Test getting the diseases list page."""
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/disease')
        assert response.status_code == 200
        assert b'Disease' in response.data

    def test_list_areas_get(self, client, auth_client):
        """Test getting the areas list page."""
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/area')
        assert response.status_code == 200
        assert b'Area' in response.data