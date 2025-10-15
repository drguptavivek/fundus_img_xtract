# Common Utilities and Components

This document describes the core utilities and reusable components used throughout the Fundus Image Manager application. These utilities provide essential functionality for image serving, data retrieval, and UI components that are used across multiple modules.

## Core Utility Functions

### Image Serving Utilities

#### `serve_image_for_grading(uuid)`
Serves an image optimized for grading interface based on its UUID.

**Purpose**: Provides a secure way to access images for grading without exposing file system paths.

**Parameters**:
- `uuid` (string): The unique identifier of the image

**Returns**: Image file with appropriate headers for display in grading interface

**Usage in**:
- `/grading/` routes
- `/search/image` endpoints
- Analytics modules

**Related Documentation**: [Media Routes](docs/routes.md#media-routes)

### User and Lab Unit Utilities

#### `get_user_lab_units(user_id)`
Retrieves all lab units associated with a user.

**Purpose**: Determines which lab units a user has access to, essential for scoping and permissions.

**Parameters**:
- `user_id` (int): The user's ID

**Returns**: List of lab unit objects with ID, name, and other details

**Usage in**:
- Authentication and authorization checks
- Task assignment logic
- Data filtering in search and analytics

**Related Documentation**: [Scoping Mechanisms](Scoping.md)

### Image and Encounter Data Retrieval

#### `get_image_details(uuid)`
Retrieves comprehensive details about an image including metadata, associated encounter, and file information.

**Purpose**: Provides a complete view of an image for display in various interfaces.

**Parameters**:
- `uuid` (string): The unique identifier of the image

**Returns**: Dictionary containing:
- Image metadata (capture date, laterality, quality)
- Associated encounter information
- File details (path, size, type)
- Processing status

**Usage in**:
- `/search/image` endpoints
- Analytics modules
- Image verification workflows

**Related Documentation**: [Database Models](Models.md#encounterfile)

#### `get_image_zip_details(uuid)`
Retrieves ZIP file information associated with an image.

**Purpose**: Traces an image back to its original ZIP upload for audit and reference.

**Parameters**:
- `uuid` (string): The unique identifier of the image

**Returns**: Dictionary containing:
- ZIP file metadata
- Upload information
- Processing status
- Associated files from the same ZIP

**Usage in**:
- Audit workflows
- Data provenance tracking
- Analytics modules

#### `get_image_task_details(uuid)`
Retrieves all grading tasks associated with an image.

**Purpose**: Shows the complete grading history and current status for an image.

**Parameters**:
- `uuid` (string): The unique identifier of the image

**Returns**: Dictionary containing:
- List of grading tasks
- Task status and assignments
- Grading results
- Consensus information

**Usage in**:
- `/search/image` endpoints
- Analytics modules
- Grading dashboard

**Related Documentation**: [Dual Grading Workflow](dual_grading.md)

#### `get_encounter_details(encounter_id)`
Retrieves comprehensive details about a patient encounter.

**Purpose**: Provides complete encounter information for clinical review and analysis.

**Parameters**:
- `encounter_id` (int): The encounter's ID

**Returns**: Dictionary containing:
- Patient demographics (anonymized as needed)
- Encounter metadata
- Associated images and reports
- Verification status

**Usage in**:
- `/search/image` endpoints
- Analytics modules
- Screening workflows

**Related Documentation**: [Database Models](Models.md#patientencounters)

## Reusable UI Components

### PhotoSwipe Image Gallery

#### Description
A sophisticated lightbox component for viewing single images or galleries with advanced features.

**Features**:
- Full-screen image viewing
- Zoom and pan capabilities
- Keyboard navigation
- Touch gestures for mobile devices
- Caption and metadata display
- Thumbnail navigation for galleries

**Usage**:
```html
<!-- Single image -->
<div class="pswp-gallery">
  <a href="/media/image/<uuid>" 
     data-pswp-src="/media/image/<uuid>" 
     data-pswp-width="1200" 
     data-pswp-height="800">
    <img src="/media/image/<uuid>?thumbnail=true" alt="Fundus image">
  </a>
</div>

<!-- Image gallery -->
<div class="pswp-gallery" id="gallery-<?php echo $encounter_id; ?>">
  <?php foreach ($images as $img): ?>
  <a href="/media/image/<?php echo $img['uuid']; ?>" 
     data-pswp-src="/media/image/<?php echo $img['uuid']; ?>" 
     data-pswp-width="<?php echo $img['width']; ?>" 
     data-pswp-height="<?php echo $img['height']; ?>">
    <img src="/media/image/<?php echo $img['uuid']; ?>?thumbnail=true" alt="Fundus image">
  </a>
  <?php endforeach; ?>
</div>
```

**JavaScript Initialization**:
```javascript
// Initialize PhotoSwipe
const lightbox = new PhotoSwipeLightbox({
  gallery: '.pswp-gallery',
  children: 'a',
  pswpModule: PhotoSwipe
});

lightbox.init();
```

**Implementation Files**:
- `/static/js/photoswipe-lightbox.umd.min.js`
- `/static/js/photoswipe.umd.min.js`
- `/static/css/photoswipe.css`
- `/static/js/pswp-init.js`

**Related Documentation**: [JavaScript Guidance](JavaScript_Guidance.md#photoswipe-integration)

### Advanced Image Viewer

#### Description
A specialized image viewer component for grading with clinical tools and adjustments.

**Features**:
- Zoom in/out with mouse wheel or buttons
- Brightness and contrast adjustment
- Color filters for different viewing modes
- Measurement tools
- Annotation capabilities
- Reset to original view

**Usage**:
```html
<div id="image-viewer" class="image-viewer-container">
  <div class="viewer-controls">
    <button id="zoom-in">+</button>
    <button id="zoom-out">-</button>
    <button id="reset-view">Reset</button>
    <input type="range" id="brightness" min="-100" max="100" value="0">
    <input type="range" id="contrast" min="-100" max="100" value="0">
  </div>
  <div class="image-container">
    <img id="graded-image" src="/media/grading-image/<uuid>" alt="Fundus image">
  </div>
</div>
```

**JavaScript Implementation**: `/static/js/edit_image.js`

**Related Documentation**: [JavaScript Guidance](JavaScript_Guidance.md#image-viewer-component)

### Flash Toasts Component

#### Description
A notification system for displaying user feedback messages.

**Features**:
- Auto-dismiss after configurable time
- Multiple types (success, error, warning, info)
- Stacking multiple notifications
- Smooth animations
- Mobile-responsive design

**Usage**:
```javascript
// Display a success message
flashToast('Image saved successfully', 'success');

// Display an error message
flashToast('Failed to process image', 'error');

// Display with custom duration
flashToast('Processing started', 'info', 5000);
```

**Implementation Files**:
- `/static/js/flash-toasts.js`
- `/static/css/app.css` (toast styles)

**Related Documentation**: [Flash Toasts Component](../static/js/flash-toasts.md)

## Integration Examples

### Search and Analytics Integration

The utilities work together in search and analytics modules:

```python
# Example in search/image route
@app.route('/search/image/<uuid>')
def search_image(uuid):
    # Get comprehensive image details
    image_details = get_image_details(uuid)
    
    # Get associated encounter information
    encounter_details = get_encounter_details(image_details['encounter_id'])
    
    # Get ZIP file provenance
    zip_details = get_image_zip_details(uuid)
    
    # Get grading task information
    task_details = get_image_task_details(uuid)
    
    return render_template('search/image_details.html',
                         image=image_details,
                         encounter=encounter_details,
                         zip_info=zip_details,
                         tasks=task_details)
```

### Analytics Dashboard Integration

```python
# Example in analytics route
@app.route('/analytics/image-performance/<uuid>')
def image_analytics(uuid):
    # Get user's lab units for scoping
    user_labs = get_user_lab_units(current_user.id)
    
    # Get image details with permission check
    image_details = get_image_details(uuid)
    
    # Verify user has access to this image
    if image_details['lab_unit_id'] not in [lab.id for lab in user_labs]:
        abort(403)
    
    # Get performance metrics
    task_details = get_image_task_details(uuid)
    
    return render_template('analytics/image_performance.html',
                         image=image_details,
                         tasks=task_details)
```

## Security Considerations

1. **Access Control**: All utilities incorporate proper permission checks
2. **Data Anonymization**: Patient data is automatically anonymized where required
3. **Audit Logging**: All access to sensitive data is logged
4. **Input Validation**: All inputs are properly validated before processing
5. **Rate Limiting**: Image serving endpoints implement rate limiting

## Performance Optimization

1. **Caching**: Frequently accessed data is cached at appropriate levels
2. **Lazy Loading**: Images and details are loaded on demand
3. **Database Optimization**: Queries use proper indexing and join strategies
4. **Image Optimization**: Images are served in appropriate sizes and formats

## Related Documentation

- [Database Models](Models.md) - For data structure understanding
- [Routes Documentation](routes.md) - For endpoint details
- [Security Guidelines](Security.md) - For security implementation
- [JavaScript Guidance](JavaScript_Guidance.md) - For frontend integration
- [Analytics Utils](analytics/utils.md) - For analytics-specific usage
- [Task Utilities](../utils/taskUtils.md) - For task management and retrieval functions