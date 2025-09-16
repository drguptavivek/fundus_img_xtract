"""
Test cases for masterUtils functions
"""

import unittest
from utils.masterUtils import get_all_diseases, get_disease_gradings, get_all_hospitals, get_all_lab_units, get_hosp_lab_units, get_all_areas, get_all_cameras


class TestMasterUtils(unittest.TestCase):
    
    def test_get_all_diseases(self):
        """Test that get_all_diseases returns a list of dictionaries with id and name"""
        diseases = get_all_diseases()
        self.assertIsInstance(diseases, list)
        if diseases:  # If there are diseases in the database
            disease = diseases[0]
            self.assertIn('id', disease)
            self.assertIn('name', disease)
    
    def test_get_disease_gradings(self):
        """Test that get_disease_gradings returns gradings for a disease"""
        diseases = get_all_diseases()
        if diseases:  # If there are diseases in the database
            disease_id = diseases[0]['id']
            gradings = get_disease_gradings(disease_id)
            self.assertIsInstance(gradings, list)
            if gradings:  # If there are gradings for this disease
                grading = gradings[0]
                self.assertIn('id', grading)
                self.assertIn('impression', grading)
                self.assertIn('disease_id', grading)
    
    def test_get_all_hospitals(self):
        """Test that get_all_hospitals returns a list of dictionaries with id and name"""
        hospitals = get_all_hospitals()
        self.assertIsInstance(hospitals, list)
        if hospitals:  # If there are hospitals in the database
            hospital = hospitals[0]
            self.assertIn('id', hospital)
            self.assertIn('name', hospital)
    
    def test_get_all_lab_units(self):
        """Test that get_all_lab_units returns a list of dictionaries with id, name, and hospital info"""
        lab_units = get_all_lab_units()
        self.assertIsInstance(lab_units, list)
        if lab_units:  # If there are lab units in the database
            lab_unit = lab_units[0]
            self.assertIn('id', lab_unit)
            self.assertIn('name', lab_unit)
            self.assertIn('hospital_id', lab_unit)
            self.assertIn('hospital_name', lab_unit)
    
    def test_get_hosp_lab_units(self):
        """Test that get_hosp_lab_units returns lab units for a hospital"""
        hospitals = get_all_hospitals()
        if hospitals:  # If there are hospitals in the database
            hospital_id = hospitals[0]['id']
            lab_units = get_hosp_lab_units(hospital_id)
            self.assertIsInstance(lab_units, list)
            if lab_units:  # If there are lab units for this hospital
                lab_unit = lab_units[0]
                self.assertIn('id', lab_unit)
                self.assertIn('name', lab_unit)
                self.assertIn('hospital_id', lab_unit)
                self.assertEqual(lab_unit['hospital_id'], hospital_id)
    
    def test_get_all_areas(self):
        """Test that get_all_areas returns a list of dictionaries with id and name"""
        areas = get_all_areas()
        self.assertIsInstance(areas, list)
        if areas:  # If there are areas in the database
            area = areas[0]
            self.assertIn('id', area)
            self.assertIn('name', area)
    
    def test_get_all_cameras(self):
        """Test that get_all_cameras returns a list of dictionaries with id and name"""
        cameras = get_all_cameras()
        self.assertIsInstance(cameras, list)
        if cameras:  # If there are cameras in the database
            camera = cameras[0]
            self.assertIn('id', camera)
            self.assertIn('name', camera)


if __name__ == '__main__':
    unittest.main()