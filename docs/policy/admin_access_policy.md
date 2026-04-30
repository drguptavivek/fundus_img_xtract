# Admin Access Policy

This policy defines how admin access is split between `admin` and `local_admin`.

## 1. Core rule

- `admin` has cross-hospital access.
- `local_admin` is scoped to their own hospital and the lab units assigned within that hospital.
- If a user has both roles, `admin` wins.
- `master-admin` is not a bypass role and does not grant automatic access beyond explicit roles.

## 2. Hospital scope

- `admin` may view and manage users, jobs, and configuration across all hospitals.
- `local_admin` may only view and manage records in their own hospital.
- Routes that load hospital-scoped data must not key off `hospital_id` alone.
- Shared helpers should check explicit roles before applying hospital filters.

## 3. Lab-unit scope

- `admin` may access all lab units relevant to the page or workflow.
- `local_admin` may access lab units in their hospital only.
- Page-specific lab-unit lists should use shared scoping helpers rather than ad hoc filters.

## 4. UI expectations

- `admin` screens should not hide cross-hospital data just because the account has a hospital assignment.
- `local_admin` screens may show only the hospital-local subset of users, jobs, and selectors.
- When a page offers a hospital or lab-unit selector, the selector should reflect the user's scope.

## 5. Implementation rules

- Prefer shared helpers for scoping decisions.
- Do not use `current_user.hospital_id` by itself as an authorization rule.
- Explicit role checks must decide whether the user is `admin` or `local_admin`.
- Legacy `master-admin` checks should not bypass role enforcement.

## 6. Related code

- [`utils/hospital_scoping.py`](/home/eyeimg/fundus_img_xtract/utils/hospital_scoping.py)
- [`admin/users.py`](/home/eyeimg/fundus_img_xtract/admin/users.py)
- [`admin/image_metadata.py`](/home/eyeimg/fundus_img_xtract/admin/image_metadata.py)
- [`admin/task_backfill.py`](/home/eyeimg/fundus_img_xtract/admin/task_backfill.py)
- [`admin/s3_config.py`](/home/eyeimg/fundus_img_xtract/admin/s3_config.py)
- [`api/userUtils.py`](/home/eyeimg/fundus_img_xtract/api/userUtils.py)
- [`api/scoping.py`](/home/eyeimg/fundus_img_xtract/api/scoping.py)
