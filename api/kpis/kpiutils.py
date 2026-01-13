# api/kpis/kpiutils.py
"""
Common utility functions for KPI API development.

This module provides reusable functions for parameter parsing, response formatting,
and common patterns used across all KPI endpoints.
"""

import json
import numpy as np
import pandas as pd
import logging
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Set, Tuple
from flask import jsonify, request
from flask_login import current_user
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.log_sanitize import sanitize_log_value


def create_kpi_response(data: Dict, message: str = "Data retrieved successfully", filters_applied: Dict = None) -> Dict:
    """
    Create standardized KPI API response.
    
    Args:
        data: Dictionary containing the KPI data
        message: Success message
        filters_applied: Dictionary of filters that were applied
        
    Returns:
        Standardized response dictionary
    """
    response = {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if filters_applied:
        response["filters_applied"] = filters_applied
        
    return response


def create_error_response(error: str, message: str, status_code: int = 400) -> tuple:
    """
    Create standardized error response.
    
    Args:
        error: Error type/category
        message: Detailed error message
        status_code: HTTP status code
        
    Returns:
        Tuple of (jsonified_response, status_code)
    """
    return jsonify({
        "success": False,
        "error": error,
        "message": message
    }), status_code


def create_combined_response(kpi_data: Dict, message: str = "Combined KPI data retrieved successfully") -> Dict:
    """
    Create standardized combined response for multiple KPI data sources.
    
    Args:
        kpi_data: Dictionary containing data from multiple KPI endpoints
        message: Success message
        
    Returns:
        Standardized response with combined data
    """
    return {
        "success": True,
        "data": kpi_data,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def parse_filter_params() -> Dict:
    """
    Parse and validate common filter parameters from request.
    
    Supports:
    - Date filters: start_date, end_date (YYYY-MM-DD format)
    - Location filters: hospital_ids, lab_unit_ids (comma-separated integers)
    
    Returns:
        Dictionary containing parsed and validated parameters
        
    Raises:
        ValueError: If parameter validation fails
    """
    params = {}
    
    try:
        # Log raw request args for debugging
        param_logger = logging.getLogger('runtime_error')
        param_logger.info(
            "Raw request args: %s",
            sanitize_log_value(dict(request.args)),
        )
        
        # Date filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date:
            try:
                params['start_date'] = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("Invalid start_date format. Use YYYY-MM-DD")
        
        if end_date:
            try:
                params['end_date'] = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("Invalid end_date format. Use YYYY-MM-DD")
        
        if start_date and end_date and params['start_date'] > params['end_date']:
            raise ValueError("start_date must be before end_date")
        
        # Location filters - support multiple IDs
        hospital_ids = request.args.get('hospital_ids')
        if hospital_ids:
            try:
                params['hospital_ids'] = [int(id.strip()) for id in hospital_ids.split(',') if id.strip()]
            except ValueError:
                raise ValueError("Invalid hospital_ids format. Use comma-separated integers")
        
        lab_unit_ids = request.args.get('lab_unit_ids')
        if lab_unit_ids:
            try:
                params['lab_unit_ids'] = [int(id.strip()) for id in lab_unit_ids.split(',') if id.strip()]
            except ValueError:
                raise ValueError("Invalid lab_unit_ids format. Use comma-separated integers")
        
        # Log successful parameter parsing
        param_logger = logging.getLogger('runtime_error')
        param_logger.info(
            "Successfully parsed filter params: %s",
            sanitize_log_value(params),
        )
        
        return params
        
    except Exception as e:
        # Log parameter parsing errors
        param_logger = logging.getLogger('runtime_error')
        param_logger.error(
            "Error parsing filter params: %s",
            sanitize_log_value(e),
        )
        param_logger.error(
            "Raw request args: %s",
            sanitize_log_value(dict(request.args)),
        )
        raise


def get_user_permissions(user_id: int) -> Set[int]:
    """
    Get user lab unit permissions without admin override.
    
    This function uses get_user_lab_unit_ids_no_admin_override to ensure
    that all users (including admins) are scoped by their lab unit eligibility.
    This maintains consistent data access patterns across KPI endpoints.
    
    Args:
        user_id: User ID to get permissions for
        
    Returns:
        Set of lab unit IDs user has access to (no admin override)
    """
    try:
        from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
        return get_user_lab_unit_ids_no_admin_override(user_id)
    except Exception as e:
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error getting user permissions for user %s: %s",
            sanitize_log_value(user_id),
            sanitize_log_value(e),
        )
        return set()


def determine_period(params: Dict) -> str:
    """
    Determine period description from filter parameters.
    
    Args:
        params: Dictionary containing filter parameters
        
    Returns:
        String description of the period
    """
    if 'start_date' in params and 'end_date' in params:
        return f"{params['start_date']} to {params['end_date']}"
    elif 'start_date' in params:
        return f"From {params['start_date']}"
    elif 'end_date' in params:
        return f"Until {params['end_date']}"
    else:
        return "All time"


def create_filters_applied_dict(params: Dict, user_lab_unit_ids: Set[int]) -> Dict:
    """
    Create standardized filters_applied dictionary.
    
    Args:
        params: Dictionary containing filter parameters
        user_lab_unit_ids: Set of lab unit IDs user has access to
        
    Returns:
        Dictionary with applied filters information
    """
    return {
        "start_date": params.get('start_date'),
        "end_date": params.get('end_date'),
        "hospital_ids": params.get('hospital_ids'),
        "lab_unit_ids": params.get('lab_unit_ids'),
        "user_lab_unit_ids": list(user_lab_unit_ids)
    }


def validate_dataframe_not_empty(df: pd.DataFrame, endpoint_name: str) -> bool:
    """
    Validate that DataFrame is not empty and log if it is.
    
    Args:
        df: DataFrame to validate
        endpoint_name: Name of the endpoint for logging
        
    Returns:
        True if DataFrame is not empty, False otherwise
    """
    if len(df) == 0:
        logger = logging.getLogger('runtime_error')
        logger.warning(
            "Empty DataFrame returned for %s",
            sanitize_log_value(endpoint_name),
        )
        return False
    return True


def safe_divide(numerator: float, denominator: float, default_value: float = 0.0) -> float:
    """
    Safely divide two numbers, returning default_value if denominator is zero.
    
    Args:
        numerator: Numerator
        denominator: Denominator
        default_value: Value to return if denominator is zero
        
    Returns:
        Result of division or default_value
    """
    try:
        return numerator / denominator if denominator != 0 else default_value
    except Exception:
        return default_value


def calculate_percentage(count: int, total: int, decimal_places: int = 1) -> float:
    """
    Calculate percentage safely.
    
    Args:
        count: Count for percentage calculation
        total: Total count
        decimal_places: Number of decimal places to round to
        
    Returns:
        Percentage value (0-100)
    """
    if total == 0:
        return 0.0
    return round((count / total) * 100, decimal_places)


def group_by_location(df: pd.DataFrame, group_columns: List[str], agg_columns: Dict[str, str]) -> pd.DataFrame:
    """
    Group DataFrame by location columns with specified aggregations.
    
    Args:
        df: DataFrame to group
        group_columns: List of columns to group by
        agg_columns: Dictionary of column names and aggregation functions
        
    Returns:
        Grouped DataFrame with aggregations applied
    """
    try:
        grouped = df.groupby(group_columns).agg(agg_columns).reset_index()
        return grouped
    except Exception as e:
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error in group_by_location: %s",
            sanitize_log_value(e),
        )
        return pd.DataFrame()


def format_month_name(month: int) -> str:
    """
    Convert month number to month name.
    
    Args:
        month: Month number (1-12)
        
    Returns:
        Month name or "Unknown" if invalid
    """
    month_names = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    return month_names[month] if 1 <= month <= 12 else "Unknown"


def log_endpoint_usage(endpoint_name: str, record_count: int, user_id: int = None):
    """
    Log endpoint usage for monitoring and debugging.
    
    Args:
        endpoint_name: Name of the endpoint
        record_count: Number of records processed
        user_id: Optional user ID for tracking
    """
    logger = logging.getLogger('runtime_error')
    user_info = f" for user {user_id}" if user_id else ""
    logger.info(
        "Endpoint %s%s: processed %s records",
        sanitize_log_value(endpoint_name),
        sanitize_log_value(user_info),
        sanitize_log_value(record_count),
    )


def handle_common_exceptions(func):
    """
    Decorator to handle common exceptions in KPI endpoints.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with exception handling
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            return create_error_response("Invalid parameters", str(e))
        except Exception as e:
            error_logger = logging.getLogger('runtime_error')
            error_logger.error(
                "Unexpected error in %s: %s",
                sanitize_log_value(func.__name__),
                sanitize_log_value(e),
            )
            return create_error_response("Internal server error", "An internal error occurred", 500)
    
    return wrapper


# Common aggregation patterns for pandas operations
COMMON_AGGREGATIONS = {
    'count': 'size',
    'nunique': 'nunique',
    'sum': 'sum',
    'mean': 'mean',
    'median': 'median',
    'min': 'min',
    'max': 'max'
}



def handle_nat_values_for_json(df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle NaT (Not a Time) and NaN values in DataFrame to prevent JSON serialization errors.
    
    Args:
        df: pandas DataFrame that may contain NaT/NaN values
        
    Returns:
        DataFrame with NaT/NaN values replaced with None and datetimes properly formatted
    """
    if len(df) == 0:
        return df
    
    # Create a copy to avoid modifying the original
    df_clean = df.copy()
    
    # Handle all columns comprehensively
    try:
        for col in df_clean.columns:
            # Check if column contains datetime data
            if hasattr(pd.api.types, 'is_datetime64_any_dtype') and pd.api.types.is_datetime64_any_dtype(df_clean[col]):
                # Convert to ISO format strings and replace NaT with None
                df_clean[col] = df_clean[col].apply(
                    lambda x: x.isoformat() if pd.notna(x) else None
                )
            else:
                # For all other columns, replace NaN/NaT with None
                # First, convert to object type to handle mixed types properly
                df_clean[col] = df_clean[col].astype('object')
                
                # Replace all NaN values (including float NaN, np.nan, etc.) with None
                def clean_value(x):
                    # Check for empty lists/arrays first (before pd.isna which can cause the error)
                    if isinstance(x, (list, np.ndarray)):
                        if hasattr(x, '__len__') and len(x) == 0:
                            return None
                        elif hasattr(x, 'size') and x.size == 0:
                            return None
                    # Check for NaN/NaT values
                    try:
                        if pd.isna(x):
                            return None
                    except (ValueError, TypeError):
                        # pd.isna() can fail on certain types
                        pass
                    # Check for float NaN
                    if isinstance(x, float) and (x != x):
                        return None
                    # Check for np.nan in int columns
                    if isinstance(x, (int, np.integer)):
                        try:
                            if pd.isna(x):
                                return None
                        except (ValueError, TypeError):
                            pass
                    return x
                
                df_clean[col] = df_clean[col].apply(clean_value)
    except Exception as e:
        error_logger = logging.getLogger('runtime_error')
        error_logger.error(
            "Error in handle_nat_values_for_json: %s",
            sanitize_log_value(e),
        )
        error_logger.error(
            "DataFrame shape: %s",
            sanitize_log_value(df.shape),
        )
        error_logger.error(
            "DataFrame columns: %s",
            sanitize_log_value(list(df.columns)),
        )
        raise
    
    return df_clean
