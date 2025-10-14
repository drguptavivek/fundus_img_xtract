"""Unit tests for the new imageSearchUtil functionality.

This test suite covers all the key features of the new image search system:
- Strict filter separation
- UUID-based returns
- User lab unit scoping
- Task disease information
- Error handling
- Performance optimization
"""

import pytest
from datetime import datetime, date as _date
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session
from typing import List, Dict, Any

# Import the functions to test
from utils.imageSearchUtil import (
    search_images_strict,
    search_images,
    validate_search_filters,
    validate_pagination,
    get_user_search_scope,
    build_direct_query,
    build_zip_query,
    get_tasks_for_multiple_images,
    format_direct_image_with_tasks,
    format_zip_image_with_tasks,
    ImageSearchError
)

# Import models for mocking
from models import (
    DirectImageUpload,
    EncounterFile,
    PatientEncounters,
    User,
    LabUnit,
    Hospital,
    Camera,
    Disease,
    GradingTask,
    Area,
    ZipFile,
    DiabeticRetinopathyReport,
    GlaucomaResultsCleaned
)


class TestValidateSearchFilters:
    """Test filter validation logic."""
    
    def test_no_filters_returns_both(self):
        """Test that no filters returns 'both' scope."""
        filters = {}
        result = validate_search_filters(filters)
        assert result == "both"
    
    def test_only_global_filters_returns_both(self):
        """Test that only global filters returns 'both' scope."""
        filters = {
            'hospital_id': 1,
            'lab_unit_ids': [1, 2],
            'upload_start': _date(2024, 1, 1),
            'upload_end': _date(2024, 12, 31)
        }
        result = validate_search_filters(filters)
        assert result == "both"
    
    def test_direct_filters_only_returns_direct(self):
        """Test that direct filters return 'direct_only' scope."""
        filters = {
            'camera_ids': [1, 2],
            'disease_ids': [1],
            'area_ids': [1],
            'is_mydriatic': True
        }
        result = validate_search_filters(filters)
        assert result == "direct_only"
    
    def test_zip_filters_only_returns_zip(self):
        """Test that ZIP filters return 'zip_only' scope."""
        filters = {
            'has_dr_report': True,
            'has_glaucoma_report': False,
            'capture_start': _date(2024, 1, 1),
            'capture_end': _date(2024, 12, 31)
        }
        result = validate_search_filters(filters)
        assert result == "zip_only"
    
    def test_conflicting_filters_raises_error(self):
        """Test that conflicting direct and ZIP filters raise an error."""
        filters = {
            'camera_ids': [1],  # Direct filter
            'has_dr_report': True  # ZIP filter
        }
        with pytest.raises(ImageSearchError, match="Cannot apply both direct image filters and ZIP filters"):
            validate_search_filters(filters)
    
    def test_invalid_upload_date_range_raises_error(self):
        """Test that invalid upload date range raises an error."""
        filters = {
            'upload_start': _date(2024, 12, 31),
            'upload_end': _date(2024, 1, 1)
        }
        with pytest.raises(ImageSearchError, match="upload_start date must be before upload_end date"):
            validate_search_filters(filters)
    
    def test_invalid_capture_date_range_raises_error(self):
        """Test that invalid capture date range raises an error."""
        filters = {
            'capture_start': _date(2024, 12, 31),
            'capture_end': _date(2024, 1, 1)
        }
        with pytest.raises(ImageSearchError, match="capture_start date must be before capture_end date"):
            validate_search_filters(filters)


class TestValidatePagination:
    """Test pagination validation."""
    
    def test_valid_pagination(self):
        """Test that valid pagination parameters pass through."""
        result = validate_pagination(1, 50)
        assert result == (1, 50)
    
    def test_page_less_than_one_raises_error(self):
        """Test that page < 1 raises an error."""
        with pytest.raises(ImageSearchError, match="Page must be >= 1"):
            validate_pagination(0, 50)
    
    def test_per_page_less_than_one_raises_error(self):
        """Test that per_page < 1 raises an error."""
        with pytest.raises(ImageSearchError, match="Per page must be >= 1"):
            validate_pagination(1, 0)
    
    def test_per_page_exceeds_limit_raises_error(self):
        """Test that per_page > 1000 raises an error."""
        with pytest.raises(ImageSearchError, match="Per page cannot exceed 1000"):
            validate_pagination(1, 1001)


class TestGetUserSearchScope:
    """Test user scoping functionality."""
    
    @patch('utils.imageSearchUtil.get_user_lab_unit_ids')
    def test_regular_user_scope(self, mock_get_lab_units):
        """Test scoping for regular user."""
        mock_get_lab_units.return_value = {1, 2, 3}
        
        mock_db = Mock()
        mock_user = Mock()
        mock_user.has_role.return_value = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        lab_unit_ids, is_admin = get_user_search_scope(123, mock_db)
        
        assert lab_unit_ids == {1, 2, 3}
        assert is_admin is False
        mock_get_lab_units.assert_called_once_with(123)
    
    @patch('utils.imageSearchUtil.get_user_lab_unit_ids')
    def test_admin_user_scope(self, mock_get_lab_units):
        """Test scoping for admin user."""
        mock_get_lab_units.return_value = {1, 2, 3}
        
        mock_db = Mock()
        mock_user = Mock()
        mock_user.has_role.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        lab_unit_ids, is_admin = get_user_search_scope(123, mock_db)
        
        assert lab_unit_ids == {1, 2, 3}
        assert is_admin is True
        mock_get_lab_units.assert_called_once_with(123)
    
    @patch('utils.imageSearchUtil.get_user_lab_unit_ids')
    def test_user_not_found(self, mock_get_lab_units):
        """Test scoping when user is not found."""
        mock_get_lab_units.return_value = {1, 2, 3}
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        lab_unit_ids, is_admin = get_user_search_scope(123, mock_db)
        
        assert lab_unit_ids == {1, 2, 3}
        assert is_admin is False


class TestGetTasksForMultipleImages:
    """Test task information retrieval for multiple images."""
    
    def test_empty_image_list_returns_empty_dict(self):
        """Test that empty image list returns empty dict."""
        mock_db = Mock()
        result = get_tasks_for_multiple_images(mock_db, [], 'direct')
        assert result == {}
    
    def test_direct_image_tasks_retrieved(self):
        """Test that direct image tasks are retrieved correctly."""
        mock_db = Mock()
        mock_task1 = Mock()
        mock_task1.direct_image_upload_id = 1
        mock_task2 = Mock()
        mock_task2.direct_image_upload_id = 2
        mock_disease1 = Mock()
        mock_disease1.name = "DR"
        mock_disease2 = Mock()
        mock_disease2.name = "Glaucoma"
        
        mock_query = Mock()
        mock_query.join.return_value.filter.return_value.filter.return_value.all.return_value = [
            (mock_task1, mock_disease1),
            (mock_task2, mock_disease2)
        ]
        mock_db.query.return_value = mock_query
        
        result = get_tasks_for_multiple_images(mock_db, [1, 2], 'direct')
        
        assert result == {1: ["DR"], 2: ["Glaucoma"]}
    
    def test_zip_image_tasks_retrieved(self):
        """Test that ZIP image tasks are retrieved correctly."""
        mock_db = Mock()
        mock_task1 = Mock()
        mock_task1.encounter_file_id = 1
        mock_task2 = Mock()
        mock_task2.encounter_file_id = 2
        mock_disease1 = Mock()
        mock_disease1.name = "AMD"
        mock_disease2 = Mock()
        mock_disease2.name = "DR"
        
        mock_query = Mock()
        mock_query.join.return_value.filter.return_value.filter.return_value.all.return_value = [
            (mock_task1, mock_disease1),
            (mock_task2, mock_disease2)
        ]
        mock_db.query.return_value = mock_query
        
        result = get_tasks_for_multiple_images(mock_db, [1, 2], 'zip')
        
        assert result == {1: ["AMD"], 2: ["DR"]}


class TestFormatDirectImageWithTasks:
    """Test formatting of direct images with task information."""
    
    def test_format_direct_image(self):
        """Test direct image formatting."""
        mock_image = Mock()
        mock_image.uuid = "test-uuid-123"
        mock_image.created_at = datetime(2024, 1, 15, 10, 30, 0)
        mock_image.hospital.name = "Test Hospital"
        mock_image.lab_unit.name = "Test Lab"
        mock_image.camera.name = "Test Camera"
        mock_image.disease.name = "DR"
        mock_image.area.name = "Macula"
        mock_image.is_mydriatic = True
        
        task_diseases = ["DR", "Glaucoma"]
        
        result = format_direct_image_with_tasks(mock_image, task_diseases)
        
        expected = {
            "uuid": "test-uuid-123",
            "type": "direct",
            "upload_date": "2024-01-15T10:30:00",
            "capture_date": "2024-01-15T10:30:00",
            "hospital": "Test Hospital",
            "lab_unit": "Test Lab",
            "camera": "Test Camera",
            "disease": "DR",
            "area": "Macula",
            "is_mydriatic": True,
            "tasks_for_diseases": ["DR", "Glaucoma"]
        }
        
        assert result == expected
    
    def test_format_direct_image_with_none_values(self):
        """Test direct image formatting with None values."""
        mock_image = Mock()
        mock_image.uuid = "test-uuid-123"
        mock_image.created_at = None
        mock_image.hospital = None
        mock_image.lab_unit = None
        mock_image.camera = None
        mock_image.disease = None
        mock_image.area = None
        mock_image.is_mydriatic = False
        
        task_diseases = []
        
        result = format_direct_image_with_tasks(mock_image, task_diseases)
        
        expected = {
            "uuid": "test-uuid-123",
            "type": "direct",
            "upload_date": None,
            "capture_date": None,
            "hospital": None,
            "lab_unit": None,
            "camera": None,
            "disease": None,
            "area": None,
            "is_mydriatic": False,
            "tasks_for_diseases": []
        }
        
        assert result == expected


class TestFormatZipImageWithTasks:
    """Test formatting of ZIP images with task information."""
    
    def test_format_zip_image(self):
        """Test ZIP image formatting."""
        mock_image = Mock()
        mock_image.uuid = "test-uuid-456"
        mock_image.lab_unit.hospital.name = "Test Hospital"
        mock_image.lab_unit.name = "Test Lab"
        
        mock_encounter = Mock()
        mock_zip_file = Mock()
        mock_zip_file.upload_date = _date(2024, 1, 14)
        mock_encounter.zip_file = mock_zip_file
        mock_encounter.capture_date_dt = _date(2024, 1, 13)
        mock_image.patient_encounter = mock_encounter
        
        task_diseases = ["AMD"]
        
        # Mock database queries for report status
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = True
        
        result = format_zip_image_with_tasks(mock_image, task_diseases, mock_db)
        
        expected = {
            "uuid": "test-uuid-456",
            "type": "zip",
            "upload_date": "2024-01-14",
            "capture_date": "2024-01-13",
            "hospital": "Test Hospital",
            "lab_unit": "Test Lab",
            "has_dr_report": True,
            "has_glaucoma_report": True,
            "tasks_for_diseases": ["AMD"]
        }
        
        assert result == expected


class TestSearchImagesStrict:
    """Test the main search function with various scenarios."""
    
    @patch('utils.imageSearchUtil.get_user_search_scope')
    @patch('utils.imageSearchUtil.validate_search_filters')
    @patch('utils.imageSearchUtil.log_search_request')
    @patch('utils.imageSearchUtil.log_search_results')
    def test_search_with_no_filters(
        self,
        mock_log_results,
        mock_log_request,
        mock_validate_filters,
        mock_get_scope
    ):
        """Test search with no filters returns both image types."""
        # Setup mocks
        mock_validate_filters.return_value = "both"
        mock_get_scope.return_value = ({1, 2}, False)
        
        # Mock database session
        mock_db = Mock()
        
        # Mock direct query
        mock_direct_query = Mock()
        mock_direct_query.count.return_value = 1
        mock_direct_img = Mock()
        mock_direct_img.id = 1
        mock_direct_img.created_at = datetime(2024, 1, 15, 10, 30, 0)
        mock_direct_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_direct_img]
        
        # Mock ZIP query
        mock_zip_query = Mock()
        mock_zip_query.count.return_value = 1
        mock_zip_img = Mock()
        mock_zip_img.id = 2
        mock_zip_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_zip_img]
        
        # Mock query builder functions
        with patch('utils.imageSearchUtil.build_direct_query', return_value=mock_direct_query), \
             patch('utils.imageSearchUtil.build_zip_query', return_value=mock_zip_query), \
             patch('utils.imageSearchUtil.get_tasks_for_multiple_images', return_value={}), \
             patch('utils.imageSearchUtil.format_direct_image_with_tasks', return_value={"uuid": "direct-uuid", "upload_date": datetime.now()}), \
             patch('utils.imageSearchUtil.format_zip_image_with_tasks', return_value={"uuid": "zip-uuid", "upload_date": datetime.now()}):
            
            results, total = search_images_strict(mock_db, page=1, per_page=50, user_id=123)
        
        # Assertions
        assert len(results) == 2
        assert total == 2
        mock_validate_filters.assert_called_once()
        mock_get_scope.assert_called_once_with(123, mock_db)
        mock_log_request.assert_called_once()
        mock_log_results.assert_called_once()
    
    @patch('utils.imageSearchUtil.get_user_search_scope')
    @patch('utils.imageSearchUtil.validate_search_filters')
    def test_search_with_direct_filters_only(
        self,
        mock_validate_filters,
        mock_get_scope
    ):
        """Test search with direct filters only returns direct images."""
        # Setup mocks
        mock_validate_filters.return_value = "direct_only"
        mock_get_scope.return_value = ({1, 2}, False)
        
        # Mock database session
        mock_db = Mock()
        
        # Mock direct query
        mock_direct_query = Mock()
        mock_direct_query.count.return_value = 1
        mock_direct_img = Mock()
        mock_direct_img.id = 1
        mock_direct_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_direct_img]
        
        # Mock query builder functions
        with patch('utils.imageSearchUtil.build_direct_query', return_value=mock_direct_query), \
             patch('utils.imageSearchUtil.get_tasks_for_multiple_images', return_value={}), \
             patch('utils.imageSearchUtil.format_direct_image_with_tasks', return_value={"uuid": "direct-uuid", "upload_date": datetime.now()}):
            
            results, total = search_images_strict(
                mock_db,
                page=1,
                per_page=50,
                camera_ids=[1],
                user_id=123
            )
        
        # Assertions
        assert len(results) == 1
        assert total == 1
        assert results[0]["uuid"] == "direct-uuid"
        mock_validate_filters.assert_called_once()
        mock_get_scope.assert_called_once_with(123, mock_db)
    
    @patch('utils.imageSearchUtil.get_user_search_scope')
    @patch('utils.imageSearchUtil.validate_search_filters')
    def test_search_with_zip_filters_only(
        self,
        mock_validate_filters,
        mock_get_scope
    ):
        """Test search with ZIP filters only returns ZIP images."""
        # Setup mocks
        mock_validate_filters.return_value = "zip_only"
        mock_get_scope.return_value = ({1, 2}, False)
        
        # Mock database session
        mock_db = Mock()
        
        # Mock ZIP query
        mock_zip_query = Mock()
        mock_zip_query.count.return_value = 1
        mock_zip_img = Mock()
        mock_zip_img.id = 2
        mock_zip_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_zip_img]
        
        # Mock query builder functions
        with patch('utils.imageSearchUtil.build_zip_query', return_value=mock_zip_query), \
             patch('utils.imageSearchUtil.get_tasks_for_multiple_images', return_value={}), \
             patch('utils.imageSearchUtil.format_zip_image_with_tasks', return_value={"uuid": "zip-uuid", "upload_date": datetime.now()}):
            
            results, total = search_images_strict(
                mock_db,
                page=1,
                per_page=50,
                has_dr_report=True,
                user_id=123
            )
        
        # Assertions
        assert len(results) == 1
        assert total == 1
        assert results[0]["uuid"] == "zip-uuid"
        mock_validate_filters.assert_called_once()
        mock_get_scope.assert_called_once_with(123, mock_db)
    
    def test_search_with_invalid_user_raises_error(self):
        """Test search with invalid user raises an error."""
        mock_db = Mock()
        
        with pytest.raises(ImageSearchError, match="User ID required for search"):
            search_images_strict(mock_db, user_id=None)
    
    @patch('utils.imageSearchUtil.get_user_search_scope')
    @patch('utils.imageSearchUtil.validate_search_filters')
    def test_search_with_conflicting_filters_raises_error(
        self,
        mock_validate_filters,
        mock_get_scope
    ):
        """Test search with conflicting filters raises an error."""
        # Setup mocks
        mock_validate_filters.side_effect = ImageSearchError("Conflicting filters")
        
        mock_db = Mock()
        
        with pytest.raises(ImageSearchError, match="Conflicting filters"):
            search_images_strict(
                mock_db,
                camera_ids=[1],  # Direct filter
                has_dr_report=True,  # ZIP filter
                user_id=123
            )
    
    def test_search_with_explicit_user_id(self):
        """Test search with explicit user ID parameter."""
        mock_db = Mock()
        
        with patch('utils.imageSearchUtil.validate_search_filters', return_value="both"), \
             patch('utils.imageSearchUtil.get_user_search_scope', return_value=({1, 2}, False)) as mock_get_scope, \
             patch('utils.imageSearchUtil.build_direct_query') as mock_direct, \
             patch('utils.imageSearchUtil.build_zip_query') as mock_zip:
            
            mock_direct.return_value.count.return_value = 0
            mock_zip.return_value.count.return_value = 0
            
            search_images_strict(mock_db, user_id=456)
        
        # Verify that get_user_search_scope was called with explicit user ID
        mock_get_scope.assert_called_once_with(456, mock_db)


class TestLegacySearchFunction:
    """Test the legacy search function for backward compatibility."""
    
    @patch('utils.imageSearchUtil.search_images_strict')
    def test_legacy_function_maps_parameters_correctly(self, mock_search_strict):
        """Test that legacy function maps parameters to new function correctly."""
        mock_search_strict.return_value = ([], 0)
        
        mock_db = Mock()
        
        search_images(
            mock_db,
            page=2,
            per_page=25,
            hospital_id=1,
            lab_unit_ids=[1, 2],
            upload_start=_date(2024, 1, 1),
            upload_end=_date(2024, 12, 31),
            camera_ids=[3],
            disease_ids=[4],
            area_ids=[5],
            is_mydriatic=True,
            has_dr_report=False,
            has_glaucoma_report=True,
            capture_start=_date(2024, 1, 1),
            capture_end=_date(2024, 12, 31),
            search_query="test"
        )
        
        # Verify that the new function was called with mapped parameters
        mock_search_strict.assert_called_once_with(
            db_session=mock_db,
            page=2,
            per_page=25,
            hospital_id=1,
            lab_unit_ids=[1, 2],
            upload_start=_date(2024, 1, 1),
            upload_end=_date(2024, 12, 31),
            camera_ids=[3],
            disease_ids=[4],
            area_ids=[5],
            is_mydriatic=True,
            has_dr_report=False,
            has_glaucoma_report=True,
            capture_start=_date(2024, 1, 1),
            capture_end=_date(2024, 12, 31),
            search_query="test"
        )


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])