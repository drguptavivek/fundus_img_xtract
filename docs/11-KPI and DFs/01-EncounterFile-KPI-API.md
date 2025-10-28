# Encounter Files KPI API Documentation

## Overview

This document describes the REST API endpoints for accessing operational KPIs and metrics derived from encounter files data. All endpoints respect user lab unit access permissions and provide filtered data based on user eligibility.

## Base URL

```
/api/kpis/encounter-files/
```

## Authentication

All endpoints require authentication and appropriate roles:
- `admin` - Full access to all data
- `data_manager` - Access to assigned lab units

## Data Scoping

All endpoints automatically apply user access control:
- **Admin users**: Access to all encounter data
- **Non-admin users**: Only data from their assigned lab units
- Implemented via `get_user_lab_unit_ids()` from `utils.upload_eligibility`

## Common Parameters

### Date Filters
- `start_date` (optional): ISO date string (YYYY-MM-DD)
- `end_date` (optional): ISO date string (YYYY-MM-DD)

### Location Filters
- `hospital_ids` (optional): Comma-separated list of hospital IDs
- `lab_unit_ids` (optional): Comma-separated list of lab unit IDs


### Response Format

All endpoints return JSON with the following structure:
```json
{
  "success": true,
  "data": {...},
  "message": "Data retrieved successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Error Response Format

```json
{
  "success": false,
  "error": "Error type",
  "message": "Detailed error message"
}
```

## Endpoints

### 1. Monthly Upload Volumes

**Endpoint**: `year-month-wise-uploads`

**Method**: `GET`

**Description**: Returns monthly aggregated upload metrics grouped by upload year-month. For each upload year-month, counts number of uploads, captures, DR reports, glaucoma reports, and encounters with no reports.

**Parameters**:
- `start_date`, `end_date`: Date range filter (applied to upload dates)
- `hospital_ids` (optional): Comma-separated list of hospital IDs
- `lab_unit_ids` (optional): Comma-separated list of lab unit IDs

**Response**:
```json
{
  "success": true,
  "data": {
    "period": "2024-01 to 2024-12",
    "summary": {
      "total_uploads": 1750,
      "total_captures": 1800,
      "total_dr_reports": 1200,
      "total_glaucoma_reports": 900,
      "total_no_reports": 300
    },
    "monthly_data": [
      {
        "year": 2024,
        "month": 1,
        "month_name": "January",
        "uploads": 142,
        "captures": 150,
        "dr_reports": 95,
        "glaucoma_reports": 72,
        "no_reports": 33,
        "hospital_id": 1,
        "hospital_name": "Main Hospital",
        "lab_unit_id": 1,
        "lab_unit_name": "Screening Unit A"
      }
    ]
  }
}
```

**Note**: Date filters apply to upload dates (when files were uploaded to system), not capture dates (when images were taken).

### 2. Report Generation Metrics

**Endpoint**: `dr-reports-count`

**Method**: `GET`

**Description**: Returns DR report generation statistics

**Response**:
```json
{
  "success": true,
  "data": {
    "period": "2024-01 to 2024-12",
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
  }
}
```

**Endpoint**: `glaucoma-reports-count`

**Method**: `GET`

**Description**: Returns glaucoma report generation statistics

**Response**: Similar structure to DR reports endpoint


### 3. Image Analysis Metrics

**Endpoint**: `images-count`

**Method**: `GET`

**Description**: Returns image volume and verification metrics

**Response**:
```json
{
  "success": true,
  "data": {
    "total_images": 8500,
    "verified_images": 7200,
    "verification_rate": 84.7,
    "by_lab_unit": [
      {"lab_unit_id": 1, "lab_unit_name": "Unit A", "total": 4200, "verified": 3600},
      {"lab_unit_id": 2, "lab_unit_name": "Unit B", "total": 4300, "verified": 3600}
    ]
  }
}
```


### 4. Clinical Results Distribution

**Endpoint**: `dr-results-distribution`

**Method**: `GET`

**Description**: Returns distribution of DR qualitative results

**Response**:
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
  }
}
```

**Endpoint**: `glaucoma-results-distribution`

**Method**: `GET`

**Description**: Returns distribution of glaucoma results

**Response**: Similar structure to DR results

**Endpoint**: `vcdr-distribution`

**Method**: `GET`

**Description**: Returns VCDR value distribution for both eyes

**Response**:
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
  }
}
```

### 5. Processing Efficiency Metrics

**Endpoint**: `processing-times`

**Method**: `GET`

**Description**: Returns processing time analysis and bottlenecks

**Response**:
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
  }
}
```


### 6. Lab Unit Performance

**Endpoint**: `lab-unit-performance`

**Method**: `GET`

**Description**: Returns comparative performance metrics by lab unit

**Response**:
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
  }
}
```

## Error Responses

### Authentication Error
```json
{
  "success": false,
  "error": "Authentication required",
  "message": "You must be logged in with appropriate permissions"
}
```

### Permission Error
```json
{
  "success": false,
  "error": "Access denied",
  "message": "You do not have permission to access this lab unit data"
}
```

### Validation Error
```json
{
  "success": false,
  "error": "Invalid parameters",
  "message": "start_date must be before end_date"
}
```

## Usage Examples

### JavaScript/Frontend

```javascript
// Load monthly upload data
async function loadMonthlyUploadData() {
  try {
    const response = await fetch('/api/kpis/encounter-files/year-month-wise-uploads?start_date=2024-01-01&end_date=2024-12-31&hospital_ids=1,2,3&lab_unit_ids=1,2');
    const result = await response.json();
    
    if (result.success) {
      updateMonthlyUploadChart(result.data);
    } else {
      console.error('Error:', result.message);
      showFlashToast(result.message, 'error');
    }
  } catch (error) {
    console.error('Network error:', error);
    showFlashToast('Failed to load KPI data', 'error');
  }
}

// Update chart with API data
function updateMonthlyUploadChart(data) {
  const chartData = {
    labels: data.monthly_data.map(d => `${d.year}-${String(d.month).padStart(2, '0')}`),
    datasets: [{
      label: 'Monthly Uploads',
      data: data.monthly_data.map(d => d.uploads),
      backgroundColor: '#1f77b4',
      borderColor: '#1f77b4',
      borderWidth: 1
    }]
  };
  
  // Update existing chart
  if (window.monthlyUploadChart) {
    window.monthlyUploadChart.data = chartData;
    window.monthlyUploadChart.update();
  } else {
    const ctx = document.getElementById('monthlyUploadChart').getContext('2d');
    window.monthlyUploadChart = new Chart(ctx, {
      type: 'line',
      data: chartData,
      options: getChartOptions('Monthly Upload Trends')
    });
  }
}
```

### Python/Backend

```python
import requests

# Example API call
response = requests.get(
    'http://localhost:5001/api/kpis/encounter-files/year-month-wise-uploads',
    params={
        'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'hospital_ids': '1,2,3',
        'lab_unit_ids': '1,2'
    },
    headers={'Authorization': 'Bearer your-token-here'}
)

if response.status_code == 200:
    data = response.json()
    if data['success']:
        process_kpi_data(data['data'])
    else:
        print(f"API Error: {data['message']}")
```

## Error Handling

### Parameter Validation Errors
- Invalid date format: Returns 400 with "Invalid start_date format. Use YYYY-MM-DD"
- Invalid hospital/lab unit IDs: Returns 400 with "Invalid hospital_ids format. Use comma-separated integers"
- Date range validation: Returns 400 with "start_date must be before end_date"

### Authentication Errors
- Missing authentication: Returns 401 with login redirect
- Insufficient permissions: Returns 403 with access denied message

### Server Errors
- Database connection issues: Returns 500 with "Internal server error"
- Query execution errors: Returns 500 with detailed error message

## Rate Limiting

- **Standard endpoints**: 100 requests per minute
- **Heavy endpoints** (processing-times, lab-unit-performance): 50 requests per minute
- **Burst limit**: 200 requests per 5-minute window

## Caching

- **Monthly data**: Cached for 15 minutes
- **Distribution data**: Cached for 10 minutes
- **Real-time metrics**: Cached for 2 minutes
- **Cache invalidation**: Automatic on new data updates

## Version History

- **v1.0**: Initial implementation with core endpoints
- **v1.1**: Added filtering and pagination support
- **v1.2**: Enhanced error handling and caching
- **v1.3**: Added year filter parameter and improved response formats
- **v1.4**: Simplified year-month-wise-uploads endpoint to group by upload year-month and count DR/glaucoma reports; removed year filter parameter