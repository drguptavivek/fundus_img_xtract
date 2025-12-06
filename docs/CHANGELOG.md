# CHANGELOG

## 10 Nov 2025: Comprehensive Documentation Overhaul

### Complete Documentation System Update
- Created 10 new comprehensive documentation files covering all major application components
- Updated main README.md with links to all new documentation for improved navigation
- Standardized documentation format and structure across all modules
- Emphasized current implementation vs speculative features

### New Comprehensive Documentation Files
1. **Comprehensive ZIP Upload Workflow** (`docs/01-Adding_Images/comprehensive_zip_workflow.md`)
   - Complete ZIP processing pipeline with security validation
   - Background job processing and task creation
   - File organization and duplicate detection
   - Integration with verification and grading systems

2. **Comprehensive Direct Upload Workflow** (`docs/01-Adding_Images/comprehensive_direct_upload_workflow.md`)
   - Individual image upload system with metadata management
   - Image editing and verification workflows
   - User quota and permission management
   - Dashboard and analytics integration

3. **AI Grades Import Workflow** (`docs/01-Adding_Images/comprehensive_ai_grades_import_workflow.md`)
   - Excel file consumption for AI grades (no automated AI grading)
   - Pre-graded image upload and grade import processes
   - AI model metadata tracking and integration
   - Use cases for AI vs human grader comparison

4. **Comprehensive Verification Workflows** (`docs/02-Verify-Anonymize/comprehensive_verification_workflows.md`)
   - DR, Glaucoma, and No-DR verification processes
   - Image anonymization and privacy protection
   - Quality control and data validation
   - Integration with task creation systems

5. **Comprehensive Task Management System** (`docs/03-Tasks/comprehensive_task_management_system.md`)
   - Task creation, assignment, and lifecycle management
   - Dual grading workflow integration
   - Intra-rater reliability assessment system
   - Ad-hoc task creation and management

6. **Comprehensive Dual Grading System** (`docs/04-Grade/comprehensive_dual_grading_system.md`)
   - Three-tier grading workflow (Resident → Resident2 → Arbitrator)
   - Role-based access control and permissions
   - Consensus building and revision system
   - Performance optimization and quality assurance

7. **Comprehensive Analytics & Reporting System** (`docs/11-KPI and DFs/comprehensive_analytics_reporting_system.md`)
   - Materialized views system with 4 specialized views
   - Automated refresh scheduling (4x daily)
   - KPI dashboard and performance metrics
   - Admin interface for view management

### Updated README.md Documentation Links
- Added new section for Analytics & Reporting System
- Updated Data Processing Workflows with comprehensive links
- Enhanced Report Verification Workflows section
- Expanded Task Creation and Grading System sections
- Added comprehensive documentation for all major workflows

### Documentation Quality Improvements
- Current implementation focus - no speculative features
- Clear distinction between actual functionality and planned features
- Comprehensive security and access control documentation
- Complete workflow diagrams and integration points
- Performance optimization and troubleshooting guides

## 27 Oct 2025: Materialized Views and Analytics System Implementation

### Advanced Analytics Platform
- **Materialized Views Implementation**: Created complete analytics ecosystem with 4 specialized views:
  - `mvw_grading_data_all` - General grading data for all diseases
  - `mvw_diabetic_retinopathy_grading_pivot` - DR-specific pivoted analysis
  - `mvw_glaucoma_grading_pivot` - Glaucoma-specific pivoted analysis
  - `mvw_amd_grading_pivot` - AMD-specific pivoted analysis

### Automated Refresh System
- **Scheduler Implementation**: Automated refresh scheduling (4x daily at 07:00, 13:30, 19:00, 01:30 IST)
- **Performance Optimization**: 25+ indexes per view with GIN indexing for JSON feature data
- **Admin Interface**: Complete admin interface for manual refresh and status monitoring
- **Refresh History**: Comprehensive logging of all refresh operations with performance metrics

### Analytics Integration
- **Real-time Updates**: Automatic materialized view population from grading activities
- **KPI Dashboards**: Advanced analytics dashboards with filtering and export capabilities
- **Query Performance**: Optimized for fast analytics queries with comprehensive indexing
- **Data Integrity**: Historical preservation with denormalized fields for audit trails

## 5 Oct 2025: Tasks Module Implementation

### New Tasks Module
- **Comprehensive Tasks System**: Implemented complete tasks module with separate templates and routes
- **Personalized Task Management**: Added `tasks/my_tasks` route for individual task management
- **Lab Unit Association Scoping**: Applied proper Lab Unit Association scoping across all task functionality
- **Task Workflow Integration**: Seamless integration with dual grading and analytics systems

### Analytics Refactoring
- **Blueprint Migration**: Refactored results blueprint to analytics blueprint
- **Enhanced Scoping**: Updated all analytics routes to implement proper Lab Unit Association scoping
- **Discrepancy Review**: Enhanced discrepancy review system with improved filtering and analysis
- **Encounter Results**: Implemented encounter-wise results for all associated images

### Search and Discovery
- **PhotoSwipe Integration**: Implemented gallery functionality for search results
- **Enhanced Filtering**: Added comprehensive LabUnit filtering to image search endpoints
- **Performance Optimization**: Fixed pagination issues and improved search results display
- **Utility Refactoring**: Complete recreation of image search utilities with comprehensive features

## 30 Sept 2025: Dual Grading System and Task Management

### Dual Grading Workflow Fixes
- **Task State Management**: Fixed dual grading workflow with proper task state updates and transitions
- **Stuck Task Cleanup**: Implemented automatic cleanup mechanism (60-minute timeout) for stuck tasks
- **TaskTracker Integration**: Added TaskTracker cleanup after successful grade submissions
- **Faculty Task Availability**: Fixed resident2 task availability issues through proper state management

### Performance and Usability
- **Timezone Support**: Rolled out end-to-end support for per-user display timezones with dynamic zoneinfo catalog
- **Dark Mode Implementation**: Implemented dark mode as default for grading pages with contrast fixes
- **Session Management**: Enhanced session security with database-backed session storage and cleanup
- **Email System**: Fixed email sending functionality with comprehensive logging for debugging

### Database and Transaction Management
- **Transaction Infrastructure**: Created comprehensive transaction management system with context managers
- **Data Integrity**: Enhanced error handling and rollback mechanisms for dual grading operations
- **Audit Trail**: Implemented comprehensive logging and audit trail for all grading activities
- **Performance Optimization**: Standardized database session management across utility functions

## 18 Sept 2025: Code Organization and Cleanup

### Module Reorganization
- **Utility Restructuring**: Renamed and organized utility modules for better clarity and maintainability
- **Function Organization**: Moved grading functions to gradeUtils.py and KPI functions to dualGradingKPIs.py
- **Code Cleanup**: Removed empty and unused modules to reduce code clutter and improve maintainability
- **API Standardization**: Cleaned up API endpoints and removed redundant code while standardizing database sessions

### Enhancement Features
- **Time Tracking**: Implemented comprehensive time tracking for grading activities with performance metrics
- **Dashboard Improvements**: Enhanced grading dashboard with mobile responsiveness and better UX
- **Error Handling**: Implemented global stack trace handler for comprehensive error capture and logging
- **Security Hardening**: Added CSRF protection, input validation, and comprehensive security measures

## 15 Sept 2025: Feature Removal and System Simplification

### Disease Specializations Removal
- **Functionality Cleanup**: Removed unused user_disease_specializations functionality as it was not used in core workflows
- **Database Cleanup**: Removed related database tables, relationships, and admin interfaces
- **Template Updates**: Removed navigation links and updated all template references
- **Documentation**: Updated documentation to reflect removal and migration to user_disease_unit_role system

### Single Grading Routes Removal
- **Legacy Route Removal**: Removed all single grading routes from the grading blueprint
- **API Cleanup**: Removed API endpoints for single grading while maintaining ImageGrading model for legacy support
- **Dual Grading Focus**: Streamlined system to focus exclusively on dual grading workflows
- **Template Simplification**: Removed legacy templates and navigation elements

## 8 Nov 2025: Deployment Infrastructure and System Optimization

### Docker-Based Deployment System
- **Containerized Environment**: Implemented comprehensive Docker-based deployment with production, development, and local development models
- **Multi-Environment Support**: Created separate configurations for production (Gunicorn) and development environments
- **Service Orchestration**: Enhanced Docker Compose configuration for seamless service management
- **Port Configuration**: Updated application to bind to 0.0.0.0 instead of 127.0.0.1 for broader accessibility

### Database Context Manager Standardization
- **Transaction Management**: Comprehensive implementation of database context manager across the application
- **File Updates**: Updated 20+ files including analytics routes, API endpoints, direct uploads, and utility modules
- **Testing Framework**: Created comprehensive test suite with 621 test cases covering all routes and functionality
- **Performance Optimization**: Standardized database session management for improved performance and reliability

### Proxy and Network Configuration
- **NGINX Proxy Support**: Enhanced application to work seamlessly behind NGINX proxy managers
- **Header Handling**: Implemented duplicate date header prevention for proxy configurations
- **Network Binding**: Updated application binding strategy for production deployment compatibility

## 7 Nov 2025: Advanced Intra-Rater and File Management Systems

### Intra-Rater Quality Assurance
- **Service Implementation**: Introduced comprehensive intra-rater service with cooldown handling and abnormal-first prioritization
- **Batch Management**: Created sophisticated batch creation system with duplicate prevention and JSON audit snapshots
- **Database Enhancement**: Extended SQLite migration to support normal_grade_id with proper seeding
- **Quality Metrics**: Implemented comprehensive quality assurance metrics and reporting for grader consistency

### File Management and Cleanup
- **Duplicate Detection**: Enhanced file upload system with improved duplicate detection and handling
- **Storage Optimization**: Implemented automated cleanup of processed ZIP files and duplicate uploads
- **File Integrity**: Added comprehensive file integrity checks with hash-based validation
- **Storage Management**: Optimized file storage organization and retrieval systems

## 14 Oct 2025: Documentation Updates

### Complete Documentation System Update
- Created 10 new comprehensive documentation files covering all major application components
- Updated main README.md with links to all new documentation for improved navigation
- Standardized documentation format and structure across all modules
- Emphasized current implementation vs speculative features

### New Comprehensive Documentation Files
1. **Comprehensive ZIP Upload Workflow** (`docs/01-Adding_Images/comprehensive_zip_workflow.md`)
   - Complete ZIP processing pipeline with security validation
   - Background job processing and task creation
   - File organization and duplicate detection
   - Integration with verification and grading systems

2. **Comprehensive Direct Upload Workflow** (`docs/01-Adding_Images/comprehensive_direct_upload_workflow.md`)
   - Individual image upload system with metadata management
   - Image editing and verification workflows
   - User quota and permission management
   - Dashboard and analytics integration

3. **AI Grades Import Workflow** (`docs/01-Adding_Images/comprehensive_ai_grades_import_workflow.md`)
   - Excel file consumption for AI grades (no automated AI grading)
   - Pre-graded image upload and grade import processes
   - AI model metadata tracking and integration
   - Use cases for AI vs human grader comparison

4. **Comprehensive Verification Workflows** (`docs/02-Verify-Anonymize/comprehensive_verification_workflows.md`)
   - DR, Glaucoma, and No-DR verification processes
   - Image anonymization and privacy protection
   - Quality control and data validation
   - Integration with task creation systems

5. **Comprehensive Task Management System** (`docs/03-Tasks/comprehensive_task_management_system.md`)
   - Task creation, assignment, and lifecycle management
   - Dual grading workflow integration
   - Intra-rater reliability assessment system
   - Ad-hoc task creation and management

6. **Comprehensive Dual Grading System** (`docs/04-Grade/comprehensive_dual_grading_system.md`)
   - Three-tier grading workflow (Resident → Resident2 → Arbitrator)
   - Role-based access control and permissions
   - Consensus building and revision system
   - Performance optimization and quality assurance

7. **Comprehensive Analytics & Reporting System** (`docs/11-KPI and DFs/comprehensive_analytics_reporting_system.md`)
   - Materialized views system with 4 specialized views
   - Automated refresh scheduling (4x daily)
   - KPI dashboard and performance metrics
   - Admin interface for view management

### Updated README.md Documentation Links
- Added new section for Analytics & Reporting System
- Updated Data Processing Workflows with comprehensive links
- Enhanced Report Verification Workflows section
- Expanded Task Creation and Grading System sections
- Added comprehensive documentation for all major workflows

### Documentation Quality Improvements
- Current implementation focus - no speculative features
- Clear distinction between actual functionality and planned features
- Comprehensive security and access control documentation
- Complete workflow diagrams and integration points
- Performance optimization and troubleshooting guides

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
- Fixed resident2 task availability issues

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
