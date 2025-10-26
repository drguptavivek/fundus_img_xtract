#!/usr/bin/env python3
"""
Test script for form submission with UUIDs in intra-rater tasks.
"""

import requests
import json
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "test2ComophArbit"
PASSWORD = "Vivek@2026"

def login(session):
    """Login to the application."""
    login_url = f"{BASE_URL}/login"
    
    # Get the login page to extract CSRF token
    response = session.get(login_url)
    if response.status_code != 200:
        print(f"Failed to get login page: {response.status_code}")
        return False
    
    # Extract CSRF token
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    csrf_token = csrf_input['value'] if csrf_input else None
    
    if not csrf_token:
        print("Could not find CSRF token in login page")
        return False
    
    # Submit login form
    login_data = {
        'username': USERNAME,
        'password': PASSWORD,
        'csrf_token': csrf_token
    }
    
    response = session.post(login_url, data=login_data, allow_redirects=False)
    
    # Check if login was successful (redirect to home page)
    if response.status_code in [302, 303]:
        print("Login successful!")
        return True
    else:
        print(f"Login failed with status code: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return False

def get_intra_task_page(session, uuid):
    """Get the intra-rater task page to extract form data."""
    url = f"{BASE_URL}/grading/intra-task/{uuid}"
    response = session.get(url)
    
    if response.status_code != 200:
        print(f"Failed to get intra-rater task page: {response.status_code}")
        return None, None
    
    # Extract CSRF token and form data
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the grading form
    form = soup.find('form', {'data-grading-form': 'true'})
    if not form:
        print("Could not find grading form")
        return None, None
    
    # Extract CSRF token
    csrf_input = form.find('input', {'name': 'csrf_token'})
    csrf_token = csrf_input['value'] if csrf_input else None
    
    # Extract task UUID from hidden field
    task_uuid_input = form.find('input', {'name': 'task_uuid'})
    task_uuid = task_uuid_input['value'] if task_uuid_input else None
    
    # Find available grading options
    grading_options = []
    radio_inputs = form.find_all('input', {'name': 'label_id'})
    for radio in radio_inputs:
        if 'value' in radio.attrs:
            grading_options.append(int(radio['value']))
    
    return csrf_token, task_uuid, grading_options[0] if grading_options else None

def test_form_submission(session, uuid):
    """Test submitting the intra-rater form with a valid UUID."""
    print(f"\n=== Testing Form Submission with UUID: {uuid} ===")
    
    # Get the task page
    csrf_token, task_uuid, first_option = get_intra_task_page(session, uuid)
    
    if not csrf_token or not task_uuid:
        print("❌ Failed to get form data")
        return False
    
    if task_uuid != uuid:
        print(f"❌ UUID mismatch: expected {uuid}, got {task_uuid}")
        return False
    
    print(f"✅ Successfully retrieved form with UUID: {task_uuid}")
    
    # Submit the form with a valid grade
    submit_url = f"{BASE_URL}/grading/intra-task/submit"
    
    form_data = {
        'task_uuid': task_uuid,
        'label_id': first_option,
        'comment': 'Test comment from form submission test',
        'action': 'save_close',
        'csrf_token': csrf_token
    }
    
    response = session.post(submit_url, data=form_data, allow_redirects=False)
    
    print(f"Submission status code: {response.status_code}")
    
    if response.status_code == 302:
        # Check redirect location
        location = response.headers.get('Location', '')
        if '/grading' in location:
            print("✅ Form submission successful - redirected to grading index")
            return True
        else:
            print(f"❌ Unexpected redirect: {location}")
            return False
    else:
        print(f"❌ Form submission failed")
        print(f"Response: {response.text[:500]}")
        return False

def test_invalid_uuid_submission(session, uuid):
    """Test submitting form with invalid UUID."""
    print(f"\n=== Testing Form Submission with Invalid UUID: {uuid} ===")
    
    # Try to submit directly with invalid UUID
    submit_url = f"{BASE_URL}/grading/intra-task/submit"
    
    form_data = {
        'task_uuid': uuid,
        'label_id': 1,
        'comment': 'Test with invalid UUID',
        'action': 'save_close',
        'csrf_token': 'dummy_token'  # This will fail but we want to see UUID validation first
    }
    
    response = session.post(submit_url, data=form_data, allow_redirects=False)
    
    print(f"Invalid UUID submission status code: {response.status_code}")
    
    if response.status_code == 302:
        # Should redirect to grading index with error message
        location = response.headers.get('Location', '')
        if '/grading' in location:
            print("✅ Invalid UUID correctly rejected - redirected to grading index")
            return True
        else:
            print(f"❌ Unexpected redirect for invalid UUID: {location}")
            return False
    else:
        print(f"❌ Invalid UUID submission failed")
        print(f"Response: {response.text[:500]}")
        return False

def main():
    session = requests.Session()
    
    # Login first
    if not login(session):
        return
    
    # Test valid UUID form submission
    valid_uuid = "5a372b5e-ee3d-46ee-88f7-64e81dbf370c"  # Our test task
    test_form_submission(session, valid_uuid)
    
    # Test invalid UUID form submission
    invalid_uuids = [
        "invalid-uuid-format",
        "123-456-789",
        ""
    ]
    
    for uuid in invalid_uuids:
        test_invalid_uuid_submission(session, uuid)

if __name__ == "__main__":
    main()