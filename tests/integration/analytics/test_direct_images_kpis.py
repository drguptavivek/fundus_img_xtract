"""
Test file for DirectImages KPI API endpoints.

This file tests the DirectImages KPI endpoints using authentication helpers
to ensure proper functionality and data accuracy.
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.integration.auth.test_auth_helpers import login_as_test_admin, login_as_test_manager, make_authenticated_request


def test_direct_images_filtered_dataframe():
    """Test the filtered dataframe endpoint for DirectImages."""
    print("Testing DirectImages filtered dataframe endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/direct-files/filtered-dataframe"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"Response Keys: {response.json().keys()}")
    else:
        print(f"Error Response: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total Records: {data.get('data', {}).get('total_records', 0)}")
        print(f"Columns: {data.get('data', {}).get('columns', [])}")
        print(f"Period: {data.get('data', {}).get('period', 'N/A')}")
    
    return response.status_code == 200


def test_direct_images_upload_metrics():
    """Test the upload metrics endpoint for DirectImages."""
    print("\nTesting DirectImages upload metrics endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/direct-files/upload-metrics"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            metrics = data.get('data', {})
            print(f"Total Uploads: {metrics.get('total_uploads', 0)}")
            print(f"Hospitals Count: {len(metrics.get('by_hospital', []))}")
            print(f"Lab Units Count: {len(metrics.get('by_lab_unit', []))}")
            print(f"Uploaders Count: {len(metrics.get('by_uploader', []))}")
            print(f"Cameras Count: {len(metrics.get('by_camera', []))}")
            print(f"Diseases Count: {len(metrics.get('by_disease', []))}")
            print(f"Pregraded Percentage: {metrics.get('pregraded_percentage', 0)}%")
            print(f"Mydriatic: {metrics.get('mydriatic_breakdown', {})}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_direct_images_with_date_filters():
    """Test DirectImages endpoints with date filters."""
    print("\nTesting DirectImages endpoints with date filters...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test with date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Test filtered dataframe with dates
    url = f"http://127.0.0.1:5001/api/kpis/direct-files/filtered-dataframe?start_date={start_date}&end_date={end_date}"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Date Filter Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            period = data.get('data', {}).get('period', 'N/A')
            total_records = data.get('data', {}).get('total_records', 0)
            print(f"Period: {period}")
            print(f"Total Records (last 30 days): {total_records}")
    
    # Test upload metrics with dates
    url = f"http://127.0.0.1:5001/api/kpis/direct-files/upload-metrics?start_date={start_date}&end_date={end_date}"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Upload Metrics with Dates Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            metrics = data.get('data', {})
            daily_uploads = metrics.get('daily_uploads', [])
            print(f"Daily Uploads Count: {len(daily_uploads)}")
            if daily_uploads:
                print(f"Latest Daily Upload: {daily_uploads[-1]}")
    
    return response.status_code == 200


def test_direct_images_excel_export():
    """Test DirectImages Excel export endpoint."""
    print("\nTesting DirectImages Excel export endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test Excel export
    url = "http://127.0.0.1:5001/api/kpis/direct-files/filtered-dataframe-excel"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Excel Export Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"Content-Disposition: {response.headers.get('Content-Disposition', 'N/A')}")
    if response.status_code != 200:
        print(f"Excel Export Error: {response.text}")
    
    return response.status_code == 200


def test_direct_images_with_location_filters():
    """Test DirectImages endpoints with location filters."""
    print("\nTesting DirectImages endpoints with location filters...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test with hospital filter (assuming hospital ID 1 exists)
    url = "http://127.0.0.1:5001/api/kpis/direct-files/upload-metrics?hospital_ids=1"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Hospital Filter Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            metrics = data.get('data', {})
            hospitals = metrics.get('by_hospital', [])
            print(f"Hospitals in filtered data: {len(hospitals)}")
            for hospital in hospitals:
                print(f"  - Hospital {hospital.get('hospital_name', 'Unknown')}: {hospital.get('upload_count', 0)} uploads")
    
    return response.status_code == 200


def test_direct_images_permissions():
    """Test DirectImages endpoints with different user roles."""
    print("\nTesting DirectImages endpoints with different user roles...")
    
    # Test with manager role
    manager_cookies = login_as_test_manager()
    url = "http://127.0.0.1:5001/api/kpis/direct-files/upload-metrics"
    response = make_authenticated_request(url, manager_cookies)
    
    print(f"Manager Role Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            filters_applied = data.get('filters_applied', {})
            user_lab_units = filters_applied.get('user_lab_unit_ids', [])
            print(f"Manager Lab Units: {user_lab_units}")
    
    return response.status_code == 200


def run_all_tests():
    """Run all DirectImages KPI tests."""
    print("=" * 60)
    print("DIRECT IMAGES KPI API TESTS")
    print("=" * 60)
    
    tests = [
        ("Filtered Dataframe", test_direct_images_filtered_dataframe),
        ("Upload Metrics", test_direct_images_upload_metrics),
        ("Date Filters", test_direct_images_with_date_filters),
        ("Excel Export", test_direct_images_excel_export),
        ("Location Filters", test_direct_images_with_location_filters),
        ("Permissions", test_direct_images_permissions),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, "PASS" if success else "FAIL"))
        except Exception as e:
            print(f"Error in {test_name}: {str(e)}")
            results.append((test_name, f"ERROR: {str(e)}"))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    for test_name, result in results:
        print(f"{test_name}: {result}")
    
    passed_count = sum(1 for _, result in results if result.startswith("PASS"))
    total_count = len(results)
    
    print(f"\nPassed: {passed_count}/{total_count}")
    print(f"Success Rate: {(passed_count/total_count)*100:.1f}%")
    
    return passed_count == total_count


if __name__ == "__main__":
    run_all_tests()