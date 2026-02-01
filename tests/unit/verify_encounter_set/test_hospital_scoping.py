"""
Test-Driven Development Tests for Hospital Scoping in Verify Routes

Tests hospital-level isolation in verify_encounter_set routes to prevent
cross-hospital data access/modification.

Protected Routes:
- GET /verify-encounter-set/ (index)
- GET /verify-encounter-set/verify/<uuid>
- POST /verify-encounter-set/update_position
- GET /verify-encounter-set/edit/<uuid>
- POST /verify-encounter-set/save_edit/<uuid>
"""

import pytest
from uuid import uuid4
from auth.utils import utcnow


class TestHospitalScopingVerifyIndex:
    """Test hospital scoping on /verify-encounter-set/ index route"""

    @pytest.fixture
    def hospitals(self, db):
        """Create two separate hospitals"""
        from models import Hospital
        hospital1 = Hospital(name="Hospital A", code="HOSP_A")
        hospital2 = Hospital(name="Hospital B", code="HOSP_B")
        db.session.add_all([hospital1, hospital2])
        db.session.flush()
        return {"hospital1": hospital1, "hospital2": hospital2}

    @pytest.fixture
    def lab_units(self, db, hospitals):
        """Create lab units in each hospital"""
        from models import LabUnit
        unit_a = LabUnit(hospital_id=hospitals["hospital1"].id, name="Lab A1")
        unit_b = LabUnit(hospital_id=hospitals["hospital2"].id, name="Lab B1")
        db.session.add_all([unit_a, unit_b])
        db.session.flush()
        return {"unit_a": unit_a, "unit_b": unit_b}

    @pytest.fixture
    def optometrist_user_a(self, db, lab_units):
        """Create optometrist for Hospital A"""
        from models import User, Role
        user = User(username="opt_a", email="opt_a@example.com")
        user.set_password("password")
        user.hospital_id = lab_units["unit_a"].hospital_id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        # Assign to lab unit A
        user.lab_units.append(lab_units["unit_a"])
        db.session.commit()
        return user

    @pytest.fixture
    def optometrist_user_b(self, db, lab_units):
        """Create optometrist for Hospital B"""
        from models import User, Role
        user = User(username="opt_b", email="opt_b@example.com")
        user.set_password("password")
        user.hospital_id = lab_units["unit_b"].hospital_id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        # Assign to lab unit B
        user.lab_units.append(lab_units["unit_b"])
        db.session.commit()
        return user

    @pytest.fixture
    def encounters_in_hospitals(self, db, lab_units):
        """Create pending encounters in both hospitals"""
        from models import PatientEncounters

        # Encounter in Hospital A
        enc_a = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient A",
            patient_id="A001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_a"].id,
            is_set_based=True,
            encounter_verified_status="pending"
        )

        # Encounter in Hospital B
        enc_b = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient B",
            patient_id="B001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_b"].id,
            is_set_based=True,
            encounter_verified_status="pending"
        )

        db.session.add_all([enc_a, enc_b])
        db.session.commit()
        return {"enc_a": enc_a, "enc_b": enc_b}

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_index_shows_only_own_hospital_encounters(self, test_client, optometrist_user_a, encounters_in_hospitals):
        """Test that index only shows encounters from user's hospital"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # View index
            response = test_client.get('/verify-encounter-set/')

            # Should succeed
            assert response.status_code == 200, "User should access verify index"

            # Should see Hospital A encounter
            assert encounters_in_hospitals["enc_a"].uuid.encode() in response.data, \
                "Should see Hospital A encounter"

            # Should NOT see Hospital B encounter
            assert encounters_in_hospitals["enc_b"].uuid.encode() not in response.data, \
                "Should NOT see Hospital B encounter"

    def test_index_shows_different_encounters_for_hospital_b(self, test_client, optometrist_user_b, encounters_in_hospitals):
        """Test that different hospital user sees different encounters"""
        with test_client:
            # Login as optometrist from Hospital B
            test_client.post('/login', data={
                'username': 'opt_b',
                'password': 'password'
            }, follow_redirects=True)

            # View index
            response = test_client.get('/verify-encounter-set/')

            # Should succeed
            assert response.status_code == 200, "User should access verify index"

            # Should see Hospital B encounter
            assert encounters_in_hospitals["enc_b"].uuid.encode() in response.data, \
                "Should see Hospital B encounter"

            # Should NOT see Hospital A encounter
            assert encounters_in_hospitals["enc_a"].uuid.encode() not in response.data, \
                "Should NOT see Hospital A encounter"


class TestHospitalScopingVerifyEncounter:
    """Test hospital scoping on /verify-encounter-set/verify/<uuid> route"""

    @pytest.fixture
    def hospitals(self, db):
        """Create two separate hospitals"""
        from models import Hospital
        hospital1 = Hospital(name="Hospital A", code="HOSP_A")
        hospital2 = Hospital(name="Hospital B", code="HOSP_B")
        db.session.add_all([hospital1, hospital2])
        db.session.flush()
        return {"hospital1": hospital1, "hospital2": hospital2}

    @pytest.fixture
    def lab_units(self, db, hospitals):
        """Create lab units in each hospital"""
        from models import LabUnit
        unit_a = LabUnit(hospital_id=hospitals["hospital1"].id, name="Lab A1")
        unit_b = LabUnit(hospital_id=hospitals["hospital2"].id, name="Lab B1")
        db.session.add_all([unit_a, unit_b])
        db.session.flush()
        return {"unit_a": unit_a, "unit_b": unit_b}

    @pytest.fixture
    def optometrist_user_a(self, db, lab_units):
        """Create optometrist for Hospital A"""
        from models import User, Role
        user = User(username="opt_a", email="opt_a@example.com")
        user.set_password("password")
        user.hospital_id = lab_units["unit_a"].hospital_id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        user.lab_units.append(lab_units["unit_a"])
        db.session.commit()
        return user

    @pytest.fixture
    def encounters_in_hospitals(self, db, lab_units):
        """Create encounters in both hospitals"""
        from models import PatientEncounters

        enc_a = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient A",
            patient_id="A001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_a"].id,
            is_set_based=True,
            encounter_verified_status="pending"
        )

        enc_b = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient B",
            patient_id="B001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_b"].id,
            is_set_based=True,
            encounter_verified_status="pending"
        )

        db.session.add_all([enc_a, enc_b])
        db.session.commit()
        return {"enc_a": enc_a, "enc_b": enc_b}

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_verify_own_hospital_encounter_succeeds(self, test_client, optometrist_user_a, encounters_in_hospitals):
        """Test accessing own hospital encounter succeeds"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Access own hospital encounter
            response = test_client.get(f'/verify-encounter-set/verify/{encounters_in_hospitals["enc_a"].uuid}')

            # Should succeed (200 OK or 200 with page content)
            assert response.status_code == 200, "User should access own hospital encounter"

    def test_verify_cross_hospital_encounter_blocked(self, test_client, optometrist_user_a, encounters_in_hospitals):
        """Test accessing cross-hospital encounter is blocked"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Try to access Hospital B encounter
            response = test_client.get(f'/verify-encounter-set/verify/{encounters_in_hospitals["enc_b"].uuid}')

            # Should be blocked with 404
            assert response.status_code == 404, "User should NOT access cross-hospital encounter"


class TestHospitalScopingUpdatePosition:
    """Test hospital scoping on /verify-encounter-set/update_position route"""

    @pytest.fixture
    def hospitals(self, db):
        """Create two separate hospitals"""
        from models import Hospital
        hospital1 = Hospital(name="Hospital A", code="HOSP_A")
        hospital2 = Hospital(name="Hospital B", code="HOSP_B")
        db.session.add_all([hospital1, hospital2])
        db.session.flush()
        return {"hospital1": hospital1, "hospital2": hospital2}

    @pytest.fixture
    def lab_units(self, db, hospitals):
        """Create lab units in each hospital"""
        from models import LabUnit
        unit_a = LabUnit(hospital_id=hospitals["hospital1"].id, name="Lab A1")
        unit_b = LabUnit(hospital_id=hospitals["hospital2"].id, name="Lab B1")
        db.session.add_all([unit_a, unit_b])
        db.session.flush()
        return {"unit_a": unit_a, "unit_b": unit_b}

    @pytest.fixture
    def optometrist_user_a(self, db, lab_units):
        """Create optometrist for Hospital A"""
        from models import User, Role
        user = User(username="opt_a", email="opt_a@example.com")
        user.set_password("password")
        user.hospital_id = lab_units["unit_a"].hospital_id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        user.lab_units.append(lab_units["unit_a"])
        db.session.commit()
        return user

    @pytest.fixture
    def images_in_hospitals(self, db, lab_units):
        """Create images in both hospitals"""
        from models import PatientEncounters, EncounterSetImage

        enc_a = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient A",
            patient_id="A001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_a"].id,
            is_set_based=True
        )

        enc_b = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient B",
            patient_id="B001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_b"].id,
            is_set_based=True
        )

        db.session.add_all([enc_a, enc_b])
        db.session.flush()

        # Images in each encounter
        img_a = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=enc_a.id,
            spatial_position=1,
            original_filename="img_a.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )

        img_b = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=enc_b.id,
            spatial_position=1,
            original_filename="img_b.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )

        db.session.add_all([img_a, img_b])
        db.session.commit()
        return {"img_a": img_a, "img_b": img_b}

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_update_own_hospital_image_succeeds(self, test_client, optometrist_user_a, images_in_hospitals):
        """Test updating own hospital image succeeds"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Update own hospital image
            response = test_client.post(
                '/verify-encounter-set/update_position',
                json={
                    'image_uuid': str(images_in_hospitals["img_a"].uuid),
                    'position': '5'
                }
            )

            # Should succeed (200 or 422 for validation, but NOT 404)
            assert response.status_code in [200, 422], \
                f"User should update own hospital image (got {response.status_code})"

    def test_update_cross_hospital_image_blocked(self, test_client, optometrist_user_a, images_in_hospitals):
        """Test updating cross-hospital image is blocked"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Try to update Hospital B image
            response = test_client.post(
                '/verify-encounter-set/update_position',
                json={
                    'image_uuid': str(images_in_hospitals["img_b"].uuid),
                    'position': '5'
                }
            )

            # Should be blocked with 404
            assert response.status_code == 404, \
                "User should NOT update cross-hospital image"


class TestHospitalScopingEditImage:
    """Test hospital scoping on /verify-encounter-set/edit/<uuid> route"""

    @pytest.fixture
    def hospitals(self, db):
        """Create two separate hospitals"""
        from models import Hospital
        hospital1 = Hospital(name="Hospital A", code="HOSP_A")
        hospital2 = Hospital(name="Hospital B", code="HOSP_B")
        db.session.add_all([hospital1, hospital2])
        db.session.flush()
        return {"hospital1": hospital1, "hospital2": hospital2}

    @pytest.fixture
    def lab_units(self, db, hospitals):
        """Create lab units in each hospital"""
        from models import LabUnit
        unit_a = LabUnit(hospital_id=hospitals["hospital1"].id, name="Lab A1")
        unit_b = LabUnit(hospital_id=hospitals["hospital2"].id, name="Lab B1")
        db.session.add_all([unit_a, unit_b])
        db.session.flush()
        return {"unit_a": unit_a, "unit_b": unit_b}

    @pytest.fixture
    def optometrist_user_a(self, db, lab_units):
        """Create optometrist for Hospital A"""
        from models import User, Role
        user = User(username="opt_a", email="opt_a@example.com")
        user.set_password("password")
        user.hospital_id = lab_units["unit_a"].hospital_id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        user.lab_units.append(lab_units["unit_a"])
        db.session.commit()
        return user

    @pytest.fixture
    def images_in_hospitals(self, db, lab_units):
        """Create images in both hospitals"""
        from models import PatientEncounters, EncounterSetImage

        enc_a = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient A",
            patient_id="A001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_a"].id,
            is_set_based=True
        )

        enc_b = PatientEncounters(
            uuid=str(uuid4()),
            name="Patient B",
            patient_id="B001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_units["unit_b"].id,
            is_set_based=True
        )

        db.session.add_all([enc_a, enc_b])
        db.session.flush()

        img_a = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=enc_a.id,
            spatial_position=1,
            original_filename="img_a.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )

        img_b = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=enc_b.id,
            spatial_position=1,
            original_filename="img_b.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )

        db.session.add_all([img_a, img_b])
        db.session.commit()
        return {"img_a": img_a, "img_b": img_b}

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_edit_own_hospital_image_succeeds(self, test_client, optometrist_user_a, images_in_hospitals):
        """Test editing own hospital image succeeds"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Edit own hospital image
            response = test_client.get(f'/verify-encounter-set/edit/{images_in_hospitals["img_a"].uuid}')

            # Should succeed (200 OK)
            assert response.status_code == 200, "User should edit own hospital image"

    def test_edit_cross_hospital_image_blocked(self, test_client, optometrist_user_a, images_in_hospitals):
        """Test editing cross-hospital image is blocked"""
        with test_client:
            # Login as optometrist from Hospital A
            test_client.post('/login', data={
                'username': 'opt_a',
                'password': 'password'
            }, follow_redirects=True)

            # Try to edit Hospital B image
            response = test_client.get(f'/verify-encounter-set/edit/{images_in_hospitals["img_b"].uuid}')

            # Should be blocked with 404
            assert response.status_code == 404, "User should NOT edit cross-hospital image"
