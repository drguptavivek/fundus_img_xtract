# Search Images Route Technical Documentation

## Overview
The search functionality provides a comprehensive system for finding and filtering retinal fundus images from two sources: direct uploads and ZIP uploads. The system implements strict filter separation to ensure accurate and efficient searching across different image types.

## Route Implementation

### Location
- **Route File**: `search/route_search_images.py`
- **Route Path**: `/search/images/` (GET requests only)
- **Template**: `templates/search/search_images.html`
- **Core Utility**: `utils/imageSearchUtil.py`

### Access Control
The route requires one of the following roles:
- `admin`
- `data_manager`
- `optometrist`

### Main Function
`search_images_strict()` from `utils/imageSearchUtil.py` performs the actual filtering with strict separation between direct and ZIP image filters.

## Filter Parameters

### Global Filters (Apply to both image types when no specific filters are present)
- `source` - Filter by image source (`all`, `zip`, `direct`)
- `hospital_id` - Filter by hospital ID
- `lab_unit_id` - Filter by lab unit ID
- `upload_start` - Filter for images uploaded after this date
- `upload_end` - Filter for images uploaded before this date
- `search_query` - Text search against UUIDs and filenames

### Direct Upload Specific Filters
- `camera_id` - Filter by camera ID
- `disease_id` - Filter by disease ID
- `area_id` - Filter by area ID
- `is_mydriatic` - Filter by mydriatic status (`true`, `false`)

### ZIP Upload Specific Filters
- `has_dr_report` - Filter for presence/absence of DR reports (`true`, `false`)
- `has_glaucoma_report` - Filter for presence/absence of Glaucoma reports (`true`, `false`)
- `capture_start` - Filter for images captured after this date
- `capture_end` - Filter for images captured before this date

## Search Implementation Details

### Filter Validation and Conflict Prevention
The system implements strict filter validation to prevent conflicts:

1. **Filter Separation**: Direct filters and ZIP filters cannot be applied simultaneously
2. **Source-Specific Validation**: 
   - When `source="direct"`, ZIP-specific filters are rejected
   - When `source="zip"`, direct-specific filters are rejected
3. **Date Validation**: Ensures start dates are before end dates
4. **Error Handling**: Raises `ImageSearchError` with descriptive messages for invalid filter combinations

### Search Scope Determination
The search scope is determined by:
1. Explicit `image_type` parameter (if provided)
2. Presence of direct-specific filters (forces direct-only search)
3. Presence of ZIP-specific filters (forces ZIP-only search)
4. Default to "both" when no specific filters are present

### Query Construction
Separate queries are constructed for each image type:

#### Direct Image Query
- **Table**: `DirectImageUpload`
- **Joins**: `LabUnit`, `Hospital`, `Camera`, `Disease`, `Area`, `User` (for uploader)
- **Filtering**: Applies direct-specific filters and global filters
- **Ordering**: `created_at DESC`

#### ZIP Image Query
- **Table**: `EncounterFile`
- **Joins**: `LabUnit`, `PatientEncounters`, `ZipFile`, `Hospital`
- **Conditional Joins**: `DiabeticRetinopathyReport`, `GlaucomaResultsCleaned` (based on report filters)
- **Filtering**: Applies ZIP-specific filters and global filters
- **Ordering**: `ZipFile.upload_date DESC NULLS LAST`

### User Access Control
- **Admin-like users** (admin, data_manager, optometrist): Can access all lab units
- **Other users**: Restricted to their assigned lab units
- **Lab unit filtering**: Applied at the query level for efficient data access

### Pagination
- **Default page size**: 50 images (configurable via `ANALYTICS_SEARCH_IMAGES_PAGE_SIZE`)
- **Pagination method**: Applied to combined results after merging and sorting
- **URL preservation**: All filter parameters are maintained in pagination links

## Task Information Integration

### Task Query Optimization
The system efficiently retrieves task information for multiple images:
- Queries tasks in batches rather than individually
- Returns tasks regardless of state (not just active ones)
- Groups tasks by image ID for efficient lookup

### Task Display
- Shows disease name and task status for each image
- Handles cases with no tasks gracefully
- Displays task information in the results interface

## Frontend Implementation

### Template Structure
The template is organized into two main filter sections:

1. **Common Filters Section** (lines 19-64):
   - Filters that apply to both image types
   - Always visible regardless of source selection

2. **Image-Specific Filters Section** (lines 67-140):
   - Contains filters specific to either direct uploads or ZIP uploads
   - Visibility toggled based on source selection
   - Clear separation between direct-only and ZIP-only filters

### JavaScript Functionality
- **Dynamic LabUnit filtering**: Fetches lab units based on selected hospital
- **Filter visibility toggling**: Shows/hides relevant filters based on source selection
- **Form state preservation**: Maintains filter values across page reloads

### UI Components
- **Bootstrap 5.3**: Used for styling and responsive design
- **PhotoSwipe**: Integrated for image viewing
- **Flash-Toasts**: For user feedback on search errors

## Error Handling

### Search Errors
- **Filter conflicts**: Detected and reported with descriptive messages
- **Invalid parameters**: Validated before query execution
- **Database errors**: Caught and logged with user-friendly error messages

### Logging
- **Request logging**: Records search parameters and user information
- **Performance logging**: Tracks query execution time
- **Error logging**: Detailed error information for debugging

## Data Flow

1. **Request Processing**: Route parses and validates all filter parameters
2. **User Authorization**: Checks user permissions and lab unit access
3. **Filter Validation**: Validates filter combinations and determines search scope
4. **Query Execution**: Executes separate queries for direct and ZIP images
5. **Task Integration**: Retrieves task information for all images
6. **Result Merging**: Combines and sorts results from both sources
7. **Pagination**: Applies pagination to merged results
8. **Template Rendering**: Passes formatted data to template with filter state

## Performance Considerations

### Query Optimization
- **Eager loading**: Uses `joinedload()` to prevent N+1 queries
- **Batch processing**: Retrieves task information efficiently
- **Conditional joins**: Only joins report tables when needed

### Memory Management
- **Pagination limits**: Prevents excessive memory usage
- **Result formatting**: Converts SQLAlchemy objects to dictionaries before template rendering
- **Session management**: Proper database session handling with context managers

## Security Features

### Access Control
- **Role-based access**: Only authorized users can access search functionality
- **Lab unit scoping**: Users can only see images from their assigned lab units
- **CSRF protection**: All forms include CSRF tokens

### Input Validation
- **Type validation**: Proper parsing of boolean and date parameters
- **Range validation**: Validates pagination parameters
- **SQL injection prevention**: Uses parameterized queries throughout

## Configuration

### Environment Variables
- `ANALYTICS_SEARCH_IMAGES_PAGE_SIZE`: Controls default pagination size

### Customization Points
- Filter validation logic in `validate_search_filters()`
- Query construction in `build_direct_query()` and `build_zip_query()`
- Result formatting in `format_direct_image_with_tasks()` and `format_zip_image_with_tasks()`
