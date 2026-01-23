# Issue: Missing EXIF Stripping in Pre-graded Upload Route

## Description
The pre-graded upload route (`direct_uploads/pregraded.py`) currently writes image bytes directly to disk without performing EXIF stripping. This deviates from the standard security posture maintained in the Zip Ingestion and Direct Upload workflows.

## Impact
Images uploaded via the pre-graded route may still contain PII or sensitive technical metadata (GPS, camera serial numbers, patient names in EXIF comments). Since these uploads bypass the manual preprocessing dashboard, this metadata remains in the system indefinitely if not pre-cleaned.

## Proposed Fix
1.  Modify `direct_uploads/pregraded.py` to use `utils.image_processing.strip_exif_data()` before saving images.
2.  Update the `DirectImageUpload` record creation to ensure it references the cleaned data.
3.  Verify that thumbnail generation still functions correctly after stripping.

## Location
-   **File**: `direct_uploads/pregraded.py`
-   **Logic**: Inside the loop processing `files` (around line 215).

## Status
- [ ] Implement EXIF stripping in `pregraded.py`
- [ ] Verify metadata removal for sample pre-graded uploads
- [ ] Update `docs/02-Verify-Anonymize/EXIF-stripping.md` to remove from "Exceptions"
