import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, User, Disease, LabUnit, DirectImageUpload, GradingTask, Grade, Consensus, DiseaseGrading
from grading.dual_grading import is_user_eligible_for_slot
from grading.consensus import create_consensus_for_task, get_consensus_for_task


class TestDualGrading(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database for testing
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        
        # Create test data
        self.user = User(id=1, username='testuser', password_hash='testpass')
        self.disease = Disease(id=1, name='Glaucoma')
        self.lab_unit = LabUnit(id=1, name='Test Lab', hospital_id=1)
        self.direct_image = DirectImageUpload(
            id=1,
            uuid='test-uuid',
            filename='test.jpg',
            folder_rel='test',
            file_hash='test-hash',
            uploader_id=1,
            hospital_id=1,
            lab_unit_id=1,
            camera_id=1,
            disease_id=1,
            area_id=1
        )
        self.disease_grading = DiseaseGrading(
            id=1,
            disease_id=1,
            impression='Normal'
        )
        
        self.db.add(self.user)
        self.db.add(self.disease)
        self.db.add(self.lab_unit)
        self.db.add(self.direct_image)
        self.db.add(self.disease_grading)
        self.db.commit()
        
    def tearDown(self):
        self.db.close()
        
    def test_is_user_eligible_for_slot_no_eligibility(self):
        """Test that a user without eligibility cannot grade a task."""
        task = GradingTask(
            id=1,
            direct_image_upload_id=1,
            disease_id=1,
            lab_unit_id=1,
            state='pending'
        )
        
        # User should not be eligible without a UserDiseaseUnitRole entry
        self.assertFalse(is_user_eligible_for_slot(self.user, task, 'resident'))
        
    def test_create_consensus_for_task_match(self):
        """Test creating consensus when resident and faculty grades match."""
        # Create a task
        task = GradingTask(
            id=1,
            direct_image_upload_id=1,
            disease_id=1,
            lab_unit_id=1,
            state='faculty_done'
        )
        self.db.add(task)
        
        # Create matching grades
        resident_grade = Grade(
            id=1,
            task_id=1,
            grader_user_id=2,  # Different user
            role_slot='resident',
            disease_grading_id=1
        )
        faculty_grade = Grade(
            id=2,
            task_id=1,
            grader_user_id=3,  # Different user
            role_slot='faculty',
            disease_grading_id=1  # Same disease grading
        )
        self.db.add(resident_grade)
        self.db.add(faculty_grade)
        self.db.commit()
        
        # Check that grades were added
        grades = self.db.query(Grade).filter(Grade.task_id == 1).all()
        print(f"Grades in database: {grades}")
        
        # Create consensus
        consensus = create_consensus_for_task(1, self.db)
        
        # Check that consensus was created
        self.assertIsNotNone(consensus)
        self.assertEqual(consensus.task_id, 1)
        self.assertEqual(consensus.final_disease_grading_id, 1)
        self.assertEqual(consensus.method, 'match')
        
    def test_create_consensus_for_task_no_match(self):
        """Test that consensus is not created when resident and faculty grades don't match."""
        # Create a task
        task = GradingTask(
            id=1,
            direct_image_upload_id=1,
            disease_id=1,
            lab_unit_id=1,
            state='faculty_done'
        )
        self.db.add(task)
        
        # Create non-matching grades
        resident_grade = Grade(
            id=1,
            task_id=1,
            grader_user_id=2,
            role_slot='resident',
            disease_grading_id=1
        )
        faculty_grade = Grade(
            id=2,
            task_id=1,
            grader_user_id=3,
            role_slot='faculty',
            disease_grading_id=2  # Different disease grading
        )
        self.db.add(resident_grade)
        self.db.add(faculty_grade)
        self.db.commit()
        
        # Try to create consensus
        consensus = create_consensus_for_task(1, self.db)
        
        # Check that consensus was not created
        self.assertIsNone(consensus)
        
    def test_get_consensus_for_task(self):
        """Test getting consensus for a task."""
        # Create a task
        task = GradingTask(
            id=1,
            direct_image_upload_id=1,
            disease_id=1,
            lab_unit_id=1,
            state='final'
        )
        self.db.add(task)
        
        # Create consensus
        consensus = Consensus(
            id=1,
            task_id=1,
            final_disease_grading_id=1,
            method='match'
        )
        self.db.add(consensus)
        self.db.commit()
        
        # Get consensus
        retrieved_consensus = get_consensus_for_task(1, self.db)
        
        # Check that consensus was retrieved
        self.assertIsNotNone(retrieved_consensus)
        self.assertEqual(retrieved_consensus.id, 1)
        self.assertEqual(retrieved_consensus.task_id, 1)
        self.assertEqual(retrieved_consensus.final_disease_grading_id, 1)
        self.assertEqual(retrieved_consensus.method, 'match')


if __name__ == '__main__':
    unittest.main()