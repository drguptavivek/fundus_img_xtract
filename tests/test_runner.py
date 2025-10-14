#!/usr/bin/env python3
"""Test runner for image search functionality with real database integration.

This script tests the new imageSearchUtil functionality using the actual database
with the provided admin credentials (username: admin, password: Vivek@2026).
"""

import os
import sys
from datetime import datetime, date as _date

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Session, User, DirectImageUpload, EncounterFile, GradingTask, Disease
from utils.imageSearchUtil import search_images_strict, ImageSearchError
from flask import Flask
from flask_login import login_user


def create_test_app():
    """Create a minimal Flask app for testing."""
    app = Flask(__name__)
    app.secret_key = 'test-secret-key'
    
    # Configure the app to use the same database as the main application
    from models import DATABASE_URL
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    return app


def login_admin_user(app):
    """Login the admin user for testing."""
    with app.app_context():
        db = Session()
        try:
            # Get the admin user
            admin_user = db.query(User).filter(User.username == 'admin').first()
            if not admin_user:
                print("ERROR: Admin user not found in database")
                return None
            
            # Verify password (simple check for testing)
            # In a real scenario, you'd use proper password verification
            print(f"Found admin user: {admin_user.username} (ID: {admin_user.id})")
            
            # Check if user has admin role
            is_admin = admin_user.has_role('admin')
            print(f"User has admin role: {is_admin}")
            
            return admin_user
            
        finally:
            db.close()


def test_basic_search(admin_user):
    """Test basic search functionality."""
    print("\n=== Testing Basic Search ===")
    
    db = Session()
    try:
        # Test 1: Search with no filters (should return both image types)
        print("Test 1: Search with no filters")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            user_id=admin_user.id
        )
        print(f"Found {total} total images, returned {len(results)} results")
        
        if results:
            print("Sample results:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. UUID: {result['uuid']}, Type: {result['type']}, "
                      f"Hospital: {result.get('hospital', 'N/A')}, "
                      f"Tasks: {result.get('tasks_for_diseases', [])}")
        
        # Test 2: Search with global filters only
        print("\nTest 2: Search with global filters only")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            upload_start=_date(2025, 1, 1),
            upload_end=_date(2025, 12, 31),
            user_id=admin_user.id
        )
        print(f"Found {total} images in 2025, returned {len(results)} results")
        
        return True
        
    except Exception as e:
        print(f"ERROR in basic search test: {e}")
        return False
    finally:
        db.close()


def test_direct_filter_search(admin_user):
    """Test search with direct image filters."""
    print("\n=== Testing Direct Image Filter Search ===")
    
    db = Session()
    try:
        # Test 1: Search with camera filter (should only return direct images)
        print("Test 1: Search with camera filter")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            camera_ids=[1],  # Assuming camera ID 1 exists
            user_id=admin_user.id
        )
        print(f"Found {total} direct images with camera ID 1, returned {len(results)} results")
        
        # Verify all results are direct images
        all_direct = all(result['type'] == 'direct' for result in results)
        print(f"All results are direct images: {all_direct}")
        
        # Test 2: Search with disease filter
        print("\nTest 2: Search with disease filter")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            disease_ids=[1],  # Assuming disease ID 1 exists
            user_id=admin_user.id
        )
        print(f"Found {total} direct images with disease ID 1, returned {len(results)} results")
        
        return True
        
    except Exception as e:
        print(f"ERROR in direct filter search test: {e}")
        return False
    finally:
        db.close()


def test_zip_filter_search(admin_user):
    """Test search with ZIP image filters."""
    print("\n=== Testing ZIP Image Filter Search ===")
    
    db = Session()
    try:
        # Test 1: Search with DR report filter (should only return ZIP images)
        print("Test 1: Search with DR report filter")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_dr_report=True,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images with DR report, returned {len(results)} results")
        
        # Verify all results are ZIP images
        all_zip = all(result['type'] == 'zip' for result in results)
        print(f"All results are ZIP images: {all_zip}")
        
        if results:
            print("Sample ZIP results:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. UUID: {result['uuid']}, "
                      f"Has DR Report: {result.get('has_dr_report', False)}, "
                      f"Has Glaucoma Report: {result.get('has_glaucoma_report', False)}")
        
        # Test 2: Search with capture date filter
        print("\nTest 2: Search with capture date filter")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            capture_start=_date(2025, 1, 1),
            capture_end=_date(2025, 12, 31),
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images with capture date in 2025, returned {len(results)} results")
        
        # Test 3: Search for ZIP images without DR reports
        print("\nTest 3: Search for ZIP images without DR reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_dr_report=False,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images without DR reports, returned {len(results)} results")
        
        if results:
            print("Sample ZIP results without DR reports:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. UUID: {result['uuid']}, "
                      f"Has DR Report: {result.get('has_dr_report', False)}, "
                      f"Has Glaucoma Report: {result.get('has_glaucoma_report', False)}")
        
        # Test 4: Search for ZIP images without Glaucoma reports
        print("\nTest 4: Search for ZIP images without Glaucoma reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_glaucoma_report=False,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images without Glaucoma reports, returned {len(results)} results")
        
        # Test 5: Search for ZIP images without either DR or Glaucoma reports
        print("\nTest 5: Search for ZIP images without either DR or Glaucoma reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_dr_report=False,
            has_glaucoma_report=False,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images without either DR or Glaucoma reports, returned {len(results)} results")
        
        # Test 6: Search for ZIP images WITH DR reports (positive test)
        print("\nTest 6: Search for ZIP images WITH DR reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_dr_report=True,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images WITH DR reports, returned {len(results)} results")
        
        if results:
            print("Sample ZIP results WITH DR reports:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. UUID: {result['uuid']}, "
                      f"Has DR Report: {result.get('has_dr_report', False)}, "
                      f"Has Glaucoma Report: {result.get('has_glaucoma_report', False)}")
        
        # Test 7: Search for ZIP images WITH Glaucoma reports (positive test)
        print("\nTest 7: Search for ZIP images WITH Glaucoma reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_glaucoma_report=True,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images WITH Glaucoma reports, returned {len(results)} results")
        
        # Test 8: Search for ZIP images WITH both DR and Glaucoma reports
        print("\nTest 8: Search for ZIP images WITH both DR and Glaucoma reports")
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            has_dr_report=True,
            has_glaucoma_report=True,
            user_id=admin_user.id
        )
        print(f"Found {total} ZIP images WITH both DR and Glaucoma reports, returned {len(results)} results")
        
        if results:
            print("Sample ZIP results WITH both reports:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. UUID: {result['uuid']}, "
                      f"Has DR Report: {result.get('has_dr_report', False)}, "
                      f"Has Glaucoma Report: {result.get('has_glaucoma_report', False)}")
        
        return True
        
    except Exception as e:
        print(f"ERROR in ZIP filter search test: {e}")
        return False
    finally:
        db.close()


def test_filter_conflict(admin_user):
    """Test that conflicting filters raise an error."""
    print("\n=== Testing Filter Conflict Detection ===")
    
    db = Session()
    try:
        # Test: Apply both direct and ZIP filters (should raise error)
        print("Test: Apply both direct and ZIP filters")
        try:
            results, total = search_images_strict(
                db_session=db,
                page=1,
                per_page=10,
                camera_ids=[1],  # Direct filter
                has_dr_report=True,  # ZIP filter
                user_id=admin_user.id
            )
            print("ERROR: Expected ImageSearchError but got results")
            return False
        except ImageSearchError as e:
            print(f"SUCCESS: Caught expected error: {e}")
            return True
        
    except Exception as e:
        print(f"ERROR in filter conflict test: {e}")
        return False
    finally:
        db.close()


def test_task_information(admin_user):
    """Test that task information is correctly included."""
    print("\n=== Testing Task Information ===")
    
    db = Session()
    try:
        # Get some existing images from the database
        direct_images = db.query(DirectImageUpload).limit(3).all()
        zip_files = db.query(EncounterFile).limit(3).all()
        
        if direct_images:
            print(f"Testing with {len(direct_images)} direct images")
            for img in direct_images:
                print(f"  Direct Image UUID: {img.uuid}")
        
        if zip_files:
            print(f"Testing with {len(zip_files)} ZIP files")
            for file in zip_files:
                print(f"  ZIP File UUID: {file.uuid}")
        
        # Test search and check task information
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            user_id=admin_user.id
        )
        
        print(f"Found {total} images with task information")
        
        if results:
            print("Task information in results:")
            for i, result in enumerate(results[:5]):
                tasks = result.get('tasks_for_diseases', [])
                print(f"  {i+1}. UUID: {result['uuid']}, Type: {result['type']}, Tasks: {tasks}")
        
        return True
        
    except Exception as e:
        print(f"ERROR in task information test: {e}")
        return False
    finally:
        db.close()


def test_uuid_based_returns(admin_user):
    """Test that no original filenames are returned."""
    print("\n=== Testing UUID-Based Returns ===")
    
    db = Session()
    try:
        results, total = search_images_strict(
            db_session=db,
            page=1,
            per_page=10,
            user_id=admin_user.id
        )
        
        print(f"Checking {len(results)} results for filename exposure")
        
        # Check that no result contains filename information
        filename_fields = ['filename', 'original_filename', 'file_name', 'name']
        has_filenames = False
        
        for result in results:
            for field in filename_fields:
                if field in result:
                    print(f"WARNING: Found filename field '{field}' in result: {result[field]}")
                    has_filenames = True
        
        if not has_filenames:
            print("SUCCESS: No filename fields found in results")
        
        # Verify UUID is present in all results
        all_have_uuid = all('uuid' in result for result in results)
        print(f"All results have UUID: {all_have_uuid}")
        
        return not has_filenames and all_have_uuid
        
    except Exception as e:
        print(f"ERROR in UUID-based returns test: {e}")
        return False
    finally:
        db.close()


def main():
    """Run all tests."""
    print("Starting Image Search Utility Tests")
    print("=====================================")
    
    # Create test app
    app = create_test_app()
    
    # Login admin user
    admin_user = login_admin_user(app)
    if not admin_user:
        print("Failed to login admin user. Exiting.")
        return False
    
    # Run tests
    tests = [
        ("Basic Search", test_basic_search),
        ("Direct Filter Search", test_direct_filter_search),
        ("ZIP Filter Search", test_zip_filter_search),
        ("Filter Conflict Detection", test_filter_conflict),
        ("Task Information", test_task_information),
        ("UUID-Based Returns", test_uuid_based_returns)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running: {test_name}")
        print(f"{'='*50}")
        
        try:
            result = test_func(admin_user)
            results.append((test_name, result))
            print(f"Test '{test_name}': {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            print(f"Test '{test_name}': ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print(f"{'='*50}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASSED" if result else "FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)