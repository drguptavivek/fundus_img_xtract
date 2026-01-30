"""
Test Data Factories

Provides factory functions to create test data with proper relationships.
"""

from typing import List, Optional
from models import User, Role, Hospital, LabUnit, Disease, UserDiseaseUnitRole
from auth.security import hash_password


class UserFactory:
    """Factory to create users with specific roles and permissions"""
    
    @staticmethod
    def create_admin(db_session, username='test_admin', password='Test@2026'):
        """Create admin user with all permissions"""
        admin_role = db_session.query(Role).filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(name='admin')
            db_session.add(admin_role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[admin_role],
            is_active=True,
            full_name=f'Test Admin ({username})'
        )
        db_session.add(user)
        db_session.flush()
        return user
    
    @staticmethod
    def create_ophthalmologist(db_session, username='test_ophthalmologist', 
                              password='Test@2026', lab_units=None):
        """Create ophthalmologist with specific lab units"""
        oph_role = db_session.query(Role).filter_by(name='ophthalmologist').first()
        if not oph_role:
            oph_role = Role(name='ophthalmologist')
            db_session.add(oph_role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[oph_role],
            is_active=True,
            full_name=f'Test Ophthalmologist ({username})'
        )
        db_session.add(user)
        db_session.flush()
        
        if lab_units:
            user.lab_units.extend(lab_units)
            db_session.flush()
        
        return user
    
    @staticmethod
    def create_by_role(db_session, role_name, username=None, password='Test@2026', **kwargs):
        """Generic factory for any role"""
        if username is None:
            username = f'test_{role_name}'
        
        role = db_session.query(Role).filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[role],
            is_active=kwargs.get('is_active', True),
            full_name=kwargs.get('full_name', f'Test {role_name.title()} ({username})')
        )
        db_session.add(user)
        db_session.flush()
        
        # Add lab units if provided
        if 'lab_units' in kwargs:
            user.lab_units.extend(kwargs['lab_units'])
            db_session.flush()
        
        return user
   
    @staticmethod
    def create_with_permissions(db_session, role_name, disease_id, lab_unit_id,
                                can_grade_resident=False, can_grade_resident2=False,
                                can_arbitrate=False, username=None, password='Test@2026'):
        """Create user with specific grading permissions"""
        user = UserFactory.create_by_role(db_session, role_name, username, password)
        
        # Grant specific permission
        permission = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease_id,
            lab_unit_id=lab_unit_id,
            can_grade_resident=can_grade_resident,
            can_grade_resident2=can_grade_resident2,
            can_arbitrate=can_arbitrate
        )
        db_session.add(permission)
        db_session.flush()
        
        return user


    @staticmethod
    def create_with_hospital(db_session, role_name, hospital_id, lab_unit_ids=None, 
                           username=None, password='Test@2026', **kwargs):
        """Create user with hospital assignment and lab units."""
        if username is None:
            username = f'test_{role_name}_h{hospital_id}'
        
        role = db_session.query(Role).filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            hospital_id=hospital_id,
            is_master_admin=kwargs.get('is_master_admin', False),
            roles=[role],
            is_active=kwargs.get('is_active', True),
            full_name=kwargs.get('full_name', f'Test {role_name.title()} H{hospital_id}')
        )
        db_session.add(user)
        db_session.flush()
        
        # Add lab units if provided
        if lab_unit_ids:
            for lu_id in lab_unit_ids:
                lab_unit = db_session.query(LabUnit).filter_by(id=lu_id).first()
                if lab_unit:
                    user.lab_units.append(lab_unit)
            db_session.flush()
        
        return user
    
    @staticmethod
    def create_grader_with_slots(db_session, username, hospital_id, lab_unit_id, 
                                  disease_slots, password='Test@2026'):
        """
        Create grader (ophthalmologist) with specific disease slots.
        
        Args:
            db_session: Database session
            username: Username for the grader
            hospital_id: Hospital ID
            lab_unit_id: Primary lab unit ID
            disease_slots: List of dicts with disease slot config
                Example: [
                    {'disease_id': 1, 'can_grade_resident': True, 'can_grade_resident2': False},
                    {'disease_id': 2, 'can_grade_resident': False, 'can_grade_resident2': True},
                ]
            password: Password
        
        Returns:
            User with slots configured
        """
        # Create user
        user = UserFactory.create_with_hospital(
            db_session,
            role_name='ophthalmologist',
            hospital_id=hospital_id,
            lab_unit_ids=[lab_unit_id],
            username=username,
            password=password
        )
        
        # Create disease slots (UserDiseaseUnitRole)
        for slot in disease_slots:
            permission = UserDiseaseUnitRole(
                user_id=user.id,
                disease_id=slot['disease_id'],
                lab_unit_id=lab_unit_id,
                can_grade_resident=slot.get('can_grade_resident', False),
                can_grade_resident2=slot.get('can_grade_resident2', False),
                can_arbitrate=slot.get('can_arbitrate', False)
            )
            db_session.add(permission)
        
        db_session.flush()
        return user
    
    @staticmethod
    def create_grader_pool(db_session, hospital_id, lab_unit_id, glaucoma_id, dr_id, prefix='res'):
        """
        Create a pool of 4 residents + 2 arbitrators with slots across Glaucoma and DR.
        
        Returns:
            dict: {'residents': [user1, user2, user3, user4], 'arbitrators': [arb1, arb2]}
        """
        hospital_letter = 'a' if hospital_id == 1 else 'b'
        residents = []
        
        # Resident 1: Can grade R1 for both Glaucoma and DR
        res_1 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_1',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_1)
        
        # Resident 2: Can grade R1/R2 for Glaucoma, only R2 for DR
        res_2 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_2',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': False, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_2)
        
        # Resident 3: Can grade R1/R2 for DR, only R1 for Glaucoma
        res_3 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_3',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': False},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_3)
        
        # Resident 4: Can grade R1/R2 for both diseases
        res_4 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_4',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_4)
        
        # Arbitrator 1: Can arbitrate Glaucoma and DR
        arb_1 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_arb_1',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_arbitrate': True},
                {'disease_id': dr_id, 'can_arbitrate': True},
            ]
        )
        
        # Arbitrator 2: Can arbitrate Glaucoma only
        arb_2 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_arb_2',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_arbitrate': True},
            ]
        )
        
        return {
            'residents': residents,
            'arbitrators': [arb_1, arb_2],
            'all': residents + [arb_1, arb_2]
        }


class CoreEntityFactory:
    """Factory to create core entities (hospitals, lab units, diseases)"""
    
    @staticmethod
    def create_hospital(db_session, name='Test Hospital', hospital_id=None):
        """Create a test hospital"""
        hospital = Hospital(
            id=hospital_id,
            name=name
        )
        db_session.add(hospital)
        db_session.flush()
        return hospital
    
    @staticmethod
    def create_lab_unit(db_session, name='Test Lab Unit', hospital_id=1, lab_unit_id=None):
        """Create a test lab unit"""
        lab_unit = LabUnit(
            id=lab_unit_id,
            name=name,
            hospital_id=hospital_id
        )
        db_session.add(lab_unit)
        db_session.flush()
        return lab_unit
    
    @staticmethod
    def create_disease(db_session, name='Test Disease', disease_id=None):
        """Create a test disease"""
        disease = Disease(
            id=disease_id,
            name=name
        )
        db_session.add(disease)
        db_session.flush()
        return disease
    
    @staticmethod
    def setup_core_entities(db_session):
        """
        Query standard core entities for testing.

        NOTE: This method queries entities created by migrations and seed_database.
        Uses NAME-based lookups instead of ID to be resilient to ID changes.

        Entities come from two sources:
        1. Migration 691d42ba3fff: Production hospitals, lab units, diseases, cameras, areas
        2. seed_database.py: Test-specific hospitals, lab units, users, roles

        Test-specific entities take precedence when there are name collisions.
        """
        from models import Camera, Area

        # Query test hospitals (created by seed_database)
        hospital = db_session.query(Hospital).filter_by(name='Hospital A').first()
        hospital_b = db_session.query(Hospital).filter_by(name='Hospital B').first()

        # Query test lab units (created by seed_database)
        lab_unit = db_session.query(LabUnit).filter_by(name='Lab A1').first()
        lab_a1 = lab_unit  # Alias for backward compatibility
        lab_a2 = db_session.query(LabUnit).filter_by(name='Lab A2').first()
        lab_a3 = db_session.query(LabUnit).filter_by(name='Lab A3').first()
        lab_b1 = db_session.query(LabUnit).filter_by(name='Lab B1').first()
        lab_b2 = db_session.query(LabUnit).filter_by(name='Lab B2').first()
        lab_b3 = db_session.query(LabUnit).filter_by(name='Lab B3').first()

        # Query diseases (created by migration)
        glaucoma = db_session.query(Disease).filter_by(name='Glaucoma').first()
        dr = db_session.query(Disease).filter_by(name='DR').first()
        amd = db_session.query(Disease).filter_by(name='AMD').first()
        dme = db_session.query(Disease).filter_by(name='DME').first()

        # Query cameras (created by migration)
        camera = db_session.query(Camera).first()

        # Query areas (created by migration)
        area = db_session.query(Area).first()

        return {
            # Primary entities (backward compatibility)
            'hospital': hospital,
            'lab_unit': lab_unit,
            'glaucoma': glaucoma,
            'dr': dr,
            'amd': amd,
            'dme': dme,
            'camera': camera,
            'area': area,
            # Extended entities for comprehensive testing
            'hospital_a': hospital,
            'hospital_b': hospital_b,
            'lab_a1': lab_a1,
            'lab_a2': lab_a2,
            'lab_a3': lab_a3,
            'lab_b1': lab_b1,
            'lab_b2': lab_b2,
            'lab_b3': lab_b3,
        }


class ImageFactory:
    """Factory to create DirectImageUpload instances for testing."""
    
    @staticmethod
    def create_direct_upload(db_session, hospital_id, lab_unit_id, user_id=None, image_id=None, 
                           uploader=None, disease_id=1, camera_id=1, area_id=1, filename=None, **kwargs):
        """
        Create a DirectImageUpload with all required fields.
        
        Args:
            db_session: Database session
            hospital_id: Hospital ID
            lab_unit_id: Lab unit ID
            user_id: User who uploaded the image (optional if uploader provided)
            image_id: Custom UUID for image (optional)
            uploader: User object (deprecated, use user_id)
            disease_id: Disease ID
            camera_id: Camera ID (default: 1)
            area_id: Area ID (default: 1)
            filename: Original filename (default: auto-generated)
            **kwargs: Additional fields
        
        Returns:
            DirectImageUpload instance
        """
        from models import DirectImageUpload
        import uuid
        
        if filename is None:
            filename = f'test_image_{uuid.uuid4().hex[:8]}.jpg'
            
        # Determine uploader ID
        final_uploader_id = user_id
        if final_uploader_id is None and uploader:
            final_uploader_id = uploader.id
        if final_uploader_id is None:
            # Fallback for old tests: try to find an admin or user
            from models import User
            user = db_session.query(User).first()
            if user:
                final_uploader_id = user.id
            else:
                # Create a temp uploader if absolutely needed
                from tests.helpers.factories import UserFactory
                user = UserFactory.create_admin(db_session)
                db_session.flush()
                final_uploader_id = user.id

        # Determine UUID
        final_uuid = image_id if image_id else str(uuid.uuid4())
        
        image = DirectImageUpload(
            uuid=final_uuid,
            original_filename=filename,
            filename=filename,
            folder_rel=kwargs.get('folder_rel', 'files/test'),
            file_hash=kwargs.get('file_hash', uuid.uuid4().hex),
            content_hash=kwargs.get('content_hash'),
            uploader_id=final_uploader_id,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            camera_id=camera_id,
            disease_id=disease_id,
            area_id=area_id,
            is_mydriatic=kwargs.get('is_mydriatic', False),
            is_pregraded=kwargs.get('is_pregraded', False),
        )
        
        db_session.add(image)
        db_session.flush()
        return image
