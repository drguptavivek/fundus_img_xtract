# Grading Eligibility

Base path: `/api`

These routes live in `api/grading_eligibility.py`.

## CSRF

- No CSRF token is required.
- All routes here are `GET` only.

## Auth and Roles

- These routes require `login_required` through `roles_required("admin")`.
- Only `admin` can access them unless the caller is a master admin, which bypasses role checks.
- A role failure returns `403 Forbidden`.
- An unauthenticated session is redirected by Flask-Login to the login flow.

## `GET /grading-eligibility/users/<user_id>`

Path parameter:
- `user_id`: integer user ID

Success response: `200 OK`

```json
{
  "user_id": 123,
  "eligibility": [
    {
      "id": 44,
      "user_id": 123,
      "disease_id": 1,
      "lab_unit_id": 10,
      "can_grade_resident": true,
      "can_grade_resident2": false,
      "can_arbitrate": true,
      "active": true
    }
  ]
}
```

Top-level response keys:
- `user_id`
- `eligibility`

`eligibility` item keys:
- `id`
- `user_id`
- `disease_id`
- `lab_unit_id`
- `can_grade_resident`
- `can_grade_resident2`
- `can_arbitrate`
- `active`

Errors:
- `404` with `{"error":"User not found"}` when the user does not exist

## `GET /grading-eligibility/users/<user_id>/details`

Path parameter:
- `user_id`: integer user ID

Success response: `200 OK`

```json
{
  "user_id": 123,
  "eligibility_details": {
    "10": {
      "lab_unit_name": "Retina Clinic",
      "hospital_name": "Hospital A",
      "diseases": {
        "1": {
          "disease_name": "Diabetic Retinopathy",
          "roles": ["Resident", "Arbitrator"]
        }
      }
    }
  }
}
```

Top-level response keys:
- `user_id`
- `eligibility_details`

`eligibility_details` shape:
- JSON object keyed by lab-unit id
- Each lab-unit object contains `lab_unit_name`, `hospital_name`, and `diseases`

`diseases` shape:
- JSON object keyed by disease id
- Each disease object contains `disease_name` and `roles`

`roles` values:
- `Resident`
- `Resident 2`
- `Arbitrator`

Field notes:
- The nested integer keys become JSON object keys, so they are serialized as strings on the wire.
- Only active eligibility rows with at least one positive role flag are included.

Errors:
- `404` with `{"error":"User not found"}` when the user does not exist
