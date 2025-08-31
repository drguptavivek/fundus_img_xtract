# Phase 1 Implementation Steps.  - USER MANAGEMENT

This document breaks down the backend development for the Direct Image Upload feature into smaller, incremental steps to ensure existing functionality is not broken.

### Step 1: Create Generic Admin Views for Simple Lookup Models

**Goal:** Implement the admin interface for managing `Hospital`, `Camera`, `Disease`, and `Area`.

1.  **Create New Templates:**
    -   Create a new file: `templates/admin/lookup_list.html`. This will be a generic template to list and add items for a lookup model.
    -   Create a new file: `templates/admin/lookup_edit.html`. This will be a generic template to edit an item.

2.  **Add Generic Routes:**
    -   In `admin/routes.py`, add three new routes:
        -   `GET, POST /admin/<model_name>`: This route will handle listing and creating items. It will use a helper function to map the `model_name` string (e.g., "hospital") to the correct SQLAlchemy model.
        -   `GET, POST /admin/<model_name>/<item_id>/edit`: For editing an item.
        -   `POST /admin/<model_name>/<item_id>/delete`: For deleting an item.
    -   These routes will render the new `lookup_list.html` and `lookup_edit.html` templates.

### Step 2: Implement Specific Views for `LabUnit`

**Goal:** Implement the admin interface for `LabUnit`, including its association with a `Hospital`.

1.  **Update Routes:**
    -   The generic routes from Step 1 will be used, but the logic for `model_name == 'lab_unit'` will be enhanced.
    -   When handling `lab_unit`, the routes will fetch all `Hospital`s and pass them to the templates.
    -   The POST logic will validate and save the `hospital_id` for the `LabUnit`.

2.  **Update Templates:**
    -   Modify `lookup_list.html` and `lookup_edit.html` to include conditional logic.
    -   If `model_name == 'lab_unit'`, the list view will show a "Hospital" column.
    -   If `model_name == 'lab_unit'`, the create/edit forms will show a dropdown menu to select the parent `Hospital`.

### Step 3: Update User Management Forms for New Fields

**Goal:** Add the necessary form fields to the user management pages for quotas and lab unit associations.

1.  **Modify `templates/admin/edit_user.html`:**
    -   Add a number input field for `file_upload_quota`.
    -   Add a multi-select box for `lab_units`. This will be populated with all available lab units. The user's currently associated units should be pre-selected.
    -   Show the selected hospital when Lab-Unit is selected for visual confirmation

2.  **Modify `templates/admin/add_user.html`:**
    -   Add a number input field for `file_upload_quota`.
    -   Add a multi-select box for `lab_units`.
    -   Show the selected hospital when Lab-Unit is selected for visual confirmation
 
### Step 4: Update User Management Backend Logic

**Goal:** Update the `add_user` and `edit_user` routes to handle the new fields.

1.  **Modify `add_user` in `admin/routes.py`:**
    -   In the GET request handler, fetch all `LabUnit` and `LabUnit.Hospital` and `file_upload_quota`  and pass them to the template.
    -   In the POST request handler, retrieve the `file_upload_quota` and the list of selected `lab_unit_ids`.
    -   Validate the POST data.
    -   Submit the data to the database.

2.  **Modify `edit_user` and `users_update` in `admin/routes.py`:**
    -   In the `edit_user` GET handler, fetch all of `LabUnit` to populate the options and this users `LabUnit`s and `file_upload_quota` to show current selections
    -   The `users_update` function (which handles POST from the user list) or a modified `edit_user` POST handler will be responsible for updating the associations.
    -   It will retrieve the list of selected `lab_unit_ids`, fetch the corresponding objects, and update the `user.lab_units` relationship.
    -   It will also handle updating the `file_upload_quota`.

### Step 5: Update Navigation

**Goal:** Add links to the new admin pages.

1.  **Modify `templates/base.html`:**
    -   Add a new "Masters" (or similar) dropdown menu in the main navigation bar, visible only to admins.
    -   Inside this dropdown, add links to the new management pages for "Hospitals", "Lab Units", "Cameras", "Diseases", and "Areas".







   1. Created a new /direct/dashboard route that:
      - Displays a paginated list of direct uploads (50 per page)
      - Shows different data based on user roles:
        - Admins and data_managers see all uploads
        - Regular contributors only see their own uploads
      - Includes comprehensive metadata for each image:
        - Filename
        - Uploader information
        - Hospital
        - Lab Unit
        - Camera
        - Disease
        - Area
        - Mydriatic status
        - Upload timestamp

   2. Implemented pagination with:
      - Navigation controls at both top and bottom of the table
      - First/Previous/Next/Last page links
      - Smart page number display that shows relevant pages around current page
      - Validation to prevent invalid page numbers

   3. Added navigation link:
      - Added "Direct Upload Dashboard" link to the Work dropdown menu in the main navigation
      - Only visible to users with contributor, data_manager, or admin roles

   4. Created reusable pagination macro:
      - Extracted pagination logic into a separate template macro to avoid code duplication
      - Made it generic enough to be reused for other paginated views

   5. Added proper error handling and logging:
      - Comprehensive error handling with user-friendly messages
      - Detailed logging for debugging and monitoring purposes
      - Input validation for page numbers

   6. Responsive design:
      - Mobile-friendly table layout
      - Properly formatted data with badges for status indicators
      - Clean, consistent styling that matches the existing application theme

  The dashboard provides an easy way for users to view their direct uploads and for administrators to monitor all uploads in the system.
  The pagination makes it efficient to navigate through large datasets, and the metadata display gives users all the contextual
  information they need about each uploaded image.


  The template looks good. I've successfully added KPIs to the direct upload dashboard with the following features:

   1. Added four KPI cards at the top of the dashboard:
      - Total Uploads: Shows the total number of uploads for the current user (or all uploads for admins/data_managers)
      - Camera Types: Shows the number of different camera types and top 3 camera types with counts
      - Diseases: Shows the number of different diseases and top 3 diseases with counts
      - Areas: Shows the number of different areas and top 3 areas with counts

   2. Used the KPI card styling from the style guide:
      - Applied appropriate color schemes (primary, info, success, warning)
      - Used proper typography with headings, values, and descriptions
      - Made cards responsive with appropriate column sizing

   3. Implemented proper data filtering:
      - For regular contributors, KPIs only show their own uploads
      - For admins and data_managers, KPIs show all uploads in the system
      - Each KPI card shows the count and top items with their respective counts

   4. Added proper error handling:
      - Shows "No data" when there are no uploads
      - Handles cases where there are fewer than 3 items to display

   5. Maintained responsive design:
      - Cards stack vertically on small screens
      - Use appropriate Bootstrap grid classes for different screen sizes
      - Consistent spacing and styling throughout

  The KPI cards provide immediate insight into upload statistics, helping users quickly understand the distribution of their uploads
  across different categories. The implementation follows the existing application styling and maintains consistency with other parts of
  the system.



 Now I've successfully fixed the Jinja2 template errors in the direct upload dashboard. Here's what I did:

   1. Fixed the bracket notation errors in the KPI card loops by:
      - Replacing direct bracket notation like list[:3] with proper Jinja2 syntax
      - Using {% set %} statements to create variables for sorted lists
      - Using {% if loop.index <= 3 %} to limit the display to top 3 items

   2. Fixed the pagination display issue by:
      - Breaking the complex expression into a separate {% set %} statement
      - This avoids the bracket notation that was causing the Jinja2 parser error

  The KPI cards are now properly displayed with:
   - Total Uploads count
   - Camera Types count with top 3 camera types and their counts
   - Diseases count with top 3 diseases and their counts
   - Areas count with top 3 areas and their counts

  Each card uses the appropriate KPI styling from the style guide with proper color schemes and typography. The dashboard now loads
  correctly without Jinja2 template parsing errors.


Now I've successfully added bulk editing capabilities to the direct upload dashboard with the following features:

   1. Bulk Edit Form:
      - Added a form that wraps the entire table with POST method
      - Included hidden action field to identify bulk edit requests
      - Added dropdowns for all editable fields (Hospital, Lab Unit, Camera, Disease, Area)
      - Added a toggle switch for Mydriatic status
      - Added an "Apply" button that is initially disabled

   2. Selection Mechanism:
      - Added checkboxes to each table row for individual selection
      - Added a "Select All" checkbox in the header
      - Implemented JavaScript to manage checkbox selection states

   3. User Experience Improvements:
      - The "Apply" button is disabled until at least one row is selected
      - Added confirmation dialog before applying changes
      - Added validation to ensure at least one field is selected for update
      - Visual feedback when checkboxes are selected

   4. Backend Integration:
      - Updated the route to handle both GET (display) and POST (bulk edit) requests
      - Added logic to process selected uploads and update only the specified fields
      - Implemented proper security filtering so users can only edit their own uploads
      - Added comprehensive error handling and transaction management
      - Added success/error flash messages

   5. Data Loading:
      - Load all available options for dropdowns (all hospitals, lab units, etc.)
      - Pass these options to the template for dropdown population
      - Maintain existing filtering for regular users vs admins

   6. Security Features:
      - Non-admin users can only edit their own uploads
      - Server-side validation of selected uploads
      - CSRF protection via the existing csrf_field()
      - Proper input sanitization and validation

  The bulk editing functionality allows users to:
   - Select multiple uploads using checkboxes
   - Choose which fields to update using the dropdowns and toggle
   - Apply changes to all selected uploads with a single action
   - Receive confirmation before making changes
   - See success/error feedback after the operation

  This significantly improves the efficiency of managing direct uploads, especially when users need to correct metadata for multiple
  files at once.

  Now I've successfully enhanced the direct upload dashboard with delete functionality and implemented the 30-file limit for bulk
  operations. Here are the key improvements:

   1. Delete Functionality:
      - Added a "Delete Selected" button alongside the "Edit Selected" button
      - Implemented server-side delete handling in the route with proper file deletion from disk
      - Added confirmation dialog before deletion to prevent accidental data loss
      - Added proper error handling and logging for file deletion failures

   2. 30-File Limit Enforcement:
      - Implemented client-side validation to prevent selecting more than 30 files
      - Added server-side validation as an additional safety check
      - Displayed a clear error message when the limit is exceeded
      - Updated the UI to show the selected file count and limit (e.g., "Selected: 5/30 files")

   3. Improved UI/UX:
      - Added a counter showing the number of selected files out of the maximum allowed
      - Separated the delete and edit operations with distinct buttons
      - Improved the bulk edit workflow with show/hide controls
      - Added proper form reset when canceling bulk edit operations
      - Enhanced error messaging and user feedback

   4. Enhanced Security:
      - Maintained user-level filtering so non-admin users can only operate on their own uploads
      - Added proper transaction handling with rollback on errors
      - Implemented file system error handling to prevent crashes if file deletion fails

   5. Better Organization:
      - Renamed the form to "bulk-operations-form" to reflect its dual purpose
      - Used hidden input fields to distinguish between edit and delete actions
      - Improved JavaScript organization with clearer function names and separation of concerns

  The implementation ensures that:
   - Users cannot accidentally delete more than 30 files at once
   - File deletions are confirmed before execution
   - Both edit and delete operations follow the same 30-file limit
   - The UI clearly indicates how many files are selected and the maximum allowed
   - All operations maintain proper security boundaries based on user roles

  This provides a much safer and more user-friendly bulk operation experience while maintaining the application's security model.
