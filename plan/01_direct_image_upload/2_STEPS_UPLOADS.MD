

DEVELOP.  **Blueprint & Routes (`direct_uploads`, `admin`)**:
    -   **`direct_uploads` Blueprint**:
        -   `GET /direct/upload`: Renders the upload page.
        -   `POST /direct/upload`: Handles the role-specific upload logic. ADD SECURITY. COLLECT LIST OF EXCLUDED FILE NAMES WITH REASON. Uplaoded success files are placed in sub-directories by /YYYY_MM_DD/ of upload. Duplicate files go to a dup_SubDir /YYYY_MM_DD/dup_userId
        -   `/direct/upload/status`: Renders the RESULTS OF the POST /direct/upload. Redirection after uplaod complete. Show number of files uplaodsd numbers of files not uplaoded and names of files not uplaoded with reasons
        
        -   `GET /direct/list`: PAGINATED LIST OF FILES UPLOADED BY USER. Recent to old. 50 per page

    -   **New API Endpoints**:
        -   `GET /api/lab-units/<int:user_id>`: Returns the lab units for a given user.
        -   `GET /api/hospital/<int:lab_unit_id>`: Returns the hospital for a given lab unit.

DEVELOP TEMPLATES
1.  **Upload Template (`templates/direct_upload/upload.html`)**:
    -   No changes from the previous plan. The template will be role-aware.
2.  **Client-Side JavaScript (`static/js/direct-upload.js`)**:
    -   No changes from the previous plan. The script will handle the dynamic, role-based population of form fields.