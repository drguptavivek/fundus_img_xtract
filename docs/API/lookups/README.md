# Lookup APIs

These endpoints expose reference data for hospitals, lab units, diseases, grading metadata, and grading eligibility.

## Index

- [Hospitals](hospitals.md)
- [Lab Units](labunits.md)
- [Disease](disease.md)
- [Grading Eligibility](grading-eligibility.md)

## Contract Rules

- All routes in this folder are read-only JSON GET endpoints.
- They use Flask-Login session auth and role checks where defined.
- No CSRF token is required because there are no mutating requests in this surface.
- Some endpoints return raw arrays, while others return wrapper objects with explicit top-level keys.
