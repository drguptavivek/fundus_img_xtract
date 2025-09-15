
# CHANGELOG 7 Sep 2025 2020 IST

  Summary of New API Endpoints

  I've successfully added several new useful API endpoints to the API blueprint, organized into modular files:

  1. Hospitals API (api/hospitals.py)

  a. Get All Hospitals
   - Endpoint: GET /api/hospitals
   - Description: Returns a list of all hospitals
   - Access: Admins and data managers only

  b. Get Hospital by ID
   - Endpoint: GET /api/hospitals/<int:hospital_id>
   - Description: Returns details of a specific hospital
   - Access: Admins and data managers only

  c. Get Lab Units for Hospital
   - Endpoint: GET /api/hospitals/<int:hospital_id>/lab-units
   - Description: Returns all lab units associated with a specific hospital
   - Access: Admins and data managers only

  d. Get Specialists for Disease at Hospital
   - Endpoint: GET /api/hospitals/<int:hospital_id>/specializations/<int:disease_id>/users
   - Description: Returns all users specialized in a specific disease at a specific hospital
   - Access: Admins and data managers only

  2. Users API (api/users.py)

  a. Get Lab Units for User
   - Endpoint: GET /api/users/<int:user_id>/lab-units
   - Description: Returns all lab units associated with a specific user
   - Access: Logged-in users (can only access their own data unless admin/data manager)

  b. Get Hospitals for User
   - Endpoint: GET /api/users/<int:user_id>/hospitals
   - Description: Returns all hospitals associated with a specific user (through their lab units)
   - Access: Logged-in users (can only access their own data unless admin/data manager)

  Benefits of These New Endpoints

   1. Better Data Navigation: Users can now navigate the relationships between hospitals, lab units, users, and disease specializations
   2. Enhanced Admin Capabilities: Admins can get detailed information about the organizational structure
   3. Improved User Management: Better understanding of user assignments and specializations
   4. Resource Planning: Hospital administrators can see which specialists are available for specific diseases

  Security Considerations

   - All endpoints follow the principle of least privilege
   - User-specific endpoints check if the requesting user has permission to access the data
   - Admin-only endpoints are properly protected
   - Data managers have appropriate access to organizational data

  Testing Verification

   - All Python files compile without syntax errors
   - The application creates successfully without issues
   - No duplicate endpoint function names
   - All endpoints are accessible at their defined URLs

  These new endpoints significantly enhance the API's capabilities for managing and querying the relationships between the core entities in the
  system.




## 7 Sept 2005 2025 IST
 I've successfully refactored the API routes into modular files, making the codebase more organized and maintainable. Here's what I did:

  1. Created Modular Route Files

  a. api/disease_gradings.py
   - Contains the get_disease_grading endpoint
   - Handles fetching a single disease grading by ID
   - Restricted to admin users only

  b. api/direct_uploads.py
   - Contains three endpoints:
     - get_lab_units - Get lab units for a user
     - get_hospital - Get hospital for a lab unit
     - get_upload_status - Get status of an upload job
   - These endpoints use different authentication requirements:
     - get_lab_units and get_hospital require login
     - get_upload_status requires login

  d. api/jobs.py
   - Contains the get_job_status endpoint
   - Handles fetching job status by token
   - Restricted to admin users only

  2. Updated api/routes.py
   - Simplified the main routes file to only import from the modular files
   - Kept it for backward compatibility and blueprint initialization
   - Removed all the actual route definitions

  3. Benefits of This Refactoring
   - Better Organization: Each API category is in its own file
   - Easier Maintenance: Changes to one API category don't affect others
   - Improved Readability: Each file has a clear, focused purpose
   - Scalability: Adding new endpoints to a category is straightforward
   - Team Development: Multiple developers can work on different API categories simultaneously

  4. Verification
   - All Python files compile without syntax errors
   - The application creates successfully without issues
   - All API endpoints are still accessible at the same URLs:
     - /api/disease-gradings/<int:grading_id>
     - /api/users/<int:user_id>/disease-specializations (GET/POST)
     - /api/users/<int:user_id>/lab-units
     - /api/lab-units/<int:lab_unit_id>/hospital
     - /api/upload-jobs/<int:job_id>/status
     - /api/upload-jobs/<job_token>

  The refactored API blueprint is now much more maintainable and organized while preserving all existing functionality.


## 7 Sept 2005 2010 IST


  Summary of Changes

   1. Created the API Blueprint:
      - Created a new api directory with __init__.py and routes.py files
      - Defined the blueprint with /api URL prefix

   2. Moved All API Routes:
      - Disease Gradings API: Moved from admin/disease_gradings.py to api/routes.py
        - Old endpoint: /admin/disease-gradings/<int:grading_id>/json
        - New endpoint: /api/disease-gradings/<int:grading_id>

      - Disease Specializations API: Moved from admin/disease_specializations.py to api/routes.py
        - Old endpoints: /admin/disease-specializations/api/users/<int:user_id>/diseases (GET/POST)
        - New endpoints: /api/users/<int:user_id>/disease-specializations (GET/POST)

      - Direct Uploads API: Moved from direct_uploads/api.py and direct_uploads/jobs.py to api/routes.py
        - Old endpoints:
          - /direct_uploads/api/lab-units/<int:user_id>
          - /direct_uploads/api/hospital/<int:lab_unit_id>
          - /direct_uploads/api/direct/upload/status/<int:job_id>
        - New endpoints:
          - /api/users/<int:user_id>/lab-units
          - /api/lab-units/<int:lab_unit_id>/hospital
          - /api/upload-jobs/<int:job_id>/status

      - Jobs API: Moved from jobs/routes.py to api/routes.py
        - Old endpoint: /jobs/<job_token>
        - New endpoint: /api/upload-jobs/<job_token>

   3. Updated Application Registration:
      - Added the new API blueprint registration in app.py

   4. Updated Frontend References:
      - Updated the job status template to use the new API endpoint
      - Updated the upload processing template to use the new API endpoint

  All API routes are now consolidated under the /api prefix, making the API more organized and easier to maintain. The application compiles without
  syntax errors, and all references to the old API endpoints have been updated to use the new centralized API blueprint.

    Issue and Fix

  Problem: The application was failing to start with the error "The name 'api' is already registered for this blueprint".

  Root Cause: The API blueprint was being registered twice in app.py:
   1. First registration at lines 212-213
   2. Second registration at lines 285-286

  Solution:
   1. Removed the duplicate registration of the API blueprint
   2. Changed the blueprint name from "api" to "fundus_api" to ensure uniqueness (though this wasn't the main issue)

  Verification:
   - The app now creates successfully without errors
   - All Python files compile without syntax errors





## 7 Sept 2025: 2000 IST
   1. Created a new file admin/disease_specializations.py with all the route handlers from disease_specializations/routes.py
   2. Updated admin/__init__.py to import and register the new route handlers with the admin blueprint
   3. Removed the disease_specializations blueprint registration from app.py
   4. Moved the template files from templates/disease_specializations/ to templates/admin/disease_specializations/
   5. Updated the template files to use the correct URL endpoints for the admin blueprint
   6. Updated the example script to import from the correct location (disease_specialzation_utils instead of the blueprint)
   7. Removed the old disease_specializations blueprint directory
   8. Verified that all Python files compile without syntax errors

  The routes are now accessible under the admin blueprint with the following URLs:
   - /admin/disease-specializations (index)
   - /admin/disease-specializations/manage/<user_id> (manage specializations for a user)
   - /admin/disease-specializations/api/users/<user_id>/diseases (API endpoints)

  All functionality should work exactly as before, but now the routes are properly organized under the admin section of the application.

✦ Let me summarize the changes I've made:

   1. Updated the upload_form function in uploads/routes.py to:
      - Add the selectinload import for efficiently loading related data
      - Use selectinload(LabUnit.hospital) when querying lab units to preload hospital data

   2. Updated the templates/upload/upload_multi.html template to:
      - Replace the select dropdowns with radio buttons for hospital and lab unit selection, matching the direct upload approach
      - Update the JavaScript to filter lab unit buttons based on the selected hospital, similar to the direct upload implementation
      - Initially hide all lab unit buttons until a hospital is selected

  These changes make the hospital and lab unit selection in the /upload_files route consistent with the approach used in the /direct/upload/ route,
  providing a more unified user experience across the application.


refactor the uploads blueprint to use the path /remedio_zip_uploads. Let me create a plan for this refactoring:

 ╰─────────────────────────────────────────────────────────────╯
✦ Let me summarize the changes I've made to refactor the uploads blueprint to /remedio_zip_uploads:

   1. Renamed the directory: Changed uploads to remedio_zip_uploads

   2. Updated the blueprint definition:
      - Changed the blueprint name from "uploads" to "remedio_zip_uploads"
      - Updated the URL prefix from "" to "/remedio_zip_uploads"

   3. Updated imports in app.py:
      - Changed from from uploads import bp as uploads_bp to from remedio_zip_uploads import bp as remedio_zip_uploads_bp
      - Updated the blueprint registration to use the new name

   4. Updated template references:
      - Modified all templates that referenced url_for('uploads.upload_form') to use url_for('remedio_zip_uploads.upload_form')
      - Updated the form action in upload_multi.html to use url_for('remedio_zip_uploads.upload_files')

   5. Updated redirect references in routes.py:
      - Changed all redirect(url_for("uploads.upload_form")) to redirect(url_for("remedio_zip_uploads.upload_form"))

   6. Updated test file:
      - Fixed indentation issues in the test file
      - Updated URL references from /upload_files to /remedio_zip_uploads/upload_files

  The blueprint is now accessible at /remedio_zip_uploads/upload_files instead of the previous /upload_files, and all references throughout the
  application have been updated to use the new blueprint name and URL structure. All Python files compile without syntax errors.

  

## 15 Sept 2025: Single Grading Routes Removed

- Removed single grading routes from the grading blueprint:
  - `/remedio/glaucoma/<uuid>` - Glaucoma grading for Remed.io ZIP files
  - `/remedio/dr/<uuid>` - DR grading for Remed.io ZIP files
  - `/direct/<uuid>` - Glaucoma grading for direct uploads
  - `/direct/disease/<uuid>/<int:disease_id>` - Disease grading for direct uploads
- Removed imports and route registrations in `grading/__init__.py`
- API endpoints for single grading have been removed
- ImageGrading model and dual grading system remain intact

Only dual grading routes are now available:
- `/task/<int:task_id>` - Dual grading task
- `/task/submit` - Dual grading submission

## 15 Sept 2025: Single Grading (ImageGrading) Functionality Removed

- Removed all `ImageGrading` (single grading) functionality as it's not used in core workflows
- Deleted files:
  - `api/gradings.py`
- Updated models.py to remove `ImageGrading` model
- Updated dashboard to remove ImageGrading queries and displays
- Updated documentation references in TODO files

The dual grading system (`Grade` model) is now the only grading system in use.

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

