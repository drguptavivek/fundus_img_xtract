# Task 4: Sync-Grid Grading Viewer

## 👁️ Consolidated Viewer
Graders need to see the "Big Picture" for diseases like Strabismus.

### 1. Synchronized Interaction
- **Sync-Zoom/Pan**: When the grader zooms in on Position 5 (Primary Gaze), all other 8 images must zoom/pan to the same relative coordinates.
- **Toggle Sync**: Allow breaking synchronization if specific detail is needed on one image.

### 2. Consolidated Grading Logic
- **Single Task**: One task per encounter set.
- **Grades**: Submission applies to the entire `patient_encounter_id`.
- **Not Gradable**: If one critical image is missing or poor quality, allow marking the set as "Not Gradable".

### 3. Media Serving
- Update `media/routes.py` to serve `EncounterSetImage` by UUID.
- Priority: Always serve `edited_filename` if it exists, otherwise `original_filename`.
