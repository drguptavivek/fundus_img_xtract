"""
Test for userGradingsDone utility functions.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import Mock, MagicMock, patch
from utils.userGradingsDone import get_user_gradings, get_user_gradings_with_details


class TestUserGradingsDone(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.user_id = 1
        self.page = 1
        self.per_page = 20
        
    @patch('utils.userGradingsDone.Session')
    def test_get_user_gradings_returns_tuple(self, mock_session_class):
        """Test that get_user_gradings returns a tuple with list and int."""
        # Mock the session and query result
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        mock_grade = Mock()
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 5
        mock_query.offset.return_value.limit.return_value.all.return_value = [mock_grade] * 3
        
        result, total = get_user_gradings(self.user_id, self.page, self.per_page)
        
        # Assert the result is a tuple with list and int
        self.assertIsInstance(result, list)
        self.assertIsInstance(total, int)
        self.assertEqual(total, 5)
        self.assertEqual(len(result), 3)
        
        # Assert session was properly closed
        mock_session.close.assert_called_once()
        
    @patch('utils.userGradingsDone.Session')
    def test_get_user_gradings_with_details_returns_tuple(self, mock_session_class):
        """Test that get_user_gradings_with_details returns a tuple with list and int."""
        # Mock the session and query result
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Create a mock result object that simulates the joined query result
        mock_result = Mock()
        mock_result.Grade.id = 1
        mock_result.disease_name = "Diabetic Retinopathy"
        mock_result.grade_impression = "Mild"
        mock_result.lab_unit_name = "Retina Lab"
        mock_result.hospital_name = "AIIMS"
        
        # Mock the query chain
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.offset.return_value.limit.return_value.all.return_value = [mock_result]
        
        result, total = get_user_gradings_with_details(self.user_id, self.page, self.per_page)
        
        # Assert the result is a tuple with list and int
        self.assertIsInstance(result, list)
        self.assertIsInstance(total, int)
        self.assertEqual(total, 2)
        self.assertEqual(len(result), 1)
        self.assertIn('disease_name', result[0])
        self.assertIn('grade_impression', result[0])
        self.assertIn('lab_unit_name', result[0])
        self.assertIn('hospital_name', result[0])
        
        # Assert session was properly closed
        mock_session.close.assert_called_once()
        
    @patch('utils.userGradingsDone.Session')
    def test_get_user_gradings_for_user_id_1(self, mock_session_class):
        """Test that get_user_gradings successfully returns gradings for user ID 1."""
        # Mock the session and query result
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Create mock Grade objects
        mock_grade1 = Mock()
        mock_grade1.id = 1
        mock_grade1.grader_user_id = 1
        mock_grade1.role_slot = "resident"
        mock_grade1.disease_grading_id = 1
        mock_grade1.comment = "Good quality image"
        mock_grade1.task_id = 101
        
        mock_grade2 = Mock()
        mock_grade2.id = 2
        mock_grade2.grader_user_id = 1
        mock_grade2.role_slot = "faculty"
        mock_grade2.disease_grading_id = 2
        mock_grade2.comment = "Needs review"
        mock_grade2.task_id = 102
        
        # Mock the query chain
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.offset.return_value.limit.return_value.all.return_value = [mock_grade1, mock_grade2]
        
        # Call the function with user_id = 1
        result, total = get_user_gradings(user_id=1, page=1, per_page=20)
        
        # Assert the result is correct
        self.assertIsInstance(result, list)
        self.assertIsInstance(total, int)
        self.assertEqual(total, 2)
        self.assertEqual(len(result), 2)
        
        # Check that the first grading has the correct properties
        self.assertEqual(result[0].id, 1)
        self.assertEqual(result[0].grader_user_id, 1)
        self.assertEqual(result[0].role_slot, "resident")
        
        # Check that the second grading has the correct properties
        self.assertEqual(result[1].id, 2)
        self.assertEqual(result[1].grader_user_id, 1)
        self.assertEqual(result[1].role_slot, "faculty")
        
        # Assert session was properly closed
        mock_session.close.assert_called_once()
        
    @patch('utils.userGradingsDone.Session')
    def test_get_user_gradings_with_details_for_user_id_1(self, mock_session_class):
        """Test that get_user_gradings_with_details successfully returns gradings for user ID 1."""
        # Mock the session and query result
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Create a mock result object that simulates the joined query result
        mock_result1 = Mock()
        mock_result1.Grade.id = 1
        mock_result1.Grade.grader_user_id = 1
        mock_result1.Grade.role_slot = "resident"
        mock_result1.Grade.disease_grading_id = 1
        mock_result1.Grade.comment = "Good quality image"
        mock_result1.Grade.task_id = 101
        mock_result1.disease_name = "Diabetic Retinopathy"
        mock_result1.grade_impression = "Mild"
        mock_result1.lab_unit_name = "Retina Lab"
        mock_result1.hospital_name = "AIIMS"
        
        mock_result2 = Mock()
        mock_result2.Grade.id = 2
        mock_result2.Grade.grader_user_id = 1
        mock_result2.Grade.role_slot = "faculty"
        mock_result2.Grade.disease_grading_id = 2
        mock_result2.Grade.comment = "Needs review"
        mock_result2.Grade.task_id = 102
        mock_result2.disease_name = "Glaucoma"
        mock_result2.grade_impression = "Suspect"
        mock_result2.lab_unit_name = "Glaucoma Lab"
        mock_result2.hospital_name = "AIIMS"
        
        # Mock the query chain
        mock_query = Mock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.offset.return_value.limit.return_value.all.return_value = [mock_result1, mock_result2]
        
        # Call the function with user_id = 1
        result, total = get_user_gradings_with_details(user_id=1, page=1, per_page=20)
        
        # Assert the result is correct
        self.assertIsInstance(result, list)
        self.assertIsInstance(total, int)
        self.assertEqual(total, 2)
        self.assertEqual(len(result), 2)
        
        # Check that the first grading has the correct properties
        self.assertEqual(result[0]['id'], 1)
        self.assertEqual(result[0]['grader_user_id'], 1)
        self.assertEqual(result[0]['role_slot'], "resident")
        self.assertEqual(result[0]['disease_name'], "Diabetic Retinopathy")
        self.assertEqual(result[0]['grade_impression'], "Mild")
        self.assertEqual(result[0]['lab_unit_name'], "Retina Lab")
        self.assertEqual(result[0]['hospital_name'], "AIIMS")
        
        # Check that the second grading has the correct properties
        self.assertEqual(result[1]['id'], 2)
        self.assertEqual(result[1]['grader_user_id'], 1)
        self.assertEqual(result[1]['role_slot'], "faculty")
        self.assertEqual(result[1]['disease_name'], "Glaucoma")
        self.assertEqual(result[1]['grade_impression'], "Suspect")
        self.assertEqual(result[1]['lab_unit_name'], "Glaucoma Lab")
        self.assertEqual(result[1]['hospital_name'], "AIIMS")
        
        # Assert session was properly closed
        mock_session.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()