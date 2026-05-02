# Scoping APIs

These endpoints expose hospital and lab-unit scope information used by JS clients, mobile clients, and upload flows.

## `GET /api/user/hospital-context`

Returns the current user’s hospital scoping context.

Response fields:
- `user_id`
- `is_master_admin`
- `hospital_id`
- `hospital_name`
- `can_access_multiple_hospitals`

## `GET /api/scoping/operation/<operation_name>`

Returns whether an operation is cross-hospital and whether the UI should show hospital filters.

Path parameter:
- `operation_name` such as `grading`, `upload`, or `analytics`

Response fields:
- `operation`
- `is_cross_hospital`
- `user_is_master_admin`
- `show_hospital_filter`

## `GET /api/eligibleLabUnit`

Returns the current user’s eligible lab units using hospital-aware upload eligibility.

Auth:
- logged-in users with the standard upload-related roles

Response fields:
- `user_id`
- `hospital_id`
- `is_master_admin`
- `eligible_lab_units`

## `GET /api/eligibleLabUnitCurrentUser`

Returns the current user’s eligible lab units and visible hospitals.

Response fields:
- `user_id`
- `hospital_id`
- `is_master_admin`
- `eligible_lab_units`
- `eligible_hospitals`

## Implementation Notes

- These routes are the public read surface for upload eligibility and hospital scoping.
- If upload eligibility logic changes, update `upload_profiles.service` and keep these endpoints as thin wrappers over the shared profile/scoping service.
