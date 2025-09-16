# Grading Routes Documentation

The Grading module in the Fundus Image Manager application provides a comprehensive system for clinical image grading with robust access controls to ensure data privacy and security.

## Overview

The grading system allows authorized medical professionals to assess fundus images for various conditions including Glaucoma and Diabetic Retinopathy. The system implements masked grading to prevent bias and maintains detailed audit trails of all grading activities.

## Route Structure

The grading routes are organized under the `/grading` prefix:

```
/grading/                          # Dashboard and statistics
2/grading/task/<int:task_id>        # Dual grading task interface
```

## Access Controls

### Role-Based Access Control (RBAC)

The grading system implements strict role-based access controls:

#### Authorized Roles:
1. **admin** - Full access to all grading features
2. **ophthalmologist** - Can grade all types of images
3. **optometrist** - Can grade remedio camera images only
4. **resident** - Can perform initial grading tasks

### Route-Specific Access Controls

#### Dashboard (`/grading/`)
```python
@roles_required("admin", "optometrist", "ophthalmologist", "resident")
```
Accessible by all authorized medical professionals.

#### Dual Grading Task (`/grading/task/<int:task_id>`)
```python
@roles_required("admin", "ophthalmologist", "resident")
```
Accessible by admins, ophthalmologists, and residents based on their assigned roles in the dual grading workflow.

### Task-Based Access Control

The dual grading system implements additional access controls based on the specific task:

```python
# Check if user is eligible for this task based on their role
if not is_user_eligible_for_task(current_user, task):
    abort(403)  # Forbidden
```

This ensures that users can only access tasks that are assigned to their role in the dual grading workflow.

## Grading Workflow

### 1. Dashboard Access
Users start at the grading dashboard which provides:
- Overall statistics on grading activities
- Quick access to pending tasks based on user role
- Personal grading history
- Navigation to specific task types

### 2. Task Selection
Users can either:
- View pending tasks in their dashboard
- Access a specific task directly via its ID
- Browse their previous gradings

### 3. Grading Interface
The grading interface provides:
- Full-screen image viewer with zoom and pan capabilities
- Brightness and contrast controls
- Color filters for enhanced visualization
- Impression selection from predefined clinical categories
- Optional remarks field for additional notes

### 4. Saving Grades
Grades are saved using an "upsert" approach:
- If the user has previously graded the same task, the existing grade is updated
- If this is a new grade, a new record is created
- Each user can have only one grade per task per role

## Security Features

### 1. Masked Grading
- Patient identifying information is hidden during grading
- Graders cannot see grades from other users
- Images are presented without patient context

### 2. Audit Trail
- All grading activities are logged with timestamps
- User identity, role, and actions are recorded
- Changes to grades are tracked with version history

### 3. Data Integrity
- CSRF protection on all grading forms
- Input validation on all grade submissions
- Database constraints to prevent duplicate gradings

## Error Handling

### 403 Forbidden
Returned when:
- User attempts to access a route without proper roles
- User attempts to access a task they're not eligible for
- User attempts to grade an image type they're not authorized for

### 404 Not Found
Returned when:
- Invalid task ID is provided
- Task no longer exists in the system

## API Endpoints

### GET `/grading/`
Displays the grading dashboard with statistics and quick access options.

### GET `/grading/task/<int:task_id>`
Displays the dual grading interface for a specific task.

### POST `/grading/task/submit`
Saves a grade for a dual grading task.

## Best Practices

### For Developers
1. Always use the `@roles_required` decorator for grading routes
2. Implement task-based access control for grading tasks
3. Validate all user inputs and task IDs
4. Use the upsert pattern for saving grades
5. Ensure proper error handling and user feedback

### For Administrators
1. Assign appropriate roles to users based on their responsibilities
2. Regularly review grading activities and access logs
3. Monitor for unauthorized access attempts