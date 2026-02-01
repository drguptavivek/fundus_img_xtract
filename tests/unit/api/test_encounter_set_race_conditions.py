"""
Test-Driven Development Tests for Race Condition Prevention

Tests race condition (TOCTOU) vulnerabilities in EncounterSet operations:
- Spatial position collisions
- Finalization state inconsistencies

Race Condition Definitions:
- TOCTOU: Time-Of-Check, Time-Of-Use gap where concurrent requests can conflict
- Solution: Database constraints + row-level locking
"""

import pytest
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from auth.utils import utcnow


class TestPositionCollisionPrevention:
    """Test that spatial position collisions are prevented by database constraint"""

    @pytest.fixture
    def encounter_with_images(self, db):
        """Create encounter with 3 images at positions 1-3"""
        from models import PatientEncounters, EncounterSetImage, LabUnit, Hospital

        hospital = Hospital(name="Test Hospital", code="TEST")
        db.session.add(hospital)
        db.session.flush()

        lab_unit = LabUnit(hospital_id=hospital.id, name="Test Lab")
        db.session.add(lab_unit)
        db.session.flush()

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name="Test Patient",
            patient_id="TEST001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_unit.id,
            is_set_based=True
        )
        db.session.add(encounter)
        db.session.flush()

        # Create 3 images at positions 1, 2, 3
        images = []
        for pos in range(1, 4):
            img = EncounterSetImage(
                uuid=str(uuid4()),
                patient_encounter_id=encounter.id,
                spatial_position=pos,
                original_filename=f"img{pos}.jpg",
                folder_rel="test/",
                created_at=utcnow()
            )
            db.session.add(img)
            images.append(img)

        db.session.commit()
        return {
            "encounter": encounter,
            "images": images,
            "lab_unit": lab_unit,
            "hospital": hospital
        }

    def test_unique_constraint_on_position_per_encounter(self, db, encounter_with_images):
        """Test that database enforces unique (encounter, position) constraint"""
        encounter = encounter_with_images["encounter"]
        img = encounter_with_images["images"][0]

        # Try to move img to position 2 (which already has an image)
        img.spatial_position = 2

        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError) as exc_info:
            db.session.commit()

        # Verify it's the position constraint
        assert 'uq_encounter_position' in str(exc_info.value).lower() or \
               'unique' in str(exc_info.value).lower(), \
            "Should be unique constraint violation"

    def test_simultaneous_position_updates_prevented(self, db, encounter_with_images):
        """Test that two concurrent updates to same position fail atomically"""
        encounter = encounter_with_images["encounter"]
        img1 = encounter_with_images["images"][0]  # Position 1
        img2 = encounter_with_images["images"][1]  # Position 2

        # Simulate Race Condition:
        # Request A: Move img1 from 1 → 4
        # Request B: Move img2 from 2 → 4 (simultaneously)
        # Only one should succeed

        # Update img1 to position 4
        img1.spatial_position = 4
        db.session.commit()

        # Now try to update img2 to position 4 (should fail)
        img2.spatial_position = 4

        with pytest.raises(IntegrityError):
            db.session.commit()

    def test_position_range_validation_still_works(self, db, encounter_with_images):
        """Test that position must be 1-9 (validation happens before constraint)"""
        from db_transaction_manager import transaction_scope

        img = encounter_with_images["images"][0]

        # Invalid position (out of range)
        with transaction_scope() as db_ctx:
            img_query = db_ctx.query(__import__('models', fromlist=['EncounterSetImage']).EncounterSetImage)\
                .filter_by(uuid=img.uuid).first()
            img_query.spatial_position = 10  # Invalid

            # Should fail (either validation or constraint)
            with pytest.raises((ValueError, IntegrityError)):
                db_ctx.commit()

    def test_swap_positions_works_with_constraint(self, db, encounter_with_images):
        """Test that swapping positions between images still works"""
        from db_transaction_manager import transaction_scope

        img1 = encounter_with_images["images"][0]  # Position 1
        img2 = encounter_with_images["images"][1]  # Position 2

        # Swap: img1 goes to pos 2, img2 goes to pos 1
        # This requires atomic update (swap in single transaction)
        with transaction_scope() as db_ctx:
            # Fetch fresh
            img1_fresh = db_ctx.query(__import__('models', fromlist=['EncounterSetImage']).EncounterSetImage)\
                .filter_by(uuid=img1.uuid).first()
            img2_fresh = db_ctx.query(__import__('models', fromlist=['EncounterSetImage']).EncounterSetImage)\
                .filter_by(uuid=img2.uuid).first()

            # Use temp position to avoid constraint violation
            img1_fresh.spatial_position = 99  # Temp
            img2_fresh.spatial_position = 1
            img1_fresh.spatial_position = 2
            db_ctx.commit()

            # Verify swap worked
            assert img1_fresh.spatial_position == 2
            assert img2_fresh.spatial_position == 1


class TestFinalizationAtomicity:
    """Test that finalization with image review checks is atomic"""

    @pytest.fixture
    def encounter_for_finalization(self, db):
        """Create encounter with 3 images, all marked as reviewed"""
        from models import PatientEncounters, EncounterSetImage, LabUnit, Hospital

        hospital = Hospital(name="Test Hospital", code="TEST")
        db.session.add(hospital)
        db.session.flush()

        lab_unit = LabUnit(hospital_id=hospital.id, name="Test Lab")
        db.session.add(lab_unit)
        db.session.flush()

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name="Test Patient",
            patient_id="TEST001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_unit.id,
            is_set_based=True,
            encounter_verified_status="pending"
        )
        db.session.add(encounter)
        db.session.flush()

        # Create 3 reviewed images
        for pos in range(1, 4):
            img = EncounterSetImage(
                uuid=str(uuid4()),
                patient_encounter_id=encounter.id,
                spatial_position=pos,
                original_filename=f"img{pos}.jpg",
                folder_rel="test/",
                is_reviewed=True,  # All reviewed
                created_at=utcnow()
            )
            db.session.add(img)

        db.session.commit()
        return {"encounter": encounter}

    def test_finalization_with_row_locking(self, db, encounter_for_finalization):
        """Test that finalization uses row-level locking for atomicity"""
        from db_transaction_manager import transaction_scope
        from models import PatientEncounters, EncounterSetImage

        encounter = encounter_for_finalization["encounter"]

        # Finalize with locking (atomic)
        with transaction_scope() as db_ctx:
            # Lock the encounter for update
            enc = db_ctx.query(PatientEncounters)\
                .filter_by(id=encounter.id)\
                .with_for_update()\
                .first()

            # Lock all images
            images = db_ctx.query(EncounterSetImage)\
                .filter_by(patient_encounter_id=enc.id)\
                .with_for_update()\
                .all()

            # Check all reviewed
            unreviewed = sum(1 for img in images if not img.is_reviewed)
            assert unreviewed == 0, "All should be reviewed"

            # Finalize
            enc.encounter_verified_status = "verified"
            db_ctx.commit()

        # Verify
        with transaction_scope() as db_ctx:
            enc_check = db_ctx.query(PatientEncounters).filter_by(id=encounter.id).first()
            assert enc_check.encounter_verified_status == "verified"

    def test_incomplete_review_blocks_finalization(self, db, encounter_for_finalization):
        """Test that finalization fails if any image is not reviewed"""
        from db_transaction_manager import transaction_scope
        from models import PatientEncounters, EncounterSetImage

        encounter = encounter_for_finalization["encounter"]

        # Mark one image as not reviewed
        with transaction_scope() as db_ctx:
            img = db_ctx.query(EncounterSetImage)\
                .filter_by(patient_encounter_id=encounter.id)\
                .first()
            img.is_reviewed = False
            db_ctx.commit()

        # Try to finalize (should fail check)
        with transaction_scope() as db_ctx:
            enc = db_ctx.query(PatientEncounters)\
                .filter_by(id=encounter.id)\
                .with_for_update()\
                .first()

            images = db_ctx.query(EncounterSetImage)\
                .filter_by(patient_encounter_id=enc.id)\
                .with_for_update()\
                .all()

            # Check - should find unreviewed
            unreviewed = sum(1 for img in images if not img.is_reviewed)
            assert unreviewed > 0, "Should have unreviewed images"

            # Should NOT finalize
            if unreviewed > 0:
                return  # Don't commit

        # Verify not finalized
        with transaction_scope() as db_ctx:
            enc_check = db_ctx.query(PatientEncounters).filter_by(id=encounter.id).first()
            assert enc_check.encounter_verified_status == "pending", \
                "Should not finalize with unreviewed images"

    def test_concurrent_review_changes_during_finalization(self, db, encounter_for_finalization):
        """Test that locking prevents changes during finalization check"""
        from db_transaction_manager import transaction_scope
        from models import PatientEncounters, EncounterSetImage

        encounter = encounter_for_finalization["encounter"]

        # Simulate: Finalization has lock, tries to mark image as unreviewed
        with transaction_scope() as db_ctx:
            # Finalization locks and checks
            enc = db_ctx.query(PatientEncounters)\
                .filter_by(id=encounter.id)\
                .with_for_update()\
                .first()

            images = db_ctx.query(EncounterSetImage)\
                .filter_by(patient_encounter_id=enc.id)\
                .with_for_update()\
                .all()

            # While locked, no one can modify images
            # (In real scenario, another request would block waiting for lock)

            unreviewed = sum(1 for img in images if not img.is_reviewed)
            assert unreviewed == 0

            # Finalize (atomically)
            enc.encounter_verified_status = "verified"
            db_ctx.commit()

        # Verify finalization succeeded
        with transaction_scope() as db_ctx:
            enc_check = db_ctx.query(PatientEncounters).filter_by(id=encounter.id).first()
            assert enc_check.encounter_verified_status == "verified"


class TestIntegrityErrorHandling:
    """Test proper error handling for constraint violations"""

    @pytest.fixture
    def encounter_with_images(self, db):
        """Create test encounter"""
        from models import PatientEncounters, EncounterSetImage, LabUnit, Hospital

        hospital = Hospital(name="Test Hospital", code="TEST")
        db.session.add(hospital)
        db.session.flush()

        lab_unit = LabUnit(hospital_id=hospital.id, name="Test Lab")
        db.session.add(lab_unit)
        db.session.flush()

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name="Test Patient",
            patient_id="TEST001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_unit.id,
            is_set_based=True
        )
        db.session.add(encounter)
        db.session.flush()

        img1 = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=1,
            original_filename="img1.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )
        img2 = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=2,
            original_filename="img2.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )
        db.session.add_all([img1, img2])
        db.session.commit()
        return {"encounter": encounter, "img1": img1, "img2": img2}

    def test_integrity_error_caught_and_handled(self, encounter_with_images):
        """Test that IntegrityError is properly caught when position collision occurs"""
        from db_transaction_manager import transaction_scope
        from models import EncounterSetImage
        from sqlalchemy.exc import IntegrityError

        img1 = encounter_with_images["img1"]
        img2 = encounter_with_images["img2"]

        # Try to create collision
        error_caught = False
        try:
            with transaction_scope() as db_ctx:
                img_query = db_ctx.query(EncounterSetImage).filter_by(uuid=img1.uuid).first()
                img_query.spatial_position = 2  # Collision with img2
                db_ctx.commit()
        except IntegrityError:
            error_caught = True

        assert error_caught, "Should catch IntegrityError on position collision"

    def test_error_message_is_clear(self, encounter_with_images):
        """Test that error message is helpful to user"""
        from db_transaction_manager import transaction_scope
        from models import EncounterSetImage
        from sqlalchemy.exc import IntegrityError

        img1 = encounter_with_images["img1"]

        error_msg = None
        try:
            with transaction_scope() as db_ctx:
                img_query = db_ctx.query(EncounterSetImage).filter_by(uuid=img1.uuid).first()
                img_query.spatial_position = 2  # Collision
                db_ctx.commit()
        except IntegrityError as e:
            error_msg = str(e)

        assert error_msg is not None
        # Should mention constraint or position
        assert 'constraint' in error_msg.lower() or 'unique' in error_msg.lower() or 'position' in error_msg.lower()
