# KPI API Testing Documentation

## Overview

This document provides comprehensive testing guidelines for the Encounter Files KPI API endpoints. It includes test cases for different user roles, permission filtering, parameter validation, and error scenarios.

## Test Environment Setup

### Prerequisites

1. Ensure the Flask application is running on `http://127.0.0.1:5001`

Test suite uses the following user types:
#### Admin User
- Username: `test_admin`
- Password: `Test@2026`
- Role: `admin`
- Access: All lab units and hospitals

#### Data Manager User
- Username: `test_data_manager`
- Password: `TestPassword123!`
- Role: `data_manager`
- Access: Limited to assigned lab units

## Test Script

A test script is available at `tests/test_kpis_api.py` for quick endpoint validation:

```bash
# Run the test script
cd tests
python test_kpis_api.py
```

## Endpoint Testing

### 1. Year-Month Wise Uploads

**Endpoint**: `/api/kpis/encounter-files/year-month-wise-uploads`

#### Test Cases

##### Basic Functionality
```bash
# Test without filters
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "period": "All time",
    "summary": {
      "total_captures": 1800,
      "total_uploads": 1750,
      "avg_processing_time": 2.1,
      "peak_month": "March",
      "peak_volume": 210
    },
    "monthly_data": [
      {
        "year": 2024,
        "month": 1,
        "month_name": "January",
        "captures": 150,
        "uploads": 142,
        "processing_completion_avg": 2.4,
        "hospital_id": 1,
        "hospital_name": "Main Hospital",
        "lab_unit_id": 1,
        "lab_unit_name": "Screening Unit A"
      }
    ]
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

##### Date Range Filtering
```bash
# Test with date range
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?start_date=2024-01-01&end_date=2024-06-30"
```

##### Year Filtering
```bash
# Test with year filter
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?year=2024"
```

##### Location Filtering
```bash
# Test with hospital filter
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?hospital_ids=1,2,3"

# Test with lab unit filter
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?lab_unit_ids=1,2"
```

##### Error Cases
```bash
# Invalid date format
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?start_date=invalid-date"

# Invalid hospital IDs
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?hospital_ids=abc,def"

# Start date after end date
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads?start_date=2024-12-31&end_date=2024-01-01"
```

**Expected Error Response**:
```json
{
  "success": false,
  "error": "Invalid parameters",
  "message": "Invalid start_date format. Use YYYY-MM-DD"
}
```

#### Permission Testing

##### Admin User Access
- Should see data from all lab units
- No location filtering applied automatically

##### Data Manager User Access
- Should only see data from assigned lab units
- Automatic filtering based on `get_user_lab_unit_ids()`

### 2. DR Reports Count

**Endpoint**: `/api/kpis/encounter-files/dr-reports-count`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/dr-reports-count"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "period": "All time",
    "dr_reports": {
      "total": 1200,
      "percentage": 75.5,
      "monthly_breakdown": [400, 380, 420],
      "by_hospital": [
        {"hospital_id": 1, "hospital_name": "Main", "count": 600},
        {"hospital_id": 2, "hospital_name": "Branch", "count": 600}
      ],
      "by_lab_unit": [
        {"lab_unit_id": 1, "lab_unit_name": "Unit A", "count": 300},
        {"lab_unit_id": 2, "lab_unit_name": "Unit B", "count": 280}
      ]
    }
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

##### With Filters
```bash
# Test with date range and location filters
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/dr-reports-count?start_date=2024-01-01&end_date=2024-12-31&hospital_ids=1&lab_unit_ids=1,2"
```

### 3. Glaucoma Reports Count

**Endpoint**: `/api/kpis/encounter-files/glaucoma-reports-count`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/glaucoma-reports-count"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "period": "All time",
    "glaucoma_reports": {
      "total": 950,
      "percentage": 59.4,
      "monthly_breakdown": [300, 320, 330],
      "by_hospital": [
        {"hospital_id": 1, "hospital_name": "Main", "count": 475},
        {"hospital_id": 2, "hospital_name": "Branch", "count": 475}
      ],
      "by_lab_unit": [
        {"lab_unit_id": 1, "lab_unit_name": "Unit A", "count": 240},
        {"lab_unit_id": 2, "lab_unit_name": "Unit B", "count": 220}
      ]
    }
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 4. Images Count

**Endpoint**: `/api/kpis/encounter-files/images-count`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/images-count"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "total_images": 8500,
    "verified_images": 7200,
    "verification_rate": 84.7,
    "by_lab_unit": [
      {
        "lab_unit_id": 1,
        "lab_unit_name": "Unit A",
        "total": 4200,
        "verified": 3600,
        "verification_rate": 85.7
      },
      {
        "lab_unit_id": 2,
        "lab_unit_name": "Unit B",
        "total": 4300,
        "verified": 3600,
        "verification_rate": 83.7
      }
    ]
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 5. DR Results Distribution

**Endpoint**: `/api/kpis/encounter-files/dr-results-distribution`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/dr-results-distribution"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "distribution": {
      "No DR": 450,
      "Mild": 280,
      "Moderate": 180,
      "Severe": 95,
      "Proliferative": 45
    },
    "percentages": {
      "No DR": 38.5,
      "Mild": 23.9,
      "Moderate": 15.4,
      "Severe": 8.1,
      "Proliferative": 3.8
    },
    "monthly_trends": [
      {"month": "2024-01", "mild_percentage": 22.1},
      {"month": "2024-02", "mild_percentage": 24.5}
    ]
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 6. Glaucoma Results Distribution

**Endpoint**: `/api/kpis/encounter-files/glaucoma-results-distribution`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/glaucoma-results-distribution"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "distribution": {
      "Normal": 600,
      "Suspect": 250,
      "Mild": 80,
      "Moderate": 15,
      "Severe": 5
    },
    "percentages": {
      "Normal": 63.2,
      "Suspect": 26.3,
      "Mild": 8.4,
      "Moderate": 1.6,
      "Severe": 0.5
    }
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 7. VCDR Distribution

**Endpoint**: `/api/kpis/encounter-files/vcdr-distribution`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/vcdr-distribution"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "right_eye": {
      "mean": 0.45,
      "median": 0.42,
      "std_dev": 0.18,
      "range": {
        "normal_0_5": 65,
        "borderline_0_5_0_7": 89,
        "abnormal_0_7_0_8": 45,
        "severely_abnormal_gt_0_8": 12
      }
    },
    "left_eye": {
      "mean": 0.47,
      "median": 0.44,
      "std_dev": 0.19,
      "range": {
        "normal_0_5": 62,
        "borderline_0_5_0_7": 85,
        "abnormal_0_7_0_8": 48,
        "severely_abnormal_gt_0_8": 16
      }
    }
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 8. Processing Times

**Endpoint**: `/api/kpis/encounter-files/processing-times`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/processing-times"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "processing_times": {
      "avg_hours": 2.4,
      "median_hours": 1.8,
      "p95_hours": 5.2,
      "p99_hours": 8.1,
      "distribution": {
        "0-1h": 250,
        "1-2h": 400,
        "2-4h": 180,
        "4-8h": 90,
        ">8h": 45
      }
    },
    "trend": [
      {"date": "2024-01-01", "avg_time": 2.1},
      {"date": "2024-01-02", "avg_time": 2.3}
    ]
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 9. Lab Unit Performance

**Endpoint**: `/api/kpis/encounter-files/lab-unit-performance`

#### Test Cases

##### Basic Functionality
```bash
curl -b "session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/lab-unit-performance"
```

**Expected Response**:
```json
{
  "success": true,
  "data": {
    "performance_data": [
      {
        "lab_unit_id": 1,
        "lab_unit_name": "Screening Unit A",
        "hospital_name": "Main Hospital",
        "metrics": {
          "total_encounters": 450,
          "completely_verified_rate": 78.5,
          "avg_processing_time": 1.8,
          "dr_report_rate": 65.2,
          "glaucoma_report_rate": 58.9,
          "verification_efficiency": 92.1,
          "quality_score": 85.3
        },
        "ranking": {
          "overall": 3,
          "processing_speed": 2,
          "verification_rate": 4,
          "quality": 1
        }
      }
    ],
    "benchmarks": {
      "avg_processing_time": 2.4,
      "avg_verification_rate": 75.0,
      "avg_quality_score": 80.0
    }
  },
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Authentication Testing

### Without Authentication
```bash
curl "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads"
```

**Expected Response**: 302 Redirect to login page

### With Invalid Session
```bash
curl -b "session=invalid_session" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads"
```

**Expected Response**: 302 Redirect to login page

### With Insufficient Permissions
Create a user without `admin` or `data_manager` roles and test access.

**Expected Response**: 403 Forbidden

## Permission Testing Scenarios

### Admin User Tests
1. Access all endpoints without filters
2. Verify data includes all lab units
3. Test location filters work correctly
4. Verify no automatic permission filtering applied

### Data Manager User Tests
1. Access all endpoints
2. Verify data is limited to assigned lab units only
3. Test location filters within allowed lab units
4. Verify attempts to access non-assigned lab units return empty data

## Parameter Validation Testing

### Date Format Validation
```bash
# Valid formats
?start_date=2024-01-01
?end_date=2024-12-31

# Invalid formats
?start_date=01-01-2024
?end_date=2024/01/01
?start_date=not-a-date
```

### ID Format Validation
```bash
# Valid formats
?hospital_ids=1,2,3
?lab_unit_ids=1,2

# Invalid formats
?hospital_ids=abc,def
?lab_unit_ids=one,two
?hospital_ids=1.5,2.7
```

### Range Validation
```bash
# Invalid ranges
?start_date=2024-12-31&end_date=2024-01-01
?year=abc
?year=99999
```

## Performance Testing

### Load Testing
Use tools like `ab` (Apache Benchmark) or `wrk` to test endpoint performance:

```bash
# Basic load test
ab -n 100 -c 10 -H "Cookie: session=<session_cookie>" \
  "http://127.0.0.1:5001/api/kpis/encounter-files/year-month-wise-uploads"
```

### Response Time Benchmarks
- Simple endpoints: < 200ms
- Complex endpoints: < 500ms
- Heavy aggregation endpoints: < 1000ms

## Integration Testing

### Frontend Integration
Test API integration with frontend JavaScript:

```javascript
// Example test function
async function testAPIIntegration() {
  try {
    const response = await fetch('/api/kpis/encounter-files/year-month-wise-uploads', {
      method: 'GET',
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    console.log('API Response:', data);
    
    // Validate response structure
    assert(data.success === true);
    assert('data' in data);
    assert('message' in data);
    assert('timestamp' in data);
    
  } catch (error) {
    console.error('API Test failed:', error);
  }
}
```

## Automated Testing with Pytest

### Test Structure
Create pytest test files following the project's testing patterns:

```python
# tests/test_kpis_api.py
import pytest
from flask import url_for

def test_year_month_wise_uploads_admin(client, admin_user):
    """Test year-month-wise-uploads endpoint with admin user."""
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user.id
        sess['_fresh'] = True
    
    response = client.get('/api/kpis/encounter-files/year-month-wise-uploads')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] is True
    assert 'data' in data
    assert 'monthly_data' in data['data']
    assert 'summary' in data['data']

def test_year_month_wise_uploads_data_manager(client, test_users):
    """Test year-month-wise-uploads endpoint with data_manager user."""
    data_manager = test_users['testResident']  # Has limited lab unit access
    
    with client.session_transaction() as sess:
        sess['user_id'] = data_manager.id
        sess['_fresh'] = True
    
    response = client.get('/api/kpis/encounter-files/year-month-wise-uploads')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['success'] is True
    
    # Verify data is filtered to user's lab units
    for month_data in data['data']['monthly_data']:
        assert month_data['lab_unit_id'] in [1, 2]  # User's assigned lab units

def test_invalid_date_format(client, admin_user):
    """Test endpoint with invalid date format."""
    with client.session_transaction() as sess:
        sess['user_id'] = admin_user.id
        sess['_fresh'] = True
    
    response = client.get('/api/kpis/encounter-files/year-month-wise-uploads?start_date=invalid')
    assert response.status_code == 400
    
    data = response.get_json()
    assert data['success'] is False
    assert 'Invalid start_date format' in data['message']
```

### Running Tests
```bash
# Run all KPI API tests
pytest tests/test_kpis_api.py -v

# Run specific test
pytest tests/test_kpis_api.py::test_year_month_wise_uploads_admin -v

# Run with coverage
pytest tests/test_kpis_api.py --cov=api.kpis.encounter_files --cov-report=html
```

## Test Data Management

### Test Data Setup
Use the existing fixtures in `conftest.py` to set up test data:

```python
@pytest.fixture
def kpi_test_data(db_session):
    """Create test data for KPI endpoints."""
    # Create hospitals
    hospital1 = Hospital(name="Test Hospital 1")
    hospital2 = Hospital(name="Test Hospital 2")
    db_session.add_all([hospital1, hospital2])
    db_session.commit()
    
    # Create lab units
    lab_unit1 = LabUnit(name="Test Lab Unit 1", hospital_id=hospital1.id)
    lab_unit2 = LabUnit(name="Test Lab Unit 2", hospital_id=hospital2.id)
    db_session.add_all([lab_unit1, lab_unit2])
    db_session.commit()
    
    # Create patient encounters with test data
    # ... create encounters, files, reports, etc.
    
    yield {
        'hospitals': [hospital1, hospital2],
        'lab_units': [lab_unit1, lab_unit2]
    }
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: KPI API Tests

on:
  push:
    paths:
      - 'api/kpis/encounter_files.py'
      - 'tests/test_kpis_api.py'
  pull_request:
    paths:
      - 'api/kpis/encounter_files.py'
      - 'tests/test_kpis_api.py'

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run KPI API tests
      run: |
        pytest tests/test_kpis_api.py -v --cov=api.kpis.encounter_files
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Ensure session cookie is valid
   - Check user has required roles
   - Verify user is active

2. **Permission Issues**
   - Verify lab unit assignments
   - Check `get_user_lab_unit_ids()` function
   - Test with admin user to isolate permission issues

3. **Data Issues**
   - Ensure test data exists in database
   - Check date ranges have data
   - Verify relationships between tables

4. **Performance Issues**
   - Check database indexes
   - Monitor query execution time
   - Consider caching for frequently accessed data

### Debugging Tips

1. Enable Flask debug mode to see detailed error messages
2. Use database query logging to analyze SQL queries
3. Add debug prints to trace execution flow
4. Use browser developer tools to inspect API responses
5. Check application logs for error details

## Test Coverage Checklist

- [ ] All 9 endpoints tested with basic functionality
- [ ] Authentication tested for all endpoints
- [ ] Permission filtering tested for both admin and data_manager roles
- [ ] Parameter validation tested for all input parameters
- [ ] Error handling tested for all error scenarios
- [ ] Date filtering tested with various date ranges
- [ ] Location filtering tested with hospital and lab unit filters
- [ ] Response format validation for all endpoints
- [ ] Performance testing for heavy endpoints
- [ ] Integration testing with frontend
- [ ] Automated tests in CI/CD pipeline