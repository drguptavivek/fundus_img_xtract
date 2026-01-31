# Task 2: Mobile API Ingestion

## 🔐 Authentication & Scoping
- **Mechanism**: JWT (JSON Web Token).
- **Claims**:
  - `hospital_id`: Assigned hospital.
  - `lab_unit_id`: Assigned lab unit.
  - `allowed_diseases`: List of IDs permitted for this token.
- **Middleware**: Validate JWT and verify that requested `disease_id` is in the allowed list.

## 🚀 Upload Endpoint
**URL**: `/api/v1/encounter-set/upload`
**Method**: POST (Multipart/Form-Data)

### Payload Parameters:
- `disease_id`: Mandatory.
- `patient_id`: (MRN/UHID).
- `patient_name`: (Optional, will be masked).
- `images[]`: Array of files.
- `positions[]`: Array of integers (1-9) matching the images array.

### Processing Logic:
1. **Metadata Stripping**: Use `Pillow` to strip EXIF/IPTC tags immediately.
2. **File Storage**: Save to `files/encounter_sets/YYYY_MM_DD/`.
3. **Database**:
   - Create/Find `PatientEncounter`.
   - Create `EncounterSetImage` records.
4. **Thumbnails**: Generate 200px thumbnails for the grid preview.
5. **PII Check**: Run basic OCR on the image to flag potential text leakage.
