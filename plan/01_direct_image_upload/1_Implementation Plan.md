## Implementation Plan (Revised) for Direct Image Uplaod feature

This plan has been updated to incorporate advanced associations between users, hospitals, and lab units, and to define distinct upload workflows for `contributor` and `data_manager` roles.

### Phase 1: Backend Development (Flask & SQLAlchemy)

1.  **Database Schema (`models.py`)**:
    -   **`DirectImageUpload` Table**: No changes from the previous plan.
    -   **Lookup Tables**:
        -   `Hospital`, `Camera`, `Disease`, `Area`: No changes.
        -   `LabUnit`: Add a `hospital_id` (Integer, FK to `hospitals.id`) to enforce the one-to-one mapping of a lab unit to a hospital.
    -   **New `user_lab_units` Association Table**: Create a new table to manage the many-to-many relationship between users and lab units.
        -   `user_id` (Integer, FK to `users.id`)
        -   `lab_unit_id` (Integer, FK to `lab_units.id`)
    -   **`User` Model**:
        -   Add `file_upload_quota` and `file_upload_count` columns as planned.
        -   Add a `lab_units` relationship using the `user_lab_units` association table.

2.  **User Roles & Permissions (`auth/roles.py`)**:
    -   Add the `'contributor'` role as planned.

3.  **Blueprint & Routes (`direct_uploads`, `admin`)**:
    -   **`direct_uploads` Blueprint**:
        -   `GET /direct/upload`: Renders the upload page.
        -   `POST /direct/upload`: Handles the role-specific upload logic.
        -   `GET /direct/list`: No changes.
    -   **New API Endpoints**:
        -   `GET /api/lab-units/<int:user_id>`: Returns the lab units for a given user.
        -   `GET /api/hospital/<int:lab_unit_id>`: Returns the hospital for a given lab unit.
    -   **`admin` Blueprint Additions**:
        -   New routes for managing each lookup table (e.g., `GET, POST /admin/hospitals`, `GET, POST /admin/hospitals/<id>/edit`, etc.). This will apply to `Hospitals`, `Cameras`, `Diseases`, `Areas`, and `LabUnits`.

4.  **Route Logic (`direct_uploads/routes.py`, `admin/routes.py`)**:
    -   The logic for `direct_uploads` remains as planned.
    -   New logic will be added to `admin/routes.py` to handle the full CRUD (Create, Read, Update, Delete) operations for the new master tables.

5.  **Database Migration (`scripts/setup_db.py`)**:
    -   Update the migration function to create the new `user_lab_units` table and add the `hospital_id` column to `lab_units`.

### Phase 2: Frontend Development (Jinja2 & JS)

1.  **Upload Template (`templates/direct_upload/upload.html`)**:
    -   No changes from the previous plan. The template will be role-aware.
2.  **Client-Side JavaScript (`static/js/direct-upload.js`)**:
    -   No changes from the previous plan. The script will handle the dynamic, role-based population of form fields.
3.  **New Admin Templates (`templates/admin/`)**:
    -   Create new templates for listing, creating, and editing each of the new lookup masters (`hospitals`, `cameras`, etc.).
    -   The template for creating/editing a `LabUnit` will include a dropdown to select its parent `Hospital`.

### Phase 3: Admin & Integration

1.  **Navigation (`templates/base.html`)**:
    -   Add a "Direct Upload" link as planned.
    -   Add a new "Admin" dropdown menu containing links to the new management pages for "Hospitals", "Lab Units", "Cameras", etc.

2.  **Admin Interface & Workflows**:
    -   **Master Data Management**:
        -   The new admin pages will provide full CRUD functionality for all lookup tables.
        -   The "Manage Lab Units" page will be the primary interface for associating a lab unit with a hospital.
    -   **User Management (`templates/admin/add_user.html`, `templates/admin/edit_user.html`)**:
        -   The "Add User" and "Edit User" forms will be updated.
        -   In addition to the quota input, a multi-select box will be added. This box will list all available `Lab Units`, allowing the admin to associate a user with one or more lab units.
        -   A user's associated hospital(s) will be implicitly determined by the hospital(s) linked to their assigned lab units. This information can be displayed as read-only text on the user edit page.

3.  **Testing**:
    -   Verify the `contributor` and `data_manager` upload workflows.
    -   Verify that admins can perform full CRUD operations on all new lookup tables.
    -   Confirm that the association between `LabUnit` and `Hospital` is enforced.
    -   Test the updated "Add User" and "Edit User" workflows, ensuring that lab unit associations are saved correctly.