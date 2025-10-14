# CHANGELOG

## 14 Oct 2025: Documentation Updates

### API Documentation
- Updated comprehensive API documentation with detailed CSRF protection information
- Added documentation for CSRF handling in routes, Jinja templates, and JavaScript requests
- Enhanced usage examples with proper CSRF token inclusion
- Added error handling patterns for CSRF and authentication failures
- Documented all 14 API endpoints across 7 API modules

### Application Documentation
- Updated `docs/app.md` to reflect current application architecture
- Added documentation for new blueprints including API, notifications, and tasks modules
- Enhanced security features documentation with CSRF protection details
- Added background task management documentation
- Updated CORS configuration and session management details

### Routes Documentation
- Updated `docs/routes.md` with comprehensive API route summary table
- Added all current API endpoints with methods, roles, and purposes
- Properly referenced the updated API documentation

## 13 Oct 2025: Search Functionality Enhancements

### Search Results Improvements
- Implemented PhotoSwipe gallery functionality on search images page
- Fixed pagination issues in search results
- Added SR number (Serial Number) to search results display
- Enhanced search results page with improved UI/UX

### Image Search Utility
- Completely recreated `utils/imageSearchUtil.py` with comprehensive features
- Added LabUnit filtering to `/search_images` endpoint
- Implemented clear filters functionality
- Added comprehensive tests for image search utilities

### API Endpoints
- Added API endpoints for Hospitals and Lab Units
- Implemented Playwright tests for API endpoints (`test_api_hospitals_labunits`)
- Added generic search blank route

## 4 Oct 2025: Tasks Module Implementation

### New Tasks Module
- Implemented comprehensive tasks module with separate templates
- Added `tasks/my_tasks` route for personalized task management
- Created task management interfaces for grading workflows
- Implemented proper Lab Unit Association scoping for tasks

### Analytics Refactoring
- Refactored results blueprint to analytics blueprint
- Updated all analytics routes to implement proper Lab Unit Association scoping
- Added discrepancy review enhancements
- Implemented encounter-wise results for all associated images

### Documentation Updates
- Created comprehensive technical documentation for search functionality
- Updated dual grading documentation and flow diagrams
- Fixed documentation file naming conventions

## 2 Oct 2025: Logging and Audit Enhancements

### Comprehensive Logging System
- Replaced one-off handler wiring with centralized logging setup
- Added rotating file handlers for app, http_error, runtime_error, grades, auth, editing, consensus, and email logs
- Implemented debug mode with debug.log and console output
- Added request-aware filter for HTTP error entries

### Image Editing Audit Trail
- Added per-attribute audit trail for bulk image metadata changes
- Implemented detailed logging in `logs/direct_image_edit.log`
- Added comprehensive audit messages for bulk operations and restores

### Task-Aware Image Editing
- Implemented editing locks for images with active grading tasks
- Added visual alerts and disabled controls when tasks are in progress
- Updated JavaScript editor to honor editing locks

### Dashboard Enhancements
- Enhanced bulk edit functionality with task state validation
- Added detailed summary modal for bulk operations
- Implemented task synchronization during bulk edits
- Added protection against editing images with non-pending tasks

## 1 Oct 2025: Authentication and Session Management

### Database Session Storage
- Implemented server-side session storage in database
- Added session cleanup functionality for ended sessions
- Enhanced session security with proper handling

### Notification System
- Added full support for composing and tracking user-to-user notifications
- Implemented admin broadcasting capabilities
- Added notification relationship to User model

### Lab Unit Association
- Created utility functions for Lab Unit Association
- Applied lab-unit eligibility to upload and verification workflows
- Implemented scoping for non-admin roles based on lab unit associations

### UI/UX Improvements
- Added role-based homepages for Optometrists, Image uploaders, and data managers
- Implemented quick actions on homepage
- Added navigation bar access control based on user roles

## 30 Sept 2025: Dual Grading System Fixes

### Task Management
- Fixed dual grading workflow with proper task state updates
- Implemented stuck task cleanup mechanism (60-minute timeout)
- Added TaskTracker cleanup after successful grade submissions
- Fixed faculty task availability issues

### Timezone Support
- Rolled out end-to-end support for per-user display timezones
- Updated timezone helper to honor .env settings
- Generated timezone options dynamically from Python's zoneinfo catalog

### Theme and UI
- Implemented dark mode as default for grading pages
- Updated theme bootstrapper for grading views
- Fixed contrast issues with outline buttons

### Email and Authentication
- Fixed email sending functionality
- Added email logging for debugging
- Enhanced password reset flow with proper links

## 29 Sept 2025: Error Handling and Data Integrity

### Lookup Deletion Fixes
- Fixed internal server errors when deleting disease IDs with associated gradings
- Added proper error messages for lookup model deletions with related records
- Implemented graceful error handling for hospital, lab unit, and other lookup deletions

### Password Reset Security
- Added PasswordResetAttempt model to track password reset attempts
- Included email, IP address, and timestamp information with appropriate indexes
- Enhanced security for password reset workflow

## 27 Sept 2025: Documentation and Logging

### Documentation Updates
- Added comprehensive logging documentation
- Created dedicated setup_email_logger() function
- Added protection against duplicate log handlers

### Password Reset Flow
- Completed password reset flow implementation
- Added "Forgot Password?" link to login page
- Ensured all pages have proper navigation links

## 18 Sept 2025: Code Organization and Cleanup

### Module Reorganization
- Renamed utility modules for better clarity and organization
- Moved user grading functions to gradeUtils.py
- Moved KPI functions to dualGradingKPIs.py
- Removed empty and unused modules

### API Cleanup
- Cleaned up API endpoints and removed redundant code
- Standardized database session management in utility functions
- Removed unused functions from dualGradingUtils.py

### Grading Enhancements
- Implemented time tracking for grading
- Added grading dashboard improvements
- Enhanced grading card behaviors and mobile responsiveness
- Added non-gradable reasons handling

## 17 Sept 2025: Logging and Error Handling

### Global Stack Trace Handler
- Implemented global stack trace handler for all requests and exceptions
- Added automatic stack trace capture without manual route integration
- Enhanced error reporting and debugging capabilities

### Logging Configuration
- Added authentication and activity logging configuration
- Implemented comprehensive logging system
- Removed markdown JS dependency

### Grade Logging
- Added detailed logging for grades with database record IDs
- Enhanced logging for both new grades and revisions
- Improved audit trail for grading activities

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
