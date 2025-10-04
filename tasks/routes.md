# Tasks Routes Documentation

This document provides an overview of all routes in the tasks blueprint along with their purposes, URL patterns, roles required, functionality, and data scoping information.

## Access Control and Data Scoping

Access to tasks routes is controlled based on user roles and lab unit associations:
- **Admins** have unrestricted access to all tasks
- **Data managers** have access to tasks scoped to their associated lab units
- **Ophthalmologists** have access to tasks based on their associated lab units
- **Optometrists** have access to tasks assigned to their associated lab units
- All access is restricted based on lab unit associations, meaning users can only view tasks related to the lab units they are associated with

## Route Summary

| Route | URL Pattern | Roles Required | Purpose |
|-------|-------------|----------------|---------|
| Tasks Index | `/tasks/` | admin, data_manager, ophthalmologist, optometrist | Main tasks page |
| My Tasks | `/tasks/my-tasks` | admin, data_manager, ophthalmologist, optometrist | View and manage user's assigned tasks |
| Pending Tasks | `/tasks/pending` | admin, data_manager, ophthalmologist, optometrist | View pending tasks in user's lab units |

## Detailed Route Descriptions

### Tasks Index
- **URL Pattern**: `/tasks/`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, ophthalmologist, optometrist
- **Data Scoping**: Access is restricted to tasks belonging to the user's associated lab units.
- **Purpose**: Provides the main tasks page where users can navigate to different task management features.
- **Template**: `templates/tasks/index.html`
- **Context Variables**:
  - `user_lab_unit_ids`: A set of lab unit IDs the user has access to

### My Tasks
- **URL Pattern**: `/tasks/my-tasks`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, ophthalmologist, optometrist
- **Data Scoping**: Access is restricted to tasks assigned to the user and belonging to their associated lab units.
- **Purpose**: Displays tasks specifically assigned to the current user. This page allows users to see and work on tasks that have been allocated to them.
- **Template**: `templates/tasks/my_tasks.html`
- **Context Variables**:
  - `user_lab_unit_ids`: A set of lab unit IDs the user has access to

### Pending Tasks
- **URL Pattern**: `/tasks/pending`
- **HTTP Methods**: GET
- **Roles Required**: admin, data_manager, ophthalmologist, optometrist
- **Data Scoping**: Access is restricted to pending tasks belonging to the user's associated lab units.
- **Purpose**: Displays pending tasks within the lab units the user has access to. This provides an overview of tasks that need to be processed in the user's assigned lab units.
- **Template**: `templates/tasks/pending.html`
- **Context Variables**:
  - `user_lab_unit_ids`: A set of lab unit IDs the user has access to