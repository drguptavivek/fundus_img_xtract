"""Test core functionality with isolated test database."""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Base, engine, Session, User, Role, Hospital, LabUnit, Camera, Disease, Area
from sqlalchemy import create_engine, select
from auth.security import hash_password


class TestCoreFunctionality:
    """Test core functionality with isolated test database."""

    def test_master_data_creation(self):
        """Test that master data can be created without conflicts."""
        with Session() as db:
            # Create hospitals
            hospitals_data = [
                {'name': 'City Hospital'},
                {'name': 'University Medical Center'},
                {'name': 'Community Eye Clinic'}
            ]
            
            hospitals = []
            for hospital_data in hospitals_data:
                hospital = db.execute(
                    select(Hospital).where(Hospital.name == hospital_data['name'])
                ).scalar_one_or_none()
                
                if not hospital:
                    hospital = Hospital(**hospital_data)
                    db.add(hospital)
                    db.flush()
                hospitals.append(hospital)
            
            # Create lab units
            lab_units_data = [
                {'name': 'OPD Unit 1', 'hospital_id': hospitals[0].id},
                {'name': 'OPD Unit 2', 'hospital_id': hospitals[0].id},
                {'name': 'Emergency Unit', 'hospital_id': hospitals[0].id},
                {'name': 'Research Lab', 'hospital_id': hospitals[1].id},
                {'name': 'Pediatrics Unit', 'hospital_id': hospitals[1].id},
                {'name': 'General OPD', 'hospital_id': hospitals[2].id}
            ]
            
            lab_units = []
            for lab_unit_data in lab_units_data:
                lab_unit = db.execute(
                    select(LabUnit).where(
                        LabUnit.name == lab_unit_data['name'],
                        LabUnit.hospital_id == lab_unit_data['hospital_id']
                    )
                ).scalar_one_or_none()
                
                if not lab_unit:
                    lab_unit = LabUnit(**lab_unit_data)
                    db.add(lab_unit)
                    db.flush()
                lab_units.append(lab_unit)
            
            # Create cameras
            cameras_data = [
                {'name': 'Topcon NW400'},
                {'name': 'Zeiss Cirrus HD-OCT'},
                {'name': 'NIDEK AFC-300'},
                {'name': 'Canon CR-2 AF'},
                {'name': 'Kowa VX-10'}
            ]
            
            cameras = []
            for camera_data in cameras_data:
                camera = db.execute(
                    select(Camera).where(Camera.name == camera_data['name'])
                ).scalar_one_or_none()
                
                if not camera:
                    camera = Camera(**camera_data)
                    db.add(camera)
                    db.flush()
                cameras.append(camera)
            
            # Create diseases
            diseases_data = [
                {'name': 'Glaucoma'},
                {'name': 'Diabetic Retinopathy'},
                {'name': 'Age-related Macular Degeneration'},
                {'name': 'Hypertensive Retinopathy'},
                {'name': 'Retinal Vein Occlusion'}
            ]
            
            diseases = []
            for disease_data in diseases_data:
                disease = db.execute(
                    select(Disease).where(Disease.name == disease_data['name'])
                ).scalar_one_or_none()
                
                if not disease:
                    disease = Disease(**disease_data)
                    db.add(disease)
                    db.flush()
                diseases.append(disease)
            
            # Create areas
            areas_data = [
                {'name': 'Urban'},
                {'name': 'Suburban'},
                {'name': 'Rural'},
                {'name': 'Remote'}
            ]
            
            areas = []
            for area_data in areas_data:
                area = db.execute(
                    select(Area).where(Area.name == area_data['name'])
                ).scalar_one_or_none()
                
                if not area:
                    area = Area(**area_data)
                    db.add(area)
                    db.flush()
                areas.append(area)
            
            db.commit()
            
            # Verify data was created
            assert len(hospitals) >= 3
            assert len(lab_units) >= 6
            assert len(cameras) >= 5
            assert len(diseases) >= 5
            assert len(areas) >= 4

    def test_user_roles_and_assignments(self):
        """Test that users can be created with roles and lab unit assignments."""
        with Session() as db:
            # Create roles
            roles_data = [
                {'name': 'admin'},
                {'name': 'ophthalmologist'},
                {'name': 'resident'},
                {'name': 'optometrist'},
                {'name': 'data_manager'},
                {'name': 'fileUploader'},
                {'name': 'contributor'}
            ]
            
            roles = {}
            for role_data in roles_data:
                role = db.execute(
                    select(Role).where(Role.name == role_data['name'])
                ).scalar_one_or_none()
                
                if not role:
                    role = Role(**role_data)
                    db.add(role)
                    db.flush()
                roles[role_data['name']] = role
            
            # Create hospitals and lab units for user assignments
            city_hospital = db.execute(
                select(Hospital).where(Hospital.name == 'City Hospital')
            ).scalar_one_or_none()
            
            if not city_hospital:
                city_hospital = Hospital(name='City Hospital')
                db.add(city_hospital)
                db.flush()
            
            opd_unit_1 = db.execute(
                select(LabUnit).where(
                    LabUnit.name == 'OPD Unit 1',
                    LabUnit.hospital_id == city_hospital.id
                )
            ).scalar_one_or_none()
            
            if not opd_unit_1:
                opd_unit_1 = LabUnit(name='OPD Unit 1', hospital_id=city_hospital.id)
                db.add(opd_unit_1)
                db.flush()
            
            # Create users
            admin_user = db.execute(
                select(User).where(User.username == 'test_admin')
            ).scalar_one_or_none()
            
            if not admin_user:
                admin_user = User(
                    username='test_admin',
                    password_hash=hash_password('adminpassword'),
                    is_active=True,
                    full_name='Test Administrator'
                )
                admin_user.roles.append(roles['admin'])
                db.add(admin_user)
                db.flush()
            
            # Create a consultant user
            consultant_user = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one_or_none()
            
            if not consultant_user:
                consultant_user = User(
                    username='dr_smith',
                    password_hash=hash_password('smithpassword'),
                    is_active=True,
                    full_name='Dr. John Smith'
                )
                consultant_user.roles.append(roles['ophthalmologist'])
                consultant_user.lab_units.append(opd_unit_1)
                db.add(consultant_user)
                db.flush()
            
            db.commit()
            
            # Verify users were created with proper roles and assignments
            assert admin_user is not None
            assert consultant_user is not None
            
            # Verify roles
            admin_role_names = [role.name for role in admin_user.roles]
            assert 'admin' in admin_role_names
            
            consultant_role_names = [role.name for role in consultant_user.roles]
            assert 'ophthalmologist' in consultant_role_names
            
            # Verify lab unit assignments
            consultant_lab_unit_names = [lu.name for lu in consultant_user.lab_units]
            assert 'OPD Unit 1' in consultant_lab_unit_names

    def test_app_startup(self):
        """Test that the app can start with our test database."""
        # This test is mainly to verify that importing and creating the app works
        try:
            from app import create_app
            app = create_app()
            assert app is not None
            assert app.name == 'app'
            return True
        except Exception as e:
            pytest.fail(f"App failed to start: {e}")