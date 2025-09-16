# Dual Grading Implementation - Current Status

## Overview
The dual grading system has been largely implemented with core functionality complete. The system allows for resident/faculty dual grading with arbitration for disagreements, with eligibility controlled per user, disease, and lab unit.

## Completed Components ✅

### 1. Data Models
- `GradingTask`: Core task entity for image×disease grading
- `Grade`: Individual grade attempts with role slots (resident/faculty/arbitrator)
- `Consensus`: Final decision recording (match or adjudication)
- `UserDiseaseUnitRole`: Eligibility matrix for user×disease×lab_unit permissions

### 2. Eligibility Matrix (Admin-Managed)
- CRUD endpoints for `user_disease_unit_role`
- Admin UI for assigning grading permissions per user/disease/lab unit
- Slot flags: `can_grade_resident`, `can_grade_faculty`, `can_arbitrate`

### 3. Task Creation Services
- `create_or_get_task()`: Idempotent task creation with global uniqueness
- `ensure_task()`: UUID-based task creation with verification gating
- Auto-creation hooks in all verification flows (Direct Image, DR, Glaucoma)
- Guardrails: Gold standard protection, cross-lab reassignment blocking

### 4. Grading Flow
- Resident/Faculty submit routes with eligibility enforcement
- Consensus logic: Automatic finalization on match, escalation on mismatch
- Arbitration routes with arbitrator exclusion rules
- State management: pending → resident_done/faculty_done → arbitration → final

### 5. Utility Functions
- User gradings retrieval with pagination
- Dual grading utility functions for pending tasks by role
- Eligibility checking functions
- Next task selection logic

## In Progress Components 🔄

### 1. Dashboard & "Start Grading"
- Improving next-task selection to prioritize cases with other-slot graded
- Enhanced counts and charts showing only verified tasks
- Better queue visibility filtering by eligibility

### 2. Security & Validation
- Adding CSRF protection to all forms
- Implementing strict enum validation
- Ensuring PHI masking in grading routes

### 3. Testing
- Unit tests for eligibility enforcement
- API tests for eligibility CRUD and task management
- Permission validation tests
- Gold standard enforcement tests

### 4. Rollout Preparation
- Feature-flag implementation for new flow
- Admin training documentation
- Legacy `ImageGrading` preservation during transition

## Key Features Implemented

### Verification Gating
- Direct uploads: Require `DirectImageVerify.verified_status = 'verified'`
- Remed.io DR: Require `PatientEncounters.dr_verified_status = 'verified'`
- Remed.io Glaucoma: Require `PatientEncounters.glaucoma_verified_status = 'verified'`

### Eligibility Enforcement
- Resident slot: `user_roles` must include 'resident' + `can_grade_resident = true`
- Faculty/Arbitrator slots: `user_roles` must include 'ophthalmologist' + respective flags
- Arbitrator exclusion: Cannot arbitrate tasks they've already graded as resident/faculty

### Global Uniqueness & Gold Standard
- Exactly one task per image×disease globally (across all lab units)
- `lab_unit_id` scopes assignment/queues only, not identity
- Finalized tasks block cross-lab reassignment with clear error messages

### Consensus Logic
- Match: When resident+faculty labels match → `consensus(method='match')`, state=final
- Mismatch: When labels differ → state=arbitration
- Adjudication: Arbitrator decision → `consensus(method='adjudication')`, state=final

## Next Steps

1. Complete dashboard improvements for better task prioritization
2. Implement comprehensive security measures (CSRF, validation, PHI masking)
3. Develop full test suite for all components
4. Prepare for rollout with feature flags
5. Create admin training materials
6. Implement denormalized view for reporting (optional)

## Status Legend
- ✅ Complete
- 🔄 In progress
- ⏳ Not started