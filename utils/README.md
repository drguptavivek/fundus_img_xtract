# Utility Modules

This directory contains utility functions used throughout the application.

## Available Modules

### dualGradingUtils.py
Utility functions specifically for dual grading operations:
- Functions for calculating pending tasks across all eligible lab units for a disease (with special handling for admin users)
- Functions for calculating pending tasks for specific lab unit and disease combinations
- Functions for checking user eligibility for tasks
- Functions for finding next eligible tasks

### masterUtils.py
Master utility functions for retrieving core entities:
- `get_all_diseases()` - Get all diseases
- `get_disease_gradings(disease_id)` - Get gradings for a specific disease
- `get_all_hospitals()` - Get all hospitals
- `get_all_lab_units()` - Get all lab units
- `get_hosp_lab_units(hospital_id)` - Get lab units for a specific hospital
- `get_all_areas()` - Get all areas
- `get_all_cameras()` - Get all cameras

### userGradingsDone.py
Utility functions for retrieving paginated list of gradings done by a user:
- `get_user_gradings()` - Returns paginated gradings for a user
- `get_user_gradings_with_details()` - Returns paginated gradings with additional details

## Testing

Each utility module has a corresponding test file:
- `test_dualGradingUtils.py`
- `test_masterUtils.py`
- `test_userGradingsDone.py`