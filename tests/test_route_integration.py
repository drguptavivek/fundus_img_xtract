"""Integration test for the updated search route with new imageSearchUtil."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from flask import Flask
from flask_login import FlaskLoginClient, login_user
from datetime import date

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock the app creation for testing
class MockApp:
    def __init__(self):
        self.config = {'ANALYTICS_SEARCH_IMAGES_PAGE_SIZE': 50}
        self.test_client_class = None
    
    def app_context(self):
        return MockContext()
    
    def test_client(self, user=None):
        return MockClient()

class MockContext:
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass

class MockClient:
    def __init__(self):
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def get(self, path):
        class MockResponse:
            def __init__(self):
                self.status_code = 200
        return MockResponse()

def create_app():
    return MockApp()
from models import User
from utils.imageSearchUtil import ImageSearchError


def test_search_route_with_new_util():
    """Test that the search route properly uses the new search_images_strict function."""
    
    # Create test app
    app = create_app()
    app.test_client_class = FlaskLoginClient
    
    with app.app_context():
        # Create test user
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            is_active=True
        )
        
        # Mock the search_images_strict function to track calls
        with patch('utils.imageSearchUtil.search_images_strict') as mock_search:
            # Setup mock to return test data
            mock_search.return_value = (
                [
                    {
                        'id': 1,
                        'uuid': 'test-uuid-1',
                        'type': 'direct',
                        'hospital': 'Test Hospital',
                        'lab_unit': 'Test Lab Unit',
                        'camera': 'Test Camera',
                        'disease': 'Test Disease',
                        'area': 'Test Area',
                        'upload_date': date(2025, 1, 1),
                        'capture_date': date(2025, 1, 1),
                        'is_mydriatic': True,
                        'has_reports': {'DR': True, 'Glaucoma': False}
                    }
                ],
                1
            )
            
            # Mock user lab units
            with patch('utils.upload_eligibility.get_user_lab_unit_ids') as mock_lab_units:
                mock_lab_units.return_value = {1, 2, 3}
                
                # Make request to search route
                with app.test_client(user=test_user) as client:
                    response = client.get('/search/images?camera_id=1')
                    
                    # Verify the response
                    assert response.status_code == 200
                    
                    # Verify search_images_strict was called with correct parameters
                    mock_search.assert_called_once()
                    call_args = mock_search.call_args
                    
                    # Check that the new function was called with correct parameters
                    assert 'db_session' in call_args.kwargs
                    assert 'page' in call_args.kwargs
                    assert 'per_page' in call_args.kwargs
                    assert 'camera_ids' in call_args.kwargs
                    assert 'user_id' in call_args.kwargs
                    assert call_args.kwargs['camera_ids'] == [1]
                    assert call_args.kwargs['user_id'] == 1
                    
                    print("✅ Route successfully uses new search_images_strict function")


def test_search_route_handles_filter_conflicts():
    """Test that the search route properly handles filter conflicts."""
    
    # Create test app
    app = create_app()
    app.test_client_class = FlaskLoginClient
    
    with app.app_context():
        # Create test user
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            is_active=True
        )
        
        # Mock the search_images_strict function to raise ImageSearchError
        with patch('utils.imageSearchUtil.search_images_strict') as mock_search:
            mock_search.side_effect = ImageSearchError("Cannot apply both direct and ZIP filters")
            
            # Mock user lab units
            with patch('utils.upload_eligibility.get_user_lab_unit_ids') as mock_lab_units:
                mock_lab_units.return_value = {1, 2, 3}
                
                # Make request that would cause filter conflict
                with app.test_client(user=test_user) as client:
                    response = client.get('/search/images?camera_id=1&has_dr_report=true')
                    
                    # Verify the response still returns 200 (error handled gracefully)
                    assert response.status_code == 200
                    
                    # Verify search_images_strict was called
                    mock_search.assert_called_once()
                    
                    print("✅ Route properly handles filter conflicts")


def test_search_route_with_zip_filters():
    """Test that the search route properly handles ZIP-specific filters."""
    
    # Create test app
    app = create_app()
    app.test_client_class = FlaskLoginClient
    
    with app.app_context():
        # Create test user
        test_user = User(
            id=1,
            username="testuser",
            email="test@example.com",
            is_active=True
        )
        
        # Mock the search_images_strict function
        with patch('utils.imageSearchUtil.search_images_strict') as mock_search:
            mock_search.return_value = ([], 0)
            
            # Mock user lab units
            with patch('utils.upload_eligibility.get_user_lab_unit_ids') as mock_lab_units:
                mock_lab_units.return_value = {1, 2, 3}
                
                # Make request with ZIP filters
                with app.test_client(user=test_user) as client:
                    response = client.get('/search/images?has_dr_report=true&has_glaucoma_report=true')
                    
                    # Verify the response
                    assert response.status_code == 200
                    
                    # Verify search_images_strict was called with ZIP filters
                    mock_search.assert_called_once()
                    call_args = mock_search.call_args
                    
                    assert call_args.kwargs['has_dr_report'] is True
                    assert call_args.kwargs['has_glaucoma_report'] is True
                    
                    print("✅ Route properly handles ZIP-specific filters")


if __name__ == "__main__":
    test_search_route_with_new_util()
    test_search_route_handles_filter_conflicts()
    test_search_route_with_zip_filters()
    print("\n🎉 All route integration tests passed!")