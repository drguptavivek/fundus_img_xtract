"""Test master data setup."""

import pytest
from models import (
    Session, User, Role, Hospital, LabUnit, Camera, Disease, Area, DiseaseGrading
)
from sqlalchemy import select


class TestMasterDataSetup:
    """Test cases for master data setup."""

    def test_hospitals_created(self):
        """Test that hospitals are created correctly."""
        with Session() as db:
            hospitals = db.execute(select(Hospital)).scalars().all()
            assert len(hospitals) >= 3
            
            # Check specific hospitals
            city_hospital = db.execute(
                select(Hospital).where(Hospital.name == 'City Hospital')
            ).scalar_one_or_none()
            assert city_hospital is not None
            assert city_hospital.name == 'City Hospital'

    def test_lab_units_created(self):
        """Test that lab units are created correctly."""
        with Session() as db:
            lab_units = db.execute(select(LabUnit)).scalars().all()
            assert len(lab_units) >= 6
            
            # Check lab units for City Hospital
            city_hospital = db.execute(
                select(Hospital).where(Hospital.name == 'City Hospital')
            ).scalar_one()
            
            opd_units = db.execute(
                select(LabUnit).where(
                    LabUnit.hospital_id == city_hospital.id,
                    LabUnit.name.like('%OPD%')
                )
            ).scalars().all()
            assert len(opd_units) >= 2

    def test_cameras_created(self):
        """Test that cameras are created correctly."""
        with Session() as db:
            cameras = db.execute(select(Camera)).scalars().all()
            assert len(cameras) >= 5
            
            # Check specific cameras
            topcon = db.execute(
                select(Camera).where(Camera.name == 'Topcon NW400')
            ).scalar_one_or_none()
            assert topcon is not None
            assert topcon.name == 'Topcon NW400'

    def test_diseases_created(self):
        """Test that diseases are created correctly."""
        with Session() as db:
            diseases = db.execute(select(Disease)).scalars().all()
            assert len(diseases) >= 5
            
            # Check specific diseases
            glaucoma = db.execute(
                select(Disease).where(Disease.name == 'Glaucoma')
            ).scalar_one_or_none()
            assert glaucoma is not None
            assert glaucoma.name == 'Glaucoma'
            
            dr = db.execute(
                select(Disease).where(Disease.name == 'Diabetic Retinopathy')
            ).scalar_one_or_none()
            assert dr is not None
            assert dr.name == 'Diabetic Retinopathy'

    def test_disease_gradings_created(self):
        """Test that disease gradings are created correctly."""
        with Session() as db:
            # Check Glaucoma gradings
            glaucoma = db.execute(
                select(Disease).where(Disease.name == 'Glaucoma')
            ).scalar_one_or_none()
            
            if glaucoma:
                gradings = db.execute(
                    select(DiseaseGrading).where(
                        DiseaseGrading.disease_id == glaucoma.id
                    )
                ).scalars().all()
                assert len(gradings) >= 5
                
                # Check specific gradings exist
                normal_grading = db.execute(
                    select(DiseaseGrading).where(
                        DiseaseGrading.disease_id == glaucoma.id,
                        DiseaseGrading.impression == 'Normal'
                    )
                ).scalar_one_or_none()
                assert normal_grading is not None
                assert normal_grading.impression == 'Normal'
            
            # Check Diabetic Retinopathy gradings
            dr = db.execute(
                select(Disease).where(Disease.name == 'Diabetic Retinopathy')
            ).scalar_one_or_none()
            
            if dr:
                gradings = db.execute(
                    select(DiseaseGrading).where(
                        DiseaseGrading.disease_id == dr.id
                    )
                ).scalars().all()
                assert len(gradings) >= 6

    def test_areas_created(self):
        """Test that areas are created correctly."""
        with Session() as db:
            areas = db.execute(select(Area)).scalars().all()
            assert len(areas) >= 4
            
            # Check specific areas
            urban = db.execute(
                select(Area).where(Area.name == 'Urban')
            ).scalar_one_or_none()
            assert urban is not None
            assert urban.name == 'Urban'

    def test_roles_created(self):
        """Test that roles are created correctly."""
        with Session() as db:
            roles = db.execute(select(Role)).scalars().all()
            assert len(roles) >= 7
            
            # Check specific roles exist
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one_or_none()
            assert admin_role is not None
            assert admin_role.name == 'admin'
            
            ophthalmologist_role = db.execute(
                select(Role).where(Role.name == 'ophthalmologist')
            ).scalar_one_or_none()
            assert ophthalmologist_role is not None
            assert ophthalmologist_role.name == 'ophthalmologist'
            
            resident_role = db.execute(
                select(Role).where(Role.name == 'resident')
            ).scalar_one_or_none()
            assert resident_role is not None
            assert resident_role.name == 'resident'

    def test_test_users_created(self):
        """Test that test users are created correctly."""
        with Session() as db:
            # Check admin user
            admin_user = db.execute(
                select(User).where(User.username == 'test_admin')
            ).scalar_one_or_none()
            assert admin_user is not None
            assert admin_user.username == 'test_admin'
            assert admin_user.full_name == 'Test Administrator'
            
            # Check admin has admin role
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one()
            assert admin_role in admin_user.roles
            
            # Check consultant users
            consultant = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one_or_none()
            assert consultant is not None
            assert consultant.username == 'dr_smith'
            assert consultant.full_name == 'Dr. John Smith'
            
            # Check consultant has ophthalmologist role
            ophthalmologist_role = db.execute(
                select(Role).where(Role.name == 'ophthalmologist')
            ).scalar_one()
            assert ophthalmologist_role in consultant.roles
            
            # Check resident users
            resident = db.execute(
                select(User).where(User.username == 'resident_1')
            ).scalar_one_or_none()
            assert resident is not None
            assert resident.username == 'resident_1'
            assert resident.full_name == 'Resident One'
            
            # Check resident has resident role
            resident_role = db.execute(
                select(Role).where(Role.name == 'resident')
            ).scalar_one()
            assert resident_role in resident.roles

    def test_user_lab_unit_assignments(self):
        """Test that users are assigned to lab units correctly."""
        with Session() as db:
            # Check consultant lab unit assignments
            consultant = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one()
            
            # Should be assigned to OPD Unit 1 and 2
            lab_unit_names = [lu.name for lu in consultant.lab_units]
            assert 'OPD Unit 1' in lab_unit_names
            assert 'OPD Unit 2' in lab_unit_names
            
            # Check that lab units belong to correct hospital
            city_hospital = db.execute(
                select(Hospital).where(Hospital.name == 'City Hospital')
            ).scalar_one()
            
            for lab_unit in consultant.lab_units:
                assert lab_unit.hospital_id == city_hospital.id