"""
Test cases for dualGradingUtils functions
"""

import unittest
from models import Session
from utils.dualGradingUtils import get_all_pending_resident_for_disease, get_all_pending_faculty_for_disease, get_all_pending_arbitration_for_disease


class TestDualGradingUtils(unittest.TestCase):
    
    def test_get_all_pending_resident_for_disease(self):
        """Test that get_all_pending_resident_for_disease returns a dictionary with total count"""
        # Test with a non-existent user/disease combination
        with Session() as db:
            result = get_all_pending_resident_for_disease(db, 999999, 999999)
            self.assertIsInstance(result, dict)
            self.assertIn('total', result)
            self.assertEqual(result['total'], 0)
    
    def test_get_all_pending_faculty_for_disease(self):
        """Test that get_all_pending_faculty_for_disease returns a dictionary with total count"""
        # Test with a non-existent user/disease combination
        with Session() as db:
            result = get_all_pending_faculty_for_disease(db, 999999, 999999)
            self.assertIsInstance(result, dict)
            self.assertIn('total', result)
            self.assertEqual(result['total'], 0)
    
    def test_get_all_pending_arbitration_for_disease(self):
        """Test that get_all_pending_arbitration_for_disease returns a dictionary with total count"""
        # Test with a non-existent user/disease combination
        with Session() as db:
            result = get_all_pending_arbitration_for_disease(db, 999999, 999999)
            self.assertIsInstance(result, dict)
            self.assertIn('total', result)
            self.assertEqual(result['total'], 0)


if __name__ == '__main__':
    unittest.main()