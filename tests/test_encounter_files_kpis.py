"""
Test file for EncounterFiles KPI API endpoints.

This file tests the EncounterFiles KPI endpoints using authentication helpers
to ensure proper functionality and data accuracy.
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_auth_helpers import login_as_test_admin, login_as_test_manager, make_authenticated_request


def test_encounter_files_filtered_dataframe():
    """Test the filtered dataframe endpoint for EncounterFiles."""
    print("Testing EncounterFiles filtered dataframe endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/filtered-dataframe"
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


def test_encounter_files_filtered_dataframe_excel():
    """Test the filtered dataframe Excel export endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles filtered dataframe Excel export endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test Excel export
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/filtered-dataframe-excel"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Excel Export Status Code: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"Content-Disposition: {response.headers.get('Content-Disposition', 'N/A')}")
    if response.status_code != 200:
        print(f"Excel Export Error: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_year_month_wise_uploads():
    """Test the year month wise uploads endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles year month wise uploads endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            summary = data.get('data', {}).get('summary', {})
            monthly_data = data.get('data', {}).get('monthly_data', [])
            
            print(f"Total Uploads: {summary.get('total_uploads', 0)}")
            print(f"Total Captures: {summary.get('total_captures', 0)}")
            print(f"Total DR Reports: {summary.get('total_dr_reports', 0)}")
            print(f"Total Glaucoma Reports: {summary.get('total_glaucoma_reports', 0)}")
            print(f"Total No Reports: {summary.get('total_no_reports', 0)}")
            print(f"Monthly Data Points: {len(monthly_data)}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_dr_reports_count():
    """Test the DR reports count endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles DR reports count endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/dr-reports-count"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            dr_reports = data.get('data', {}).get('dr_reports', {})
            print(f"Total DR Reports: {dr_reports.get('total', 0)}")
            print(f"Percentage DR Reports: {dr_reports.get('percentage', 0)}%")
            print(f"Hospitals with DR Reports: {len(dr_reports.get('by_hospital', []))}")
            print(f"Lab Units with DR Reports: {len(dr_reports.get('by_lab_unit', []))}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_glaucoma_reports_count():
    """Test the glaucoma reports count endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles glaucoma reports count endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/glaucoma-reports-count"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            glaucoma_reports = data.get('data', {}).get('glaucoma_reports', {})
            print(f"Total Glaucoma Reports: {glaucoma_reports.get('total', 0)}")
            print(f"Percentage Glaucoma Reports: {glaucoma_reports.get('percentage', 0)}%")
            print(f"Monthly Breakdown: {len(glaucoma_reports.get('monthly_breakdown', []))} months")
            print(f"Hospitals with Glaucoma Reports: {len(glaucoma_reports.get('by_hospital', []))}")
            print(f"Lab Units with Glaucoma Reports: {len(glaucoma_reports.get('by_lab_unit', []))}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_images_count():
    """Test the images count endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles images count endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/images-count"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            images_data = data.get('data', {})
            print(f"Total Encounters: {images_data.get('total_encounters', 0)}")
            print(f"Verified Images: {images_data.get('verified_images', 0)}")
            print(f"Verification Rate: {images_data.get('verification_rate', 0)}%")
            print(f"Lab Units Data: {len(images_data.get('by_lab_unit', []))}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_dr_results_distribution():
    """Test the DR results distribution endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles DR results distribution endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/dr-results-distribution"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            distribution = data.get('data', {})
            print(f"DR Results Distribution: {distribution.get('distribution', {})}")
            print(f"DR Percentages: {distribution.get('percentages', {})}")
            print(f"Monthly Trends: {len(distribution.get('monthly_trends', []))} months")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_glaucoma_results_distribution():
    """Test the glaucoma results distribution endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles glaucoma results distribution endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/glaucoma-results-distribution"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            distribution = data.get('data', {})
            print(f"Glaucoma Results Distribution: {distribution.get('distribution', {})}")
            print(f"Glaucoma Percentages: {distribution.get('percentages', {})}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_vcdr_distribution():
    """Test the VCDR distribution endpoint for EncounterFiles."""
    print("\nTesting EncounterFiles VCDR distribution endpoint...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test basic request
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/vcdr-distribution"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            vcdr_data = data.get('data', {})
            right_eye = vcdr_data.get('right_eye', {})
            left_eye = vcdr_data.get('left_eye', {})
            
            print(f"Right Eye Mean: {right_eye.get('mean', 0)}")
            print(f"Right Eye Median: {right_eye.get('median', 0)}")
            print(f"Right Eye STD: {right_eye.get('std_dev', 0)}")
            print(f"Left Eye Mean: {left_eye.get('mean', 0)}")
            print(f"Left Eye Median: {left_eye.get('median', 0)}")
            print(f"Left Eye STD: {left_eye.get('std_dev', 0)}")
        else:
            print(f"Error: {data.get('error', 'Unknown error')}")
    else:
        print(f"Error Response: {response.text}")
    
    return response.status_code == 200


def test_encounter_files_with_date_filters():
    """Test EncounterFiles endpoints with date filters."""
    print("\nTesting EncounterFiles endpoints with date filters...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test with date range
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Test filtered dataframe with dates
    url = f"http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?start_date={start_date}&end_date={end_date}"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Date Filter Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            summary = data.get('data', {}).get('summary', {})
            monthly_data = data.get('data', {}).get('monthly_data', [])
            print(f"Total Uploads (last 30 days): {summary.get('total_uploads', 0)}")
            print(f"Monthly Data Points: {len(monthly_data)}")
    
    return response.status_code == 200


def test_encounter_files_with_location_filters():
    """Test EncounterFiles endpoints with location filters."""
    print("\nTesting EncounterFiles endpoints with location filters...")
    
    # Login as admin user
    admin_cookies = login_as_test_admin()
    
    # Test with hospital filter (assuming hospital ID 1 exists)
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?hospital_ids=1"
    response = make_authenticated_request(url, admin_cookies)
    
    print(f"Hospital Filter Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            monthly_data = data.get('data', {}).get('monthly_data', [])
            print(f"Data Points with Hospital Filter: {len(monthly_data)}")
            for entry in monthly_data[:3]:  # Print first 3 entries
                print(f"  - Hospital {entry.get('hospital_name', 'Unknown')}: {entry.get('uploads', 0)} uploads")
    
    return response.status_code == 200


def test_encounter_files_permissions():
    """Test EncounterFiles endpoints with different user roles."""
    print("\nTesting EncounterFiles endpoints with different user roles...")
    
    # Test with manager role
    manager_cookies = login_as_test_manager()
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/dr-reports-count"
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
    """Run all EncounterFiles KPI tests."""
    print("=" * 60)
    print("ENCOUNTER FILES KPI API TESTS")
    print("=" * 60)
    
    tests = [
        ("Filtered Dataframe", test_encounter_files_filtered_dataframe),
        ("Filtered Dataframe Excel Export", test_encounter_files_filtered_dataframe_excel),
        ("Year Month Wise Uploads", test_encounter_files_year_month_wise_uploads),
        ("DR Reports Count", test_encounter_files_dr_reports_count),
        ("Glaucoma Reports Count", test_encounter_files_glaucoma_reports_count),
        ("Images Count", test_encounter_files_images_count),
        ("DR Results Distribution", test_encounter_files_dr_results_distribution),
        ("Glaucoma Results Distribution", test_encounter_files_glaucoma_results_distribution),
        ("VCDR Distribution", test_encounter_files_vcdr_distribution),
        ("Date Filters", test_encounter_files_with_date_filters),
        ("Location Filters", test_encounter_files_with_location_filters),
        ("Permissions", test_encounter_files_permissions),
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