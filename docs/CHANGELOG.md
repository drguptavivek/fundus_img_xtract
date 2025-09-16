
# CHANGELOG

## 16 Sept 2025: Enhanced Grading Security and Simplified Slot Selection

- Modified `dual_grading_task` function to make `slot_type` a mandatory parameter instead of optional
- Updated route registration to remove `slot_type` from URL path parameters for improved security
- Modified `start_grading` function to call `dual_grading_task` directly with `slot_type` as a function parameter
- Simplified logic in `dual_grading_task` by removing complex slot determination code since slot is now explicitly specified
- Added direct validation of slot availability based on task state
- Improved security by preventing manipulation of slot type through URL parameters

All grading routes now use function parameters for slot specification rather than URL path parameters, enhancing security while maintaining functionality.

## 15 Sept 2025: Disease Specializations Functionality Removed

- Removed all `user_disease_specializations` functionality as it was not used in core workflows
- Deleted files:
  - `admin/disease_specializations.py`
  - `api/disease_specializations.py`
  - `utils/disease_specialzation_utils.py`
- Removed templates:
  - `templates/admin/disease_specializations/` directory
  - `templates/disease_specializations/macros.html`
- Updated models.py to remove `user_disease_specializations` table and relationships
- Removed admin routes and API endpoints for disease specializations
- Removed "Disease Specializations" navigation link from base template
- Updated documentation references in TODO files

The more granular `user_disease_unit_role` system is used for access control in the dual grading workflow.

## 15 Sept 2025: Single Grading Routes and API Endpoints Removed

- Removed single grading routes from the grading blueprint:
  - `/remedio/glaucoma/<uuid>` - Glaucoma grading for Remed.io ZIP files
  - `/remedio/dr/<uuid>` - DR grading for Remed.io ZIP files
  - `/direct/<uuid>` - Glaucoma grading for direct uploads
  - `/direct/disease/<uuid>/<int:disease_id>` - Disease grading for direct uploads
- Removed API endpoints for single grading:
  - `/api/gradings` - API endpoint for fetching gradings
- Removed imports and route registrations in `grading/__init__.py`
- Kept ImageGrading model and core functionality intact for legacy support

Only dual grading routes are now available:
- `/task/<int:task_id>` - Dual grading task
- `/task/submit` - Dual grading submission 

