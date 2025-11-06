"""
Test cases for analytics routes to verify functionality after 
database session management changes.
"""

import pytest


def test_encounter_results_route():
    """Test the encounter results route."""
    # Just verify that the route exists and can be imported properly
    # Full integration tests would require a running app with test data
    from analytics.route_encounter_results import encounter_results
    assert encounter_results is not None
    

def test_view_encounter_route():
    """Test the view encounter route."""
    from analytics.route_encounter_view import view_encounter
    assert view_encounter is not None


def test_encounter_files_route():
    """Test the encounter files route."""
    from analytics.route_encounterFiles_kpi_display import encounter_files
    assert encounter_files is not None


def test_image_results_route():
    """Test the image results route."""
    from analytics.route_image_results import image_results
    assert image_results is not None


def test_images_without_tasks_route():
    """Test the images without tasks route."""
    from analytics.route_images_without_tasks import images_without_tasks
    assert images_without_tasks is not None


def test_encounter_results_simple_route():
    """Test the encounter results simple route."""
    from analytics.route_routes_simple import encounter_results_simple
    assert encounter_results_simple is not None


def test_view_task_details_route():
    """Test the view task details route."""
    from analytics.route_task_details import view_task_details
    assert view_task_details is not None


def test_view_upload_route():
    """Test the view upload route."""
    from analytics.route_direct_view import view_upload
    assert view_upload is not None


def test_direct_files_route():
    """Test the direct files route."""
    from analytics.route_directFiles_kpi_display import direct_files
    assert direct_files is not None


if __name__ == "__main__":
    pytest.main([__file__])