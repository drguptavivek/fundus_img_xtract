# Job Utilities Documentation

This document provides an overview of the utility functions available in the job utilities module. These utilities are designed for handling job data, particularly for ZIP uploads.

## Module Overview

This module provides utility functions for handling job data, particularly for ZIP uploads.

## Functions

### `get_recent_zip_uploads(limit: int = 100, job_type: str = "zip upload") -> List[Dict[str, Any]]`

Get recent ZIP upload jobs with success/failure status

**Parameters:**
- `limit` (int): Maximum number of records to return (default: 100)
- `job_type` (str): Type of job to filter (default: "zip upload")

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing job information and status counts

**Result Dictionary Fields:**
- `job` (Job): The job object
- `total_items` (int): Total number of items in the job
- `successful_items` (int): Number of successful items in the job
- `failed_items` (int): Number of failed items in the job
- `processing_items` (int): Number of processing items in the job
- `status` (str): Overall job status ('processing', 'partial', 'failed', or 'success')
- `status_class` (str): CSS class for displaying the status ('text-warning', 'text-danger', or 'text-success')

**Implementation Details:**
- Uses selectinload to efficiently load related lab unit and hospital data
- Counts successful, failed, and processing items from the job items
- Determines overall status based on item states:
  - If any items are still processing: status is 'processing'
  - If there are failed items: status is 'failed' (or 'partial' if there are also successful items)
  - If all items are successful: status is 'success'
- Properly closes the database session after the query