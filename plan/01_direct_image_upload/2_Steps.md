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
