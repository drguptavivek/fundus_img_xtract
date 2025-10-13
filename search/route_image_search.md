Search Images Route Analysis
Route Implementation
The route is defined in search/route_search_images.py at /search/images/ and handles GET requests. It uses the centralized search_images() function from utils/imageSearchUtil.py to perform the actual filtering.

Filter Parameters
The system supports the following filter parameters:

Common Filters (apply to both image types):
source - Filter by image source (all, zip, direct)
hospital_id - Filter by hospital ID
lab_unit_id - Filter by lab unit ID
upload_start - Filter for images uploaded after this date
upload_end - Filter for images uploaded before this date
capture_start - Filter for images captured after this date
capture_end - Filter for images captured before this date
search_query - Text search against filenames, UUIDs, and other identifiers
Direct Upload Specific Filters:
camera_id - Filter by camera ID (only applies to direct uploads)
disease_id - Filter by disease ID (only applies to direct uploads)
area_id - Filter by area ID (only applies to direct uploads)
is_mydriatic - Filter by mydriatic status (true, false)
ZIP Upload Specific Filters:
has_dr_report - Filter for presence/absence of DR reports (true, false)
has_glaucoma_report - Filter for presence/absence of Glaucoma reports (true, false)
How Filtering Works
Parameter Parsing: The route parses all filter parameters from the request args, using helper functions like _parse_bool_param() and _parse_date() to properly convert string values.

User Access Control: The system checks user permissions and restricts lab unit access based on the user's role. Admin-like users (admin, data_manager, optometrist) can see all lab units, while other users are restricted to their assigned lab units.

Search Function Call: The route calls the search_images() function with all the parsed parameters.

Query Construction: In utils/imageSearchUtil.py, separate queries are constructed for direct uploads and ZIP uploads:

For direct uploads, it queries the DirectImageUpload table
For ZIP uploads, it queries the EncounterFile table
The results are combined using a UNION ALL operation
Filter Application: Each filter is applied conditionally to the appropriate query:

Date filters use comparison operators (>=, <=)
ID filters use IN clauses for lists or direct equality for single values
Boolean filters use equality checks
Text search uses LIKE/CONTAINS operations
Pagination: Results are paginated with a configurable page size (default 50).

Template Rendering: The filtered results are passed to the template along with all the filter values to maintain form state.

Template Structure
The template templates/search/search_images.html is organized into two main filter sections:

Common Filters Section (lines 15-65): Contains filters that apply to both image types
Image-Specific Filters Section (lines 68-137): Contains filters specific to either direct uploads or ZIP uploads
The form uses GET method to submit filters, and all filter values are preserved in the form fields using the filters context variable.

Key Implementation Details
When a disease filter is applied, the source is automatically set to "direct" since diseases only apply to direct uploads (lines 71-72).

The route passes a filter_params dictionary to the template (lines 208-223) which contains all the current filter values.

The _filter_kwargs() helper function (lines 225-230) is used to construct URLs for pagination that preserve all current filter parameters.

The template uses Bootstrap classes for styling and includes responsive design considerations with col-12 col-md-3 classes for form fields.

