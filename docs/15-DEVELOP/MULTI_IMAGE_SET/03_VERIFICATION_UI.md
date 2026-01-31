# Task 3: Verification and Grid Management UI

## 🖥️ User Interface
A new dashboard for "Set Verification" where Optometrists process uploaded encounters.

### 1. Grid Interaction
- **Display**: A 3x3 grid showing thumbnails of uploaded images.
- **Drag & Drop**: Allow re-ordering images if the mobile uploader made a mistake.
- **Empty Slots**: Visual indicators for missing cardinal positions.

### 2. Manual Anonymization (Manual Masking)
Instead of complex auto-masking, integrate the existing image editor:
- **Editor Flow**:
  1. Click thumbnail to open editor.
  2. Apply Crop/Black-out mask to PII (Patient names on charts, etc.).
  3. Save creates the `edited_filename` version.
- **Global Action**: "Mark All as Anonymized" once all images are processed.

### 3. Verification Action
- Once verified, set `PatientEncounters.verification_state = 'verified'`.
- Trigger `taskCreationServices.py` to generate the `GradingTask`.
