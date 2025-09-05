# Audit Workflows Documentation

## Overview

The audit module provides data quality assurance tools for administrators to identify and review inconsistencies or missing information in the patient encounter data. Currently, it includes functionality to identify patient encounters that are missing capture dates.

## Routes

### GET `/audit/missing_capture_date`

**Access Control**: Restricted to users with `admin` role only.

**Description**: Displays a list of patient encounters that are missing capture dates. This helps administrators identify data quality issues that need to be addressed.

**Template**: `audit/missing_capture_date.html`

**Data Retrieval**:
- Queries the `PatientEncounters` table for records where `capture_date_dt` is NULL
- Orders results by ID in descending order (most recent first)
- Calculates the total count of missing capture date records

**Response**:
- `items`: List of PatientEncounters objects with missing capture dates
- `total`: Count of total missing capture date records

## Implementation Details

### Missing Capture Date Audit

This workflow identifies patient encounters that have not had their capture date properly parsed and stored in the `capture_date_dt` field. The `capture_date_dt` field is a standardized date column that should contain the parsed date from the original `capture_date` string field.

#### Data Flow
1. The system queries the database for all PatientEncounters where `capture_date_dt` is NULL
2. Results are ordered by ID in descending order to show the most recent entries first
3. The total count is calculated for display
4. Results are rendered in the audit template

#### Use Case
This audit tool helps administrators:
- Identify data quality issues in the ingestion process
- Track down encounters that may have had parsing errors
- Ensure all encounters have proper date information for reporting and analysis

#### Template Display
The `audit/missing_capture_date.html` template displays:
- Total count of encounters with missing capture dates
- A list of encounters with their details
- Navigation to view individual encounter information

## Database Schema Context

### PatientEncounters Table
- `capture_date`: Original string representation of the capture date (unparsed)
- `capture_date_dt`: Parsed date field that should contain a standardized date value
- When `capture_date_dt` is NULL, it indicates the parsing process either failed or was not completed

## Future Enhancements

The audit module is designed to be extensible for additional data quality checks such as:
- Duplicate patient records
- Inconsistent data formats
- Missing required fields
- Invalid value ranges