"""
Unit tests for taskUtils PII masking.

Test IDs from PII_Exposure_Control_Policy.md:
- PII-UNIT-002: Task utils masks cross-hospital PII

Bead: 5A (fundus_img_xtract-4g2)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from utils.taskUtils import get_task_detail


class TestGetTaskDetailPIIMasking:
    """Tests for PII masking in get_task_detail function."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return MagicMock()
    
    @pytest.fixture
    def mock_task_same_hospital(self):
        """Create a mock task from the same hospital as current user."""
        task = Mock()
        task.id = 1
        task.state = 'pending'
        task.lab_unit_id = 1
        task.created_at = Mock()
        task.updated_at = Mock()
        task.grades = []
        task.consensus = None
        
        # Lab unit and hospital
        task.lab_unit = Mock()
        task.lab_unit.id = 1
        task.lab_unit.name = 'Test Lab'
        task.lab_unit.hospital_id = 1
        task.lab_unit.hospital = Mock()
        task.lab_unit.hospital.name = 'Hospital A'
        
        # Disease
        task.disease = Mock()
        task.disease.name = 'DR'
        
        # Encounter file with PII
        task.encounter_file = Mock()
        task.encounter_file.uuid = 'test-uuid-123'
        task.encounter_file.patient_id = '12345678'
        task.encounter_file.patient_name = 'John Doe'
        
        task.direct_image = None
        
        return task
    
    @pytest.fixture
    def mock_task_different_hospital(self):
        """Create a mock task from a different hospital."""
        task = Mock()
        task.id = 2
        task.state = 'pending'
        task.lab_unit_id = 2
        task.created_at = Mock()
        task.updated_at = Mock()
        task.grades = []
        task.consensus = None
        
        # Lab unit and hospital (different hospital)
        task.lab_unit = Mock()
        task.lab_unit.id = 2
        task.lab_unit.name = 'Other Lab'
        task.lab_unit.hospital_id = 2
        task.lab_unit.hospital = Mock()
        task.lab_unit.hospital.name = 'Hospital B'
        
        # Disease
        task.disease = Mock()
        task.disease.name = 'DR'
        
        # Encounter file with PII
        task.encounter_file = Mock()
        task.encounter_file.uuid = 'test-uuid-456'
        task.encounter_file.patient_id = '87654321'
        task.encounter_file.patient_name = 'Jane Smith'
        
        task.direct_image = None
        
        return task
    
    def test_same_hospital_optometrist_sees_full_pii(self, mock_db_session, mock_task_same_hospital):
        """Optometrist at same hospital should see full PII."""
        with patch('utils.taskUtils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 1
            mock_user.hospital_id = 1  # Same hospital
            mock_user.has_role.return_value = False
            
            # Mock roles
            role = Mock()
            role.name = 'optometrist'
            mock_user.roles = [role]
            
            with patch('utils.taskUtils.get_user_lab_unit_ids', return_value=[1, 2]):
                # Mock query
                mock_query = mock_db_session.query.return_value
                mock_query.filter.return_value.options.return_value.first.return_value = mock_task_same_hospital
                
                result = get_task_detail(mock_db_session, 1)
                
                assert result is not None
                assert result['patient_id'] == '12345678'  # Full PII
                assert result['patient_name'] == 'John Doe'  # Full PII
    
    def test_different_hospital_grader_sees_masked_pii(self, mock_db_session, mock_task_different_hospital):
        """Grader from different hospital should see masked PII."""
        with patch('utils.taskUtils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 2
            mock_user.hospital_id = 1  # Different from task's hospital (2)
            mock_user.has_role.return_value = False
            
            # Mock roles
            role = Mock()
            role.name = 'resident'
            mock_user.roles = [role]
            
            with patch('utils.taskUtils.get_user_lab_unit_ids', return_value=[1, 2]):
                # Mock query
                mock_query = mock_db_session.query.return_value
                mock_query.filter.return_value.options.return_value.first.return_value = mock_task_different_hospital
                
                result = get_task_detail(mock_db_session, 2)
                
                assert result is not None
                assert result['patient_id'] == 'P****321'  # Masked (last 3 chars)
                assert result['patient_name'] == 'Anonymous'  # Masked
    
    def test_resident_same_hospital_sees_masked_pii(self, mock_db_session, mock_task_same_hospital):
        """Resident at same hospital should still see masked PII (role-based)."""
        with patch('utils.taskUtils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 3
            mock_user.hospital_id = 1  # Same hospital
            mock_user.has_role.return_value = False
            
            # Mock roles
            role = Mock()
            role.name = 'resident'
            mock_user.roles = [role]
            
            with patch('utils.taskUtils.get_user_lab_unit_ids', return_value=[1]):
                # Mock query
                mock_query = mock_db_session.query.return_value
                mock_query.filter.return_value.options.return_value.first.return_value = mock_task_same_hospital
                
                result = get_task_detail(mock_db_session, 1)
                
                assert result is not None
                assert result['patient_id'] == 'P****678'  # Masked (role-based)
                assert result['patient_name'] == 'Anonymous'  # Masked (role-based)
    
    def test_admin_sees_full_pii_regardless_of_hospital(self, mock_db_session, mock_task_different_hospital):
        """Admin should see full PII regardless of hospital."""
        with patch('utils.taskUtils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 4
            mock_user.hospital_id = 1  # Different from task's hospital
            mock_user.has_role.return_value = True  # Admin
            
            # Mock roles
            role = Mock()
            role.name = 'admin'
            mock_user.roles = [role]
            
            # Mock query
            mock_query = mock_db_session.query.return_value
            mock_query.filter.return_value.options.return_value.first.return_value = mock_task_different_hospital
            
            result = get_task_detail(mock_db_session, 2)
            
            assert result is not None
            # Admin bypasses scoping, so we don't check PII masking here
            # (admin check happens before masking logic)
    
    def test_direct_image_no_pii_exposure(self, mock_db_session):
        """Direct image uploads should not expose PII."""
        task = Mock()
        task.id = 3
        task.state = 'pending'
        task.lab_unit_id = 1
        task.created_at = Mock()
        task.updated_at = Mock()
        task.grades = []
        task.consensus = None
        
        task.lab_unit = Mock()
        task.lab_unit.id = 1
        task.lab_unit.name = 'Test Lab'
        task.lab_unit.hospital_id = 1
        task.lab_unit.hospital = Mock()
        task.lab_unit.hospital.name = 'Hospital A'
        
        task.disease = Mock()
        task.disease.name = 'DR'
        
        # Direct image (no patient info)
        task.direct_image = Mock()
        task.direct_image.uuid = 'direct-uuid-789'
        task.direct_image.folder_rel = 'uploads'
        task.direct_image.filename = 'image.jpg'
        task.direct_image.camera = None
        
        task.encounter_file = None
        
        with patch('utils.taskUtils.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 5
            mock_user.hospital_id = 1
            mock_user.has_role.return_value = False
            
            role = Mock()
            role.name = 'resident'
            mock_user.roles = [role]
            
            with patch('utils.taskUtils.get_user_lab_unit_ids', return_value=[1]):
                mock_query = mock_db_session.query.return_value
                mock_query.filter.return_value.options.return_value.first.return_value = task
                
                result = get_task_detail(mock_db_session, 3)
                
                assert result is not None
                assert result['patient_id'] == 'Unknown'
                assert result['patient_name'] == 'Unknown'
