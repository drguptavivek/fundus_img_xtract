# KPI API Development Guide for Coding Agents

## Core Principle
**All KPI development MUST use the centralized utilities in `api/kpis/kpiutils.py`.** This ensures consistency, reusability, and maintainability. Avoid local implementations of shared logic.

## Key File Locations
- **Central Utilities**: `api/kpis/kpiutils.py`
- **Endpoint Definitions**: `api/kpis/encounter_files.py` (or similar)
- **DataFrame Generation**: `utils/dataframeEncounterFiles.py` (or similar)

---

## Standard KPI Endpoint Pattern
Use this structure for all new KPI endpoints. It leverages the central utilities for parsing, permissions, filtering, and response formatting.

```python
from flask_login import current_user
from auth.roles import roles_required
from api.kpis.encounter_files import get_filtered_encounter_dataframe
from api.kpis.kpiutils import (
    create_kpi_response,
    create_error_response,
    parse_filter_params,
    get_user_permissions,
    determine_period,
    validate_dataframe_not_empty,
    log_endpoint_usage,
    handle_common_exceptions,
    handle_nat_values_for_json
)
from utils.utils import with_session

@api_bp.route('/kpis/encounter-files/your-endpoint-name', methods=['GET'])
@login_required
@roles_required("admin", "data_manager")
@handle_common_exceptions # Optional: Handles common exceptions automatically
def your_endpoint_name():
    """Docstring: Describe what the KPI returns. Mention date filters apply to upload_date."""
    with with_session() as db:
        # 1. Parse params and get permissions
        params = parse_filter_params()
        user_lab_unit_ids = get_user_permissions(current_user.id)

        # 2. Get filtered base DataFrame
        df, filters_applied = get_filtered_encounter_dataframe(db, params, user_lab_unit_ids)

        # 3. Handle empty DataFrame
        if not validate_dataframe_not_empty(df, "your_endpoint_name"):
            return create_kpi_response({}, "No data found", filters_applied=filters_applied)

        # 4. Your KPI logic (aggregation, transformation)
        result_df = df.groupby('hospital_name').agg(encounter_count=('encounter_id', 'nunique')).reset_index()
        
        # 5. Clean DataFrame for JSON conversion
        result_df = handle_nat_values_for_json(result_df)

        # 6. Prepare response data
        response_data = {
            "period": determine_period(params),
            "by_hospital": result_df.to_dict('records')
        }

        # 7. Log usage and return standardized response
        log_endpoint_usage("your_endpoint_name", len(df), current_user.id)
        return create_kpi_response(response_data, "Data retrieved successfully", filters_applied=filters_applied)
```

---

## Essential `kpiutils.py` Functions

- **Response Formatting**:
  - `create_kpi_response()`: Standard success response.
  - `create_error_response()`: Standard error response.
- **Parameter Handling**:
  - `parse_filter_params()`: Parses and validates `start_date`, `end_date`, `hospital_ids`, `lab_unit_ids`.
- **Permissions**:
  - `get_user_permissions()`: Gets user's lab unit IDs. **Crucially, this has no admin override.**
- **Data Validation & Cleaning**:
  - `validate_dataframe_not_empty()`: Checks if a DataFrame is empty and logs it.
  - `handle_nat_values_for_json()`: **Use this before `df.to_dict()`** to convert `NaT` and `NaN` to `None` and format datetimes.
- **Helpers**:
  - `determine_period()`: Creates a string description of the filter period.
  - `create_filters_applied_dict()`: Creates the `filters_applied` dictionary for the response.
  - `safe_divide()`, `calculate_percentage()`: Safe math operations.
- **Logging & Decorators**:
  - `log_endpoint_usage()`: Logs endpoint calls for monitoring.
  - `@handle_common_exceptions`: A decorator to auto-handle `ValueError` and `Exception`.

---

## Implementation Checklist

1.  **Endpoint**: Create a new route following the pattern above in `api/kpis/`.
2.  **Imports**: Import all helpers from `api/kpis/kpiutils.py`.
3.  **Permissions**: Use `@roles_required` and `get_user_permissions()`.
4.  **Filtering**: Use a `get_filtered_*_dataframe()` function to get the base data.
5.  **Serialization**: Use `handle_nat_values_for_json()` before converting data to a dictionary.
6.  **Response**: Use `create_kpi_response()` to return data.
7.  **Docstring**: Add a clear docstring to your endpoint.

---

## DataFrame Generation (`utils/dataframe*.py`)

- **Decorator**: Must use `@with_session()`.
- **Parameters**: Must accept `db` as the first argument.
- **Return**: Must return a pandas DataFrame.
- **Logic**: Should contain the base query and initial data shaping. Date filters can be passed here.

```python
# In utils/dataframeEncounterFiles.py
@with_session()
def generate_encounter_upload_metrics_df(db, start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    # ... query and DataFrame creation logic ...
    return pd.DataFrame(data)
```

## Filtering and Security

- The `get_filtered_*_dataframe()` function is the single source of truth for applying filters.
- It first applies **user permission-based filtering** (`lab_unit_id`). This is non-negotiable and applies to all users, including admins.
- It then applies any request-based filters from `parse_filter_params()`.