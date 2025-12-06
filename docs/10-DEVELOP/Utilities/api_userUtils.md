# API User Utilities Documentation

This document provides an overview of the utility functions available in the user API module. These utilities are designed to manage user-related operations such as retrieving eligible lab units.

## API Endpoints

### `GET /eligibleLabUnit`

Retrieves the eligible lab units for the current user or a specified user ID. This endpoint is protected and requires authentication.

**Authentication:** Requires a valid user session (login required)

**Parameters:**
- `user_id` (integer, optional): If provided and the current user has admin role, retrieves eligible lab units for the specified user ID. Otherwise, retrieves eligible lab units for the current user.

**Response:**
```json
{
  "user_id": 1,
  "eligible_lab_units": [
    {
      "id": 1,
      "name": "Lab Unit A",
      "hospital_id": 1,
      "hospital_name": "Main Hospital"
    }
  ]
}
```

**Response Fields:**
- `user_id`: The ID of the user whose eligible lab units are returned
- `eligible_lab_units`: Array of lab units the user has access to, each containing:
  - `id`: The lab unit ID
  - `name`: The lab unit name
  - `hospital_id`: The ID of the associated hospital
  - `hospital_name`: The name of the associated hospital (null if no hospital is associated)

**Authorization:**
- Regular users can only retrieve their own eligible lab units
- Admin users can specify a `user_id` parameter to retrieve eligible lab units for other users

**Implementation Details:**
- Uses `get_user_lab_unit_ids` from `utils.upload_eligibility` to determine which lab units a user has access to
- Performs database queries using the `LabUnit` model to fetch detailed information about the eligible lab units
- Returns results in a structured JSON format suitable for frontend consumption