"""Test runner for image search functionality with real database integration.

This script tests the new imageSearchUtil functionality using the actual database
with the provided admin credentials (username: admin, password: Vivek@2026).
"""

import pytest
from datetime import datetime, date as _date
from models import Session, User, DirectImageUpload, EncounterFile, GradingTask, Disease
from utils.imageSearchUtil import search_images_strict, ImageSearchError


def test_basic_search(admin_user, db_session):
    """Test basic search functionality."""
    # Test 1: Search with no filters (should return both image types)
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)
    
    # Test 2: Search with global filters only
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        upload_start=_date(2025, 1, 1),
        upload_end=_date(2025, 12, 31),
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)


def test_direct_filter_search(admin_user, db_session):
    """Test search with direct image filters."""
    # Test 1: Search with camera filter (should only return direct images)
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        camera_ids=[1],  # Assuming camera ID 1 exists
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)
    
    # Verify all results are direct images if any results exist
    if results:
        all_direct = all(result['type'] == 'direct' for result in results)
        assert all_direct
    
    # Test 2: Search with disease filter
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        disease_ids=[1],  # Assuming disease ID 1 exists
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)


def test_zip_filter_search(admin_user, db_session):
    """Test search with ZIP image filters."""
    # Test 1: Search with DR report filter (should only return ZIP images)
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        has_dr_report=True,
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)
    
    # Verify all results are ZIP images if any results exist
    if results:
        all_zip = all(result['type'] == 'zip' for result in results)
        assert all_zip
    
    # Test 2: Search with capture date filter
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        capture_start=_date(2025, 1, 1),
        capture_end=_date(2025, 12, 31),
        user_id=admin_user.id
    )
    assert isinstance(results, list)
    assert isinstance(total, int)


def test_filter_conflict(admin_user, db_session):
    """Test that conflicting filters raise an error."""
    # Test: Apply both direct and ZIP filters (should raise error)
    with pytest.raises(ImageSearchError):
        search_images_strict(
            db_session=db_session,
            page=1,
            per_page=10,
            camera_ids=[1],  # Direct filter
            has_dr_report=True,  # ZIP filter
            user_id=admin_user.id
        )


def test_task_information(admin_user, db_session):
    """Test that task information is correctly included."""
    # Test search and check task information
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        user_id=admin_user.id
    )
    
    assert isinstance(results, list)
    assert isinstance(total, int)
    
    # Check that results have the expected structure
    if results:
        for result in results[:3]:  # Check first 3 results
            assert 'uuid' in result
            assert 'type' in result
            assert 'tasks_for_diseases' in result
            assert isinstance(result['tasks_for_diseases'], list)


def test_uuid_based_returns(admin_user, db_session):
    """Test that no original filenames are returned."""
    results, total = search_images_strict(
        db_session=db_session,
        page=1,
        per_page=10,
        user_id=admin_user.id
    )
    
    # Check that no result contains filename information
    filename_fields = ['filename', 'original_filename', 'file_name', 'name']
    has_filenames = False
    
    for result in results:
        for field in filename_fields:
            if field in result:
                has_filenames = True
                break
    
    assert not has_filenames, "Results should not contain filename fields"
    
    # Verify UUID is present in all results
    if results:
        all_have_uuid = all('uuid' in result for result in results)
        assert all_have_uuid, "All results should have UUID field"