# Grading Eligibility API

These endpoints expose the per-user grading eligibility matrix used by admin screens and grading helpers.

Auth and CSRF:

- Both routes use session auth plus the `admin` role.
- Both routes are `GET`, so no CSRF token is required.

## Routes

| Route | Method | Auth | Response | Status codes |
| --- | --- | --- | --- | --- |
| `/api/grading-eligibility/users/<int:user_id>` | `GET` | Session + login + `admin` | `{ "user_id": int, "eligibility": [{"id": int, "user_id": int, "disease_id": int, "lab_unit_id": int, "can_grade_resident": bool, "can_grade_resident2": bool, "can_arbitrate": bool, "active": bool}] }` | `404` if the user is missing. `403` on role failure. |
| `/api/grading-eligibility/users/<int:user_id>/details` | `GET` | Session + login + `admin` | `{ "user_id": int, "eligibility_details": { "<lab_unit_id>": {"lab_unit_name": str, "hospital_name": str, "diseases": { "<disease_id>": {"disease_name": str, "roles": [str, ...] }}}}}` | `404` if the user is missing. `403` on role failure. |

## `GET /api/grading-eligibility/users/<int:user_id>`

Returns the raw `UserDiseaseUnitRole` rows for the user.

Example:

```json
{
  "user_id": 12,
  "eligibility": [
    {
      "id": 1,
      "user_id": 12,
      "disease_id": 3,
      "lab_unit_id": 10,
      "can_grade_resident": true,
      "can_grade_resident2": false,
      "can_arbitrate": false,
      "active": true
    }
  ]
}
```

## `GET /api/grading-eligibility/users/<int:user_id>/details`

The route keeps only active rows and only rows where at least one of the three role flags is true.

Role labels are emitted exactly as:

- `Resident`
- `Resident 2`
- `Arbitrator`

Example:

```json
{
  "user_id": 12,
  "eligibility_details": {
    "10": {
      "lab_unit_name": "Retina Clinic",
      "hospital_name": "City Eye Hospital",
      "diseases": {
        "3": {
          "disease_name": "Diabetic Retinopathy",
          "roles": ["Resident", "Arbitrator"]
        }
      }
    }
  }
}
```
