# Multi-Image Set Workflow (e.g., Strabismus) - Overview

## 🎯 Objective
Implement a specialized workflow for diseases requiring multiple spatially-related images (like the 9-cardinal gaze positions for Strabismus). This system will support Android-based uploads via API, manual grid management, and synchronized grid grading.

## 🏗️ Architecture
The system transitions from "Image-Centric" to "Encounter-Centric" for specific diseases.

### Key Components
1. **PatientEncounter (Set Container)**: Serves as the primary bucket. For set-based diseases, the `GradingTask` links directly here.
2. **EncounterSetImage (New Model)**: Stores individual images within a set, including their spatial position (1-9).
3. **Android API (Ingestion)**: A JWT-secured endpoint for high-speed multi-image uploads.
4. **Verification Module**: A UI for Optometrists to verify positions and manually mask PII using the existing editor.
5. **Sync-Grid Viewer**: A synchronized 3x3 viewer for graders to assess the entire encounter at once.

## 🔄 Workflow Summary
1. **Ingestion**: Mobile app uploads 1-9 images with `disease_id` and metadata.
2. **Preprocessing**: Server strips EXIF, performs OCR checks, and generates thumbnails.
3. **Verification**: Optometrist confirms image positions and applies manual crops/masks.
4. **Task Creation**: System creates a single polymorphic `GradingTask` for the entire `PatientEncounter`.
5. **Grading**: Resident/Arbitrator views the 3x3 grid and submits a consolidated grade for the set.

## 📁 Document Index
- [01_SCHEMA_MODELS.md](01_SCHEMA_MODELS.md): Database changes and polymorphism.
- [02_API_INGESTION.md](02_API_INGESTION.md): Mobile API, JWT security, and metadata stripping.
- [03_VERIFICATION_UI.md](03_VERIFICATION_UI.md): Grid management and manual anonymization.
- [04_GRID_GRADING.md](04_GRID_GRADING.md): Set-based tasks and synchronized viewer.
- [05_CELERY_INTEGRATION.md](05_CELERY_INTEGRATION.md): Background processing for images and PII.
- [06_TEST_PLAN.md](06_TEST_PLAN.md): TDD strategy and test cases.
