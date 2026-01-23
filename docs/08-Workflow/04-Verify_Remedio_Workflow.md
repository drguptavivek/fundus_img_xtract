# Verify Remedio Workflow

This workflow handles the verification of data ingested from Remedio Zip files. It ensures that the OCR-extracted data and image metadata are accurate before the data is committed to the main clinical records.

```mermaid
sequenceDiagram
    participant User
    participant WebServer as Web Server (Flask)
    participant DB as Database
    participant TaskService as Task Service

    note right of User: Phase 1: List & Selection
    User->>WebServer: View Verification List (GET /verify_remedio/list)
    WebServer->>DB: Fetch Patient Encounters (Filter by LabUnit, Date)
    WebServer->>DB: Fetch Stats (DR, Glaucoma, Verified Counts)
    WebServer-->>User: Render List Page

    note right of User: Phase 2: Details & Edit
    User->>WebServer: Select Encounter (GET /verify_remedio/edit/<id>)
    WebServer->>DB: Fetch Encounter Details (Images, Reports, Cleaned Rows)
    WebServer-->>User: Render Edit Page

    note right of User: Phase 3: Correction
    User->>WebServer: Save Changes (POST /verify_remedio/edit/<id>/save)
    WebServer->>DB: Update Patient Details (ID, Date)
    WebServer->>DB: Update DR Reports (Results, Qualitative)
    WebServer->>DB: Update Glaucoma Results (VCDR, Qualitative)
    WebServer-->>User: Flash Success Message

    note right of User: Phase 4: Image Tagging
    User->>WebServer: Mark Eye Side/Centering (POST /edit/<id>/mark_eye)
    WebServer->>DB: Update EncounterFile (Eye Side, Centering)
    WebServer-->>User: Return Updated Status

    note right of User: Phase 5: Verification
    alt Verify DR
        User->>WebServer: Verify DR (POST .../verify/dr)
        WebServer->>DB: Check Image Tags
        WebServer->>DB: Mark DR Verified
        WebServer->>TaskService: Create Grading Tasks (DR)
    else Verify Glaucoma
        User->>WebServer: Verify Glaucoma (POST .../verify/glaucoma)
        WebServer->>DB: Check Image Tags
        WebServer->>DB: Mark Glaucoma Verified
        WebServer->>TaskService: Create Grading Tasks (Glaucoma)
    else Verify Encounter (NoDR)
        User->>WebServer: Verify Encounter (POST .../verify/encounter)
        WebServer->>DB: Check DR/Glaucoma Status (Must be verified if present)
        WebServer->>DB: Mark Encounter Verified
        WebServer->>TaskService: Create Grading Tasks (DR - if no reports)
        WebServer-->>User: Return Next Unverified URL
    end
```

## Key Components

1.  **List View**:
    -   Displays a paginated list of patient encounters from Remedio Zip uploads.
    -   Filters by date and verification status.
    -   Shows KPIs for the current day (DR, Glaucoma, Encounter counts).

2.  **Edit View**:
    -   Allows editing of patient ID, capture date, and specific report values (VCDR, DR results).
    -   **Image Tagging**: Critical step where users must tag eye laterality (Right/Left) and centering (Macula/Disk) before verification can proceed.

3.  **Verification Logic**:
    -   **Granular Verification**: DR and Glaucoma results are verified separately.
    -   **Encounter Verification**: The final step. It requires DR and Glaucoma to be verified first (if reports exist). If no DR reports exist, verifying the encounter treats it as a NoDR case (but still creates a DR grading task for safety).
    -   **Task Creation**: Upon verification, grading tasks are automatically created for the relevant diseases.

4.  **Unverification**:
    -   Allows reverting a verified status *only if* no grading tasks are already in progress.
    -   Removes any pending grading tasks associated with the encounter.
