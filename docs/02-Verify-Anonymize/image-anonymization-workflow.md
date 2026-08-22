# Image Anonymization Workflow Documentation

This document provides detailed technical documentation for the Image Anonymization workflow used for direct images uploaded via the `direct_uploads` module.

## Overview

The Image Anonymization workflow provides a comprehensive system for editing, verifying, and managing direct fundus image uploads before they are made available for grading tasks. This workflow ensures patient privacy by allowing anonymization of sensitive information while maintaining image quality for medical analysis.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Route Structure](#route-structure)
3. [Database Models](#database-models)
4. [Image Editing Process](#image-editing-process)
5. [Verification Process](#verification-process)
6. [Task Creation Integration](#task-creation-integration)
7. [UI Components](#ui-components)
8. [JavaScript Interactions](#javascript-interactions)
9. [API Endpoints](#api-endpoints)
10. [Error Handling](#error-handling)
11. [Security Considerations](#security-considerations)
12. [Performance Considerations](#performance-considerations)
13. [Monitoring and Logging](#monitoring-and-logging)

## System Architecture

The Image Anonymization system consists of several key components:

- **Preprocess Module** (`preprocess/`): Contains the anonymization routes and logic
- **Direct Uploads Module** (`direct_uploads/`): Handles image saving and storage
- **Frontend JavaScript** (`static/js/edit_image.js`): Provides image editing interface
- **Database Models**: Track uploads, verification status, and grading tasks
- **Media Service**: Serves original and edited images

### Key Components

1. **DirectImageUpload Model**: Represents uploaded images with metadata
2. **DirectImageVerify Model**: Tracks verification status and user actions
3. **Image Editor**: Canvas-based image editing with anonymization tools
4. **Verification System**: User-based verification workflow
5. **Task Creation Integration**: Creates grading tasks after verification

## Route Structure

### Main Routes

| Route | Method | Purpose | Template |
|-------|--------|---------|----------|
| `/preprocess/dashboard` | GET | Dashboard with statistics and navigation | `preprocess/anonymization_dashboard.html` |
| `/preprocess/anonymize_image/<uuid:uuid>` | GET/POST | Edit and verify individual images | `preprocess/anonymize_image.html` |
| `/preprocess/anonymize_image/<uuid:uuid>/restore_original` | POST | Restore original image (delete edited) | N/A (AJAX) |
| `/direct/upload/save_image/<int:upload_id>` | POST | Save edited image to disk | N/A (AJAX) |

### Key Files

- **Route Module**: `preprocess/anonymize_image.py`
- **Save Handler**: `direct_uploads/save_image.py`
- **Frontend Script**: `static/js/edit_image.js`
- **Templates**: `templates/preprocess/`
- **Blueprint Registration**: `preprocess/__init__.py`

### Key Files

- **Route Module**: `preprocess/anonymize_image.py`
- **Save Handler**: `direct_uploads/save_image.py`
- **Frontend Script**: `static/js/edit_image.js`
- **Templates**: `templates/preprocess/`

## Database Models

### Primary Models

1. **DirectImageUpload**: Represents uploaded images
2. **DirectImageVerify**: Tracks verification status
3. **GradingTask**: Created after verification
4. **User, Hospital, LabUnit, Camera, Disease, Area**: Reference data

### Key Fields

```python
# DirectImageUpload model (key fields)
id: Mapped[int]
uuid: Mapped[UUID]
filename: Mapped[str]
folder_rel: Mapped[str]
edited_filename: Mapped[str | None]  # Name of edited file if any
hospital_id: Mapped[int]
lab_unit_id: Mapped[int]
camera_id: Mapped[int]
disease_id: Mapped[int]
area_id: Mapped[int]
uploader_id: Mapped[int]
created_at: Mapped[datetime]

# DirectImageVerify model
id: Mapped[int]
image_upload_id: Mapped[int]
verified_status: Mapped[str]  # 'verified' or other statuses
remarks: Mapped[str | None]
verified_by_id: Mapped[int]
verified_at: Mapped[datetime]

# Related models used in queries
User, Hospital, LabUnit, Camera, Disease, Area, GradingTask
```

## Image Editing Process

### 1. Image Loading and Display

**Function**: `anonymize_image(uuid: UUID)` (GET)

**Process**:
1. Load image by UUID from DirectImageUpload
2. Check user permissions (lab unit restrictions)
3. Verify no active grading tasks exist
4. Build URLs for original and edited versions
5. Load current verification status
6. Render editing interface

**Key Code**:
```python
# Load image by UUID
upload = db_session.execute(
    select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
).scalar_one_or_none()

# Check for blocking tasks
task_state_rows = db_session.execute(
    select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
).scalars().all()
if task_state_rows:
    normalized_task_states = [_normalize_task_state(state) for state in task_state_rows]
    blocking_task_states = sorted({state for state in normalized_task_states if state and state != "pending"})
    editing_locked = bool(blocking_task_states)
```

### 2. Image Editing Interface

**Frontend**: `static/js/edit_image.js`

**Features**:
- **Canvas-based editing**: HTML5 Canvas for image manipulation
- **Multiple tools**: Brush, eraser, and rectangular crop tools
- **Brush customization**: Adjustable size (1-50px) and color picker
- **Rectangular cropping**: One movable/resizable selection backed by clean image pixels
- **Undo/Redo functionality**: Full history management with navigation
- **Real-time preview**: Live preview of edits with marching ants for crop
- **Touch support**: Basic touch event handling for tablet devices
- **Editing lock detection**: Disables editing when tasks are in progress

**Key Components**:
```javascript
// State management
let currentTool = 'brush';
let brushSize = 10;
let brushColor = '#000000';
let history = [];
let historyIndex = -1;

// Drawing state
let isDrawing = false;
let lastX = 0;
let lastY = 0;

// Cropping state (single rectangle)
let isCropping = false;         // actively interacting (down → move → up)
let crop = null;                // { x, y, width, height } OR null
let cropBase = null;            // clean pixels beneath the temporary overlay
let cropMode = null;            // 'creating' | 'moving' | 'resizing'
let activeHandle = null;        // 'NW' | 'NE' | 'SE' | 'SW' | null
let dragDX = 0, dragDY = 0;     // for moving (pointer offset from top-left)

const HANDLE_SIZE = 10;         // px
const MIN_CROP_SIZE = 16;
let antsOffset = 0;             // marching ants
let antsRAF = null;
```

### 3. Image Saving Process

**Route**: `/direct/upload/save_image/<int:upload_id>`
**Handler**: `direct_uploads/save_image.py`

**Process**:
1. Validate user permissions
2. Check for blocking grading tasks
3. Decode and validate the image data
4. Derive the edited filename extension from the actual JPEG/PNG/WebP bytes
5. Save to file system
6. Update database record
7. Log the action

**Key Code**:
```python
# Generate edited filename
decoded_image = decode_image_edit_payload(image_data)
edited_basename = f"edited_{Path(upload.filename).stem}{decoded_image.extension}"
edited_path = abs_from_parts(upload.folder_rel, edited_basename, kind="edited")

# Ensure the destination directory exists
edited_path.parent.mkdir(parents=True, exist_ok=True)

# Save the edited image
edited_path.write_bytes(image_bytes)

# Update the database with the basename of the edited file
upload.edited_filename = edited_basename
db.commit()
```

## Verification Process

### 1. Verification Dashboard

**Function**: `anonymization_dashboard()`

**Features**:
- **KPIs**: Total anonymized, pending, and user-verified images
- **Filtering**: By hospital, lab unit, camera, disease, area, status, user
- **Pagination**: Recent verifications with pagination
- **Charts**: Pending images by disease and lab unit
- **Navigation**: Quick access to next unverified image

**Key Code**:
```python
# Count all records with verified_status = "verified"
total_anonymized_images = db_session.execute(
    select(func.count(DirectImageVerify.id)).where(DirectImageVerify.verified_status == "verified")
).scalar_one()

# Count all DirectImageUpload records that do NOT have a verified status
verified_subquery = (
    select(DirectImageVerify.image_upload_id)
    .where(DirectImageVerify.verified_status == "verified")
    .distinct()
).subquery()

pending_anonymization_images = db_session.execute(
    select(func.count(DirectImageUpload.id)).where(
        ~DirectImageUpload.id.in_(select(verified_subquery.c.image_upload_id).scalar_subquery())
    )
).scalar_one()

# Count all verified records by the current user
user_verified_images = db_session.execute(
    select(func.count(DirectImageVerify.id)).where(
        DirectImageVerify.verified_status == "verified",
        DirectImageVerify.verified_by_id == current_user.id,
    )
).scalar_one()
```

### 2. Image Verification

**Function**: `anonymize_image(uuid: UUID)` (POST)

**Process**:
1. Validate user permissions
2. Process verification form data
3. Update or create DirectImageVerify record
4. Handle task creation/removal based on status
5. Commit transaction
6. Redirect to next unverified image

**Key Code**:
```python
# Handle the toggle switch - if checked, it will be "verified", otherwise it won't be in form data
verified_status = request.form.get("verified_status", "unverified")
remarks = request.form.get("remarks")

if current_verification:
    current_verification.verified_status = verified_status
    current_verification.remarks = remarks
    current_verification.verified_by_id = current_user.id
    current_verification.verified_at = func.now()
else:
    db_session.add(
        DirectImageVerify(
            image_upload_id=upload.id,
            verified_status=verified_status,
            remarks=remarks,
            verified_by_id=current_user.id,
            verified_at=func.now(),
        )
    )

# Handle task creation/removal based on verification status
if verified_status == "verified":
    # Create a grading task for the verified direct image
    ensure_task(upload.uuid, upload.disease_id)
elif verified_status != "verified":
    # Check if we can unverify the image (all tasks must be pending)
    if not can_unverify_image(db_session, kind="direct", image_id=upload.id):
        flash("Cannot unverify image - some tasks are in progress.", "danger")
        return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))
    
    # Remove all pending grading tasks for this image
    removed_count = remove_pending_tasks(db_session, kind="direct", image_id=upload.id)
```

### 3. Unverification Process

**Function**: `anonymize_image(uuid: UUID)` (POST, unverified status)

**Process**:
1. Check if unverification is allowed (all tasks must be pending)
2. Update verification status
3. Remove pending grading tasks
4. Commit transaction

**Key Code**:
```python
# Check if unverification is allowed
if not can_unverify_image(db_session, kind="direct", image_id=upload.id):
    flash("Cannot unverify image - some tasks are in progress.", "danger")
    return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))

# Remove pending tasks
removed_count = remove_pending_tasks(db_session, kind="direct", image_id=upload.id)
```

## Task Creation Integration

### Verification Gating

The system integrates with `TaskCreationServices` through the verification system:

```python
# In TaskCreationServices
def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    if kind == 'direct':
        return db.execute(
            select(1).select_from(DirectImageVerify)
            .where(and_(
                DirectImageVerify.image_upload_id == image_id,
                DirectImageVerify.verified_status == 'verified'
            ))
        ).first() is not None
```

### Task Creation Flow

1. **Verification Trigger**: User verifies an image via POST to `/preprocess/anonymize_image/<uuid>`
2. **Disease Lookup**: Use the disease associated with the upload (`upload.disease_id`)
3. **Task Creation**: Call `ensure_task()` with image UUID and disease ID
4. **Error Handling**: Log any task creation failures without failing the verification
5. **Redirect**: Navigate to next unverified image or dashboard

### Task Creation Flow

1. **Verification Trigger**: User verifies an image
2. **Disease Lookup**: Use the disease associated with the upload
3. **Task Creation**: Call `ensure_task()` with image UUID and disease ID
4. **Error Handling**: Log any task creation failures

## UI Components

### Dashboard Features

- **Statistics Cards**: Total anonymized, pending, user-verified counts
- **Filter Panel**: Comprehensive filtering options
- **Recent Verifications Table**: Paginated list with details
- **Chart Visualization**: Pending images by disease and lab unit
- **Quick Navigation**: "Next Unverified Image" button

### Image Editor Features

- **Tool Selection**: Brush, eraser, and crop tools
- **Brush Controls**: Size slider and color picker
- **Canvas Area**: Interactive editing surface
- **History Controls**: Undo/redo buttons
- **Action Buttons**: Save, restore, clear
- **Verification Form**: Status toggle and remarks field

### JavaScript Interactions

- **Canvas Drawing**: Mouse and touch support for drawing
- **Crop Tool**: Single rectangular crop with corner handles and canvas resizing
- **History Management**: Undo/redo with state persistence
- **AJAX Communication**: Save and restore without page reload
- **Real-time Feedback**: Visual feedback for all actions

## API Endpoints

### Save Image Endpoint

**URL**: `POST /direct/upload/save_image/<int:upload_id>`

**Request**:
```json
{
  "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "csrf_token": "..."
}
```

**Response (Success)**:
```json
{
  "message": "Image saved successfully."
}
```

**Response (Error)**:
```json
{
  "error": "Cannot edit image while grading tasks are in progress."
}
```

### Restore Original Endpoint

**URL**: `POST /preprocess/anonymize_image/<uuid:uuid>/restore_original`

**Request**:
```json
{
  "csrf_token": "..."
}
```

**Response (Success)**:
```json
{
  "redirect_url": "/preprocess/anonymize_image/550e8400-e29b-41d4-a716-446655440000"
}
```

## Error Handling

### Common Error Scenarios

1. **Permission Denied**: User lacks required roles or lab unit access
2. **Image Not Found**: Invalid UUID or upload ID
3. **Task Conflict**: Grading tasks in progress preventing editing
4. **File System Errors**: Unable to save or delete files
5. **Database Errors**: Transaction failures or constraint violations

### Error Handling Pattern

```python
try:
    # Processing logic
    db_session.commit()
    flash("Operation completed successfully.", "success")
except Exception as e:
    db_session.rollback()
    editing_logger.exception("Operation failed: %s", e)
    flash("Operation failed. Please try again.", "danger")
```

### Client-Side Error Handling

```javascript
fetch(saveUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
    body: JSON.stringify({ image_data: imageData })
})
.then(response => response.json())
.then(data => {
    if (data.error) { 
        alert('Error: ' + data.error); 
    } else { 
        alert('Success!'); 
        window.location.reload(); 
    }
})
.catch(error => { 
    console.error('Error:', error); 
    alert('An unexpected error occurred.'); 
});
```

## Security Considerations

### Access Control

- **Role-based access**: Requires `admin`, `optometrist`, or `data_manager` roles
- **Lab unit restrictions**: Users can only access assigned lab units
- **Ownership checks**: Users can only edit their own uploads (unless admin/data_manager)
- **CSRF protection**: All forms include CSRF tokens

### Data Integrity

- **Transaction management**: All operations wrapped in database transactions
- **File system consistency**: Database and file system kept in sync
- **Audit trail**: Complete record of who edited what and when
- **Validation**: Input validation and sanitization

### Privacy Considerations

- **Patient data**: Handle PHI according to privacy requirements
- **Access logging**: Log all editing and verification actions
- **Secure storage**: Edited files stored securely with controlled access
- **Data retention**: Follow data retention policies

## Performance Considerations

### Database Optimization

- **Indexing**: Key fields are indexed for efficient queries
- **Query optimization**: Efficient joins and filtering
- **Pagination**: Limit results per page
- **Eager loading**: Reduce N+1 query problems

### Frontend Optimization

- **Canvas performance**: Efficient drawing operations
- **Memory management**: Proper cleanup of canvas resources
- **Image loading**: Optimized image loading with caching
- **AJAX efficiency**: Minimal data transfer

### File System Considerations

- **Path organization**: Structured file organization for efficient access
- **Concurrent access**: Handle concurrent file operations safely
- **Storage management**: Monitor disk usage for edited images
- **Backup strategy**: Ensure edited images are backed up

## Monitoring and Logging

### Key Metrics to Monitor

- **Processing times**: Time from upload to verification
- **Edit rates**: Frequency and type of edits
- **Verification rates**: Completion rates and patterns
- **Error rates**: Failed operations and their causes
- **User activity**: Patterns of usage by user and lab unit

### Logging Strategy

```python
# Comprehensive logging with context
editing_logger.info("Save image request for upload_id=%s", upload_id)
editing_logger.info("Content-Type: %s", request.content_type)
editing_logger.debug("Starting anonymize_image function for UUID %s - User: %s, Method: %s",
                     uuid_val, current_user.username, request.method)
editing_logger.info("Created grading task for verified direct image UUID %s", upload.uuid)
editing_logger.info("Saved edited image for upload %s by user %s", upload_id, current_user.id)
editing_logger.exception("Failed to create grading task for verified direct image UUID %s: %s",
                         upload.uuid, task_error)
```

### Audit Trail

- **User actions**: All editing and verification actions logged
- **File operations**: File creation, modification, and deletion tracked
- **Access patterns**: Who accessed which images and when
- **System events**: Key system events and state changes

## Best Practices

### For Users

1. **Verify image quality**: Ensure edits don't compromise diagnostic value
2. **Use appropriate tools**: Select the right tool for the anonymization task
3. **Document decisions**: Use remarks field to explain verification decisions
4. **Follow workflow**: Complete all required steps before verification

### For Developers

1. **Maintain audit trail**: Log all actions for compliance
2. **Handle edge cases**: Account for various image formats and sizes
3. **Provide feedback**: Clear error messages and progress indicators
4. **Test thoroughly**: Verify all workflows work correctly

### For System Administrators

1. **Monitor storage**: Track disk usage for edited images
2. **Review logs**: Regularly review system logs for issues
3. **Backup data**: Ensure both original and edited images are backed up
4. **Performance tuning**: Optimize system performance based on usage patterns

## Related Documentation

- [Verification Workflows Overview](verification-workflows-overview.md)
- [Direct Uploads Documentation](../01-Adding_Images/direct_uploads.md)
- [Task Creation Services](../03-Tasks/taskCreationServices.md)
- [Database Schema](../00-Core/models.md)
- [Security Guidelines](../04-Security/security-guidelines.md)

## Troubleshooting

### Common Issues

1. **Image not loading**: Check file permissions and paths
2. **Edits not saving**: Verify CSRF token and permissions
3. **Verification failing**: Check for active grading tasks
4. **Performance issues**: Monitor database query performance
5. **File system errors**: Check disk space and permissions

### Debugging Steps

1. **Check logs**: Review application logs for error messages
2. **Verify permissions**: Ensure user has appropriate roles
3. **Test database**: Check database connectivity and queries
4. **Validate files**: Ensure files exist and are accessible
5. **Monitor network**: Check for network connectivity issues

## Future Enhancements

### Potential Improvements

1. **AI-assisted anonymization**: Automatic detection of sensitive information
2. **Batch operations**: Process multiple images simultaneously
3. **Advanced editing tools**: More sophisticated editing capabilities
4. **Mobile support**: Optimize for tablet/mobile devices
5. **Integration**: Better integration with other workflows

### Technical Debt

1. **Code consolidation**: Reduce duplication between modules
2. **Performance optimization**: Optimize large image handling
3. **Error handling**: Improve error recovery mechanisms
4. **Testing**: Increase test coverage for all workflows
5. **Documentation**: Maintain up-to-date documentation

## Conclusion

The Image Anonymization workflow provides a comprehensive solution for editing and verifying direct fundus image uploads while maintaining patient privacy and data integrity. The system combines powerful editing tools with robust verification processes to ensure high-quality, anonymized images are available for grading tasks.

The workflow is designed to be user-friendly while maintaining strict security and audit requirements. By following this documentation, users can effectively anonymize images and developers can maintain and extend the system as needed.
