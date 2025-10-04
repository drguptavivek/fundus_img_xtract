# Analytics Routes Documentation

This document provides an overview of all routes in the analytics blueprint along with their purposes, URL patterns, roles required, and functionality.

## Route Summary

| Route | URL Pattern | Roles Required | Purpose |
|-------|-------------|----------------|---------|
| Image Results | `/analytics/images` | admin, data_manager | Render per-image grading results with filtering and pagination |
| Encounter Results | `/analytics/encounters` | admin, data_manager | Render encounter-level grading summaries |
| Images Without Tasks | `/analytics/images/no-tasks` | admin, data_manager, optometrist | Display images that have no associated grading tasks |
| Search Images | `/analytics/images/search` | admin, data_manager, optometrist | Search for images with comprehensive filters |
| Direct View | `/analytics/direct/view/<uuid_str>` | admin, data_manager, optometrist | View details for a direct image upload |
| Encounter View | `/analytics/encounter/view/<int:encounter_id>` | admin, data_manager | View details for a specific encounter |
| Encounter Results Simple | `/analytics/encounters-simple` | admin, data_manager | Render a simplified encounter list showing only encounters with non-pending tasks |
| Discrepancy Review | `/analytics/discrepancy-review` | admin, data_manager, optometrist | Main page for discrepancy review process |
| Task Details | `/analytics/viewTaskDetails/<int:task_id>` | admin, data_manager, optometrist | View details for a specific grading task |

## Detailed Route Descriptions

### Image Results
- **URL Pattern**: `/analytics/images`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager
- **Purpose**: Renders per-image grading results with filtering and pagination capabilities. Allows filtering by disease, upload type (ZIP or direct), hospital, lab unit, and task state.
- **Query Parameters**:
  - `page`: Page number for pagination
  - `disease_id`: Filter by disease ID
  - `upload_type`: Filter by upload type ('zip' or 'direct')
  - `hospital_id`: Filter by hospital ID
  - `lab_unit_id`: Filter by lab unit ID
  - `task_state`: Filter by task state ('pending', 'resident_done', 'faculty_done', 'arbitration', 'final')

### Encounter Results
- **URL Pattern**: `/analytics/encounters`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager
- **Purpose**: Renders encounter-level grading summaries. Provides an overview of all encounters with their grading status and related information.
- **Query Parameters**:
  - `page`: Page number for pagination
  - `hospital_id`: Filter by hospital ID
  - `lab_unit_id`: Filter by lab unit ID
  - `capture_date`: Filter by capture date

### Images Without Tasks
- **URL Pattern**: `/analytics/images/no-tasks`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Displays images that have no associated grading tasks. Useful for identifying ungraded images.
- **Query Parameters**:
  - `page`: Page number for pagination
  - `type`: Filter by type ('all', 'zip', 'direct')
  - `lab_unit_id`: Filter by lab unit ID

### Search Images
- **URL Pattern**: `/analytics/images/search` (also available at `/analytics/images/search/`)
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Provides comprehensive search functionality for images with various filters including hospital, lab unit, camera, disease, area, and date ranges.
- **Query Parameters**:
  - `page`: Page number for pagination
  - `source`: Filter by source ('all', 'zip', 'direct')
  - `hospital_id`: Filter by hospital ID
  - `lab_unit_id`: Filter by lab unit ID
  - `camera_id`: Filter by camera ID
  - `disease_id`: Filter by disease ID
  - `area_id`: Filter by area ID
  - `is_mydriatic`: Filter by mydriatic status
  - `has_encounter`: Filter by presence of encounter
  - `has_dr_report`: Filter by presence of DR report
  - `has_glaucoma_report`: Filter by presence of glaucoma report
  - `upload_start`: Filter by upload start date
  - `upload_end`: Filter by upload end date
  - `capture_start`: Filter by capture start date
  - `capture_end`: Filter by capture end date

### Direct View
- **URL Pattern**: `/analytics/direct/view/<uuid_str>`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Displays detailed information for a direct image upload, including associated tasks and grading information.
- **Path Parameters**:
  - `uuid_str`: The UUID of the direct image upload to view

### Encounter View
- **URL Pattern**: `/analytics/encounter/view/<int:encounter_id>`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager
- **Purpose**: Displays comprehensive details for a specific encounter, including images, reports, grading tasks, and consensus information.
- **Path Parameters**:
  - `encounter_id`: The ID of the encounter to view

### Encounter Results Simple
- **URL Pattern**: `/analytics/encounters-simple`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager
- **Purpose**: Renders a simplified encounter list showing only encounters with non-pending grading tasks. This provides a quick overview of encounters that have progressed beyond the initial state.

### Discrepancy Review
- **URL Pattern**: `/analytics/discrepancy-review`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Provides the main page for the discrepancy review process, allowing users to identify and review grading tasks where there are discrepancies between different graders.
- **Query Parameters**:
  - `page`: Page number for pagination
  - `disease_id`: Filter by disease ID
  - `lab_unit_id`: Filter by lab unit ID
  - `resident_grade`: Filter by resident's grade
  - `faculty_grade`: Filter by faculty's grade
  - `arbitrator_grade`: Filter by arbitrator's grade
  - `final_grade`: Filter by final grade

### Task Details
- **URL Pattern**: `/analytics/viewTaskDetails/<int:task_id>`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, optometrist
- **Purpose**: Displays detailed information for a specific grading task, including all associated grades, consensus information, and image details.
- **Path Parameters**:
  - `task_id`: The ID of the grading task to view