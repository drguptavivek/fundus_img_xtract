# Grading Routes Documentation

The Grading module in the Fundus Image Manager application provides a comprehensive system for clinical image grading with robust access controls to ensure data privacy and security.

## Overview

The grading system allows authorized medical professionals to assess fundus images for various conditions including Glaucoma and Diabetic Retinopathy. The system implements masked grading to prevent bias and maintains detailed audit trails of all grading activities.

## Route Structure

The grading routes are organized under the `/grading` prefix:

```
/grading/                          # Dashboard and statistics
/grading/remedio/glaucoma/image/<uuid>  # Grade Glaucoma images from remedio camera
/grading/remedio/dr/image/<uuid>        # Grade Diabetic Retinopathy images from remedio camera
/grading/direct/glaucoma/<uuid>         # Grade Glaucoma images from direct uploads
/grading/direct/disease/<uuid>/<int:disease_id>  # Grade images for specific diseases from direct uploads
```

## Access Controls

### Role-Based Access Control (RBAC)

The grading system implements strict role-based access controls:

#### Authorized Roles:
1. **admin** - Full access to all grading features
2. **ophthalmologist** - Can grade all types of images
3. **optometrist** - Can grade remedio camera images only

#### Role Restrictions:
- **optometrist** users are restricted from grading direct uploaded images
- **ophthalmologist** users can only grade direct uploaded images from their own LabUnit
- **admin** users have unrestricted access to all grading features

### Route-Specific Access Controls

#### Dashboard (`/grading/`)
```python
@roles_required("admin", "optometrist", "ophthalmologist")
```
Accessible by all authorized medical professionals.

#### Remedio Camera Grading Routes
```python
@roles_required("admin", "optometrist", "ophthalmologist")
```
- `/grading/remedio/glaucoma/image/<uuid>`
- `/grading/remedio/dr/image/<uuid>`

Accessible by all authorized medical professionals.

#### Direct Image Grading Routes
```python
@roles_required("admin", "ophthalmologist")
```
- `/grading/direct/glaucoma/<uuid>`
- `/grading/direct/disease/<uuid>/<int:disease_id>`

Restricted to administrators and ophthalmologists only. Additionally, ophthalmologists can only grade images from their own LabUnit.

### LabUnit-Based Access Control

For direct image uploads, an additional layer of access control is implemented:

```python
# Check access control - consultants can only grade images from their own LabUnit
if not current_user.has_role('admin'):
    # Get user's lab units
    user_lab_unit_ids = [lu.id for lu in current_user.lab_units]
    # Check if image belongs to user's lab unit
    if diu.lab_unit_id not in user_lab_unit_ids:
        abort(403)  # Forbidden
```

This ensures that ophthalmologists can only access and grade images that were uploaded by their own facility.

## Grading Workflow

### 1. Dashboard Access
Users start at the grading dashboard which provides:
- Overall statistics on grading activities
- Quick access to ungraded images
- Personal grading history
- Start grading buttons for different image types

### 2. Image Selection
Users can either:
- Click "Start Grading" to get a random ungraded image
- Enter a specific image UUID to grade a particular image
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
- If the user has previously graded the same image, the existing grade is updated
- If this is a new grade, a new record is created
- Each user can have only one grade per image per condition

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
- Ophthalmologist tries to access an image from another LabUnit
- User attempts to grade an image type they're not authorized for

### 404 Not Found
Returned when:
- Invalid image UUID is provided
- Image no longer exists in the system

## API Endpoints

### GET `/grading/`
Displays the grading dashboard with statistics and quick access options.

### GET `/grading/remedio/glaucoma/image/<uuid>`
Displays the grading interface for a specific Glaucoma image from remedio camera.

### GET `/grading/remedio/dr/image/<uuid>`
Displays the grading interface for a specific Diabetic Retinopathy image from remedio camera.

### GET `/grading/direct/glaucoma/<uuid>`
Displays the grading interface for a specific Glaucoma image from direct uploads (admin/ophthalmologist only).

### GET `/grading/direct/disease/<uuid>/<int:disease_id>`
Displays the grading interface for a specific disease image from direct uploads (admin/ophthalmologist only, with LabUnit restrictions).

### POST `/grading/remedio/glaucoma/grade`
Saves a Glaucoma grade for a remedio camera image.

### POST `/grading/remedio/dr/grade`
Saves a Diabetic Retinopathy grade for a remedio camera image.

### POST `/grading/direct/glaucoma/grade`
Saves a Glaucoma grade for a direct uploaded image (admin/ophthalmologist only).

### POST `/grading/direct/disease/grade`
Saves a disease grade for a direct uploaded image (admin/ophthalmologist only, with LabUnit restrictions).

### POST `/grading/remedio/glaucoma/remove`
Removes a Glaucoma grade for a remedio camera image.

### POST `/grading/remedio/dr/remove`
Removes a Diabetic Retinopathy grade for a remedio camera image.

### POST `/grading/direct/glaucoma/remove`
Removes a Glaucoma grade for a direct uploaded image (admin/ophthalmologist only).

### POST `/grading/direct/disease/remove`
Removes a disease grade for a direct uploaded image (admin/ophthalmologist only, with LabUnit restrictions).

## Best Practices

### For Developers
1. Always use the `@roles_required` decorator for grading routes
2. Implement LabUnit-based access control for direct image routes
3. Validate all user inputs and UUIDs
4. Use the upsert pattern for saving grades
5. Ensure proper error handling and user feedback

### For Administrators
1. Assign appropriate roles to users based on their responsibilities
2. Regularly review grading activities and access logs
3. Ensure LabUnit associations are correctly configured for ophthalmologists
4. Monitor for unauthorized access attempts