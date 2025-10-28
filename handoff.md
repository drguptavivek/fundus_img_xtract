# KPI Infrastructure Handoff

## Current Status

I have successfully enhanced the KPI infrastructure in `api/kpis/encounter_files.py` with comprehensive improvements:

## ✅ Completed Infrastructure Setup:

### 1. Standardized Response Functions
Enhanced response functions for consistency across all APIs:
- **`create_kpi_response()`**: Now accepts optional `filters_applied` parameter
- **`create_error_response()`**: Standardized error handling
- **`create_combined_response()`**: Available for future combined API needs

### 2. Enhanced Parameter Parsing with Logging
Updated `parse_filter_params()` function that:
- Parses and validates all filter parameters (date, hospital, lab unit)
- **Added comprehensive logging to `runtime_error.log`**:
  - Logs successful parameter parsing
  - Logs parameter parsing errors with full context
  - Includes raw request args for debugging
- Provides clear error visibility for troubleshooting

### 3. Centralized Filtering Function
Enhanced `get_filtered_encounter_dataframe()` function that:
- Uses `generate_encounter_upload_metrics_df()` utility to get complete dataframe
- **Returns tuple of (filtered DataFrame, filters_applied dictionary)** for easy consumption by endpoints
- Applies user permissions (all users including admins are scoped by their lab unit eligibility)
- Applies date filters through `upload_date` (from ZipFile)
- Applies hospital and lab unit filters
- Handles all filter scenarios correctly
- Includes robust error handling with logging to `runtime_error.log`

### 4. New Utility API Endpoints

#### A. Filtered Dataframe API (`/kpis/encounter-files/filtered-dataframe`)
- Returns filtered dataframe as JSON for use in app templates
- Uses same common filtering function as KPI endpoints
- Provides metadata including period, total records, columns, and applied filters
- Supports all filter parameters (date, hospital, lab unit)

#### B. Excel Export API (`/kpis/encounter-files/filtered-dataframe-excel`)
- Returns filtered dataframe as Excel file for download
- Uses same filtering logic for consistency
- Generates dynamic filename with timestamp and filter info
- Creates two-sheet Excel file: "Encounter Data" and "Filters Applied"

### 5. Updated KPI Endpoints

#### A. `year_month_wise_uploads` - Now Uses Filtered Dataframe
- Updated to use `get_filtered_encounter_dataframe()` for consistent filtering
- Replaced complex SQL with pandas operations using `pd.Grouper`
- Handles empty dataframe gracefully
- **Uses standardized `create_kpi_response(data, message, filters_applied)` with explicit variables**
- Maintains same response format for compatibility

#### B. `dr_reports_count` - Updated to Use Filtered Dataframe
- Completely refactored to use `get_filtered_encounter_dataframe()` for consistent filtering
- Replaced complex SQL queries with pandas operations
- **Uses explicit variable pattern for response data, message, and filters**
- Maintains same response format for compatibility

#### C. `glaucoma_reports_count` - Updated to Use Filtered Dataframe
- Completely refactored to use `get_filtered_encounter_dataframe()` for consistent filtering
- Replaced complex SQL queries with pandas operations
- **Uses explicit variable pattern for response data, message, and filters**
- Maintains same response format for compatibility

#### D. `images_count` - Simplified to Use Filtered Dataframe
- **Significantly simplified from ~140 lines to ~50 lines**
- Updated to use `get_filtered_encounter_dataframe()` for consistent filtering
- Replaced multiple complex SQL queries with simple pandas operations
- **Uses pandas aggregation functions for lab unit breakdowns**
- **Uses explicit variable pattern for response data, message, and filters**

## 🎯 Key Benefits Achieved:

1. **Standardized Responses**: All APIs use consistent response format
2. **Comprehensive Logging**: Parameter parsing and filtering errors are logged to `runtime_error.log`
3. **Filter Visibility**: Each API response shows exactly what filters were applied
4. **Centralized Filtering**: Single function handles all filtering logic
5. **Consistent Behavior**: All endpoints use same filtering approach
6. **Proper Date Handling**: Date filters applied through `ZipFile.upload_date`
7. **User Scoping**: All users (including admins) are properly scoped by lab unit eligibility
8. **Template Integration**: Frontend can access filtered data for custom visualizations
9. **Excel Export**: Users can download filtered data for offline analysis
10. **Error Visibility**: Comprehensive logging for debugging
11. **Clean Architecture**: Removed obsolete functions, simplified codebase
12. **All Filter Scenarios**: Works correctly with no filter, partial filters, or complete filters
13. **Enhanced Function Return**: `get_filtered_encounter_dataframe()` returns both DataFrame and filters_applied
14. **Improved Code Readability**: Explicit variable pattern for response data, message, and filters
15. **Significant Code Reduction**: `images_count` endpoint reduced from ~140 lines to ~50 lines

## ✅ All KPI Endpoints Updated:

All endpoints have been successfully updated to use the new filtered dataframe approach:

1. **`dr_results_distribution`** - ✅ Updated to use filtered dataframe with proper data joining
2. **`glaucoma_results_distribution`** - ✅ Updated to use filtered dataframe with proper data joining
3. **`vcdr_distribution`** - ✅ Updated to use filtered dataframe with VCDR calculations

## 📋 Implementation Guidelines for Future Endpoints:

When creating new KPI endpoints, follow this established pattern:

### 1. Import KPI Utilities
```python
from api.kpis.kpiutils import (
    create_kpi_response,
    create_error_response,
    parse_filter_params,
    get_user_permissions,
    determine_period,
    create_filters_applied_dict,
    validate_dataframe_not_empty,
    log_endpoint_usage
)
```

### 2. Database Context Manager Pattern
```python
with with_session() as db:
    try:
        params = parse_filter_params()
        user_lab_unit_ids = get_user_permissions(current_user.id)  # No admin override
        
        # Get filtered dataframe using common function
        df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)
        
        # Your KPI logic here using pandas operations
        
        # Log endpoint usage for monitoring
        log_endpoint_usage("your_endpoint_name", len(df), current_user.id)
        
        return create_kpi_response(response_data, response_message, filters_applied=filters_applied)
        
    except ValueError as e:
        return create_error_response("Invalid parameters", str(e))
    except Exception as e:
        return create_error_response("Internal server error", str(e), 500)
```

### 2. DataFrame Approach Best Practices
- **Always use `get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)`** for consistent filtering
- **Use pandas operations** instead of complex SQL queries
- **Handle empty DataFrames gracefully** with `if df.empty:` checks
- **Use proper column names** from the DataFrame (e.g., 'verified_images', 'encounter_id')
- **Convert datetime columns** before grouping: `df['upload_date'] = pd.to_datetime(df['upload_date'])`

### 4. Logging Pattern
- **Parameter parsing errors** are automatically logged by `parse_filter_params()` (from kpiutils)
- **DataFrame generation errors** are automatically logged by `get_filtered_encounter_dataframe()`
- **Use `log_endpoint_usage()`** for consistent endpoint monitoring:
```python
log_endpoint_usage("your_endpoint_name", len(df), current_user.id)
```
- **Add specific logging** for endpoint-specific logic if needed:
```python
endpoint_logger = logging.getLogger('runtime_error')
endpoint_logger.info(f"Processing KPI data for {len(df)} records")
```

### 4. Response Pattern
```python
# Always include filters_applied in response
return create_kpi_response(response_data, "Data retrieved successfully", filters_applied=filters_applied)
```

### 5. Common DataFrame Columns Available
- `encounter_id` - Unique encounter identifier
- `upload_date` - When files were uploaded (for filtering)
- `capture_date` - When images were taken
- `hospital_id`, `hospital_name` - Hospital information
- `lab_unit_id`, `lab_unit_name` - Lab unit information
- `has_dr_report` - Boolean flag for DR reports
- `has_glaucoma_report` - Boolean flag for glaucoma reports
- `verified_images` - Count of verified images

## 🔒 Security Enhancement:

- **No Admin Override**: `get_user_permissions()` in kpiutils.py uses `get_user_lab_unit_ids_no_admin_override()`
- **Consistent Access Control**: All users (including admins) are scoped by their lab unit eligibility
- **Secure Data Access**: Prevents admin bypass of lab unit restrictions in KPI endpoints

## 🔄 Current Status:

- **7/9 endpoints working** - All existing endpoints updated and functional
- **2/9 endpoints missing** - `processing-times` and `lab-unit-performance` (not implemented yet)
- **Infrastructure complete** - Ready for additional endpoints using same pattern
- **Documentation updated** - `docs/11-KPI and DFs/kpiApiGuidance.md` includes kpiutils.py guidance

## 📁 Files Modified:

- `api/kpis/kpiutils.py` - **NEW**: Centralized utilities for all KPI development
- `api/kpis/encounter_files.py` - Updated to use kpiutils.py functions
- `docs/11-KPI and DFs/kpiApiGuidance.md` - Updated with kpiutils.py guidance
