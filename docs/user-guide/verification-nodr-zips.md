# Verification of No-DR ZIPs

This guide explains the verification process for ZIP archives that contain fundus images but lack Diabetic Retinopathy (DR) screening reports. The system identifies these as "noDR" encounters and provides a separate verification workflow to ensure these images are properly processed for DR grading.

## Overview

The noDR verification process handles ZIP files from REMEDIO camera systems that contain fundus images but do not include DR screening reports. These encounters still contain valuable images that need to be made available for DR grading, and this verification process ensures they are properly integrated into the grading workflow.

Key points about noDR verification:
- Identifies ZIP archives with images but without DR reports
- Allows manual verification of image laterality before grading
- Creates DR grading tasks for verified encounters
- Provides separate workflow from standard DR/Glaucoma verification

## Accessing noDR Verification

### Required Permissions
- **Admin**: Full access to all noDR verification tools
- **Data Manager**: Access to encounters within assigned lab units
- **Optometrist**: Access to verification for assigned encounters

### Navigation Path
1. Log in to the system
2. Navigate to **Verify No-DR** in the main menu (or directly to `/verify_remedio_nodr/list`)
3. View the list of noDR encounters organized by date
4. Click on any encounter to view or edit details

## noDR Verification Process

### Step 1: Locate noDR Encounters
1. In the noDR verification list, browse encounters by date
2. Use filters to show:
   - **All encounters**: All noDR encounters regardless of verification status
   - **Verified only**: Only encounters that have been verified
   - **Unverified only**: Only encounters awaiting verification (default)
3. Click "Recent Unverified" to jump to the latest date with unverified encounters

### Step 2: Review Encounter Details
When viewing an encounter, check:
- **Patient Information**: ID, examination date
- **Images**: All fundus images included in the encounter
- **Lab Unit**: Hospital and lab unit where images were captured
- **ZIP Source**: The original ZIP file that contained these images

### Step 3: Edit Encounter Information
In edit mode, you can:
- Update patient ID if needed
- Correct capture date if it's inaccurate
- Review all images associated with the encounter

### Step 4: Tag Image Laterality
This is a critical step before verification:
1. In the edit view, locate each image
2. Select the appropriate laterality for each image:
   - **Right**: Right eye (OD)
   - **Left**: Left eye (OS)
   - **Cannot Tell**: When laterality cannot be determined
3. The system saves your selection automatically

### Step 5: Verify the Encounter
After ensuring all information is correct and all images are tagged:
1. Click the **Verify** button
2. The system will:
   - Mark the encounter as verified
   - Record who verified it and when
   - Automatically create DR grading tasks for all images
   - Add images to the DR grading queue

## Image Laterality Tagging

### Why It's Important
- Ensures proper image identification for grading
- Required before verification can be completed
- Helps DR graders understand which eye they're evaluating
- Critical for accurate diagnosis and treatment planning

### How to Tag Images
1. In the edit view, locate each image
2. Select the appropriate laterality from the dropdown:
   - **Right**: Right eye (OD)
   - **Left**: Left eye (OS)
   - **Cannot Tell**: When laterality cannot be determined
3. The system saves your selection automatically
4. Continue for all images in the encounter

### Verification Requirements
- All images must be tagged with laterality before verification
- The system will prevent verification if any images are untagged
- You'll see a warning message indicating how many images still need tagging

## Verification Status Management

### Verifying Encounters
- Marks the encounter as reviewed and approved for DR grading
- Creates DR grading tasks for all images
- Records verifier identity and timestamp
- Makes images available in the DR grading queue

### Unverifying Encounters
- Removes verification status
- Deletes pending DR grading tasks (only if tasks are still pending)
- Allows for corrections and re-verification
- Requires appropriate permissions

### Verification History
- System tracks who verified each encounter
- Timestamps are recorded for audit purposes
- Recent verification history is available for each user

## Common noDR Verification Issues

### Missing Image Laterality
- **Symptom**: System prevents verification with message about untagged images
- **Solution**: Tag all images with appropriate laterality before verifying

### Unable to Unverify Encountered
- **Symptom**: Unverify button unavailable or action fails
- **Reason**: Some grading tasks have progressed beyond "pending" status
- **Solution**: Tasks that are in progress or completed cannot be unverified through this process

### Encounter Access Errors
- **Symptom**: Cannot access specific encounters
- **Reason**: User does not have permissions for the lab unit
- **Solution**: Contact administrator to adjust permissions or verify assignment

## Navigation and Organization

### Date-Based Organization
- Encounters are organized by capture date
- Most recent dates appear first
- Pagination available for dates with many encounters

### Quick Navigation
- Use "Recent Unverified" link to jump to the latest unverified encounters
- Previous/Next buttons for navigating between encounters
- Back to list option to return to date selection

## Quality Control

### Before Verification
1. Confirm patient information is accurate
2. Ensure all images are of adequate quality
3. Verify that image laterality is correctly tagged
4. Check that encounter belongs to the correct lab unit

### After Verification
1. Verify that grading tasks appear in the DR queue
2. Confirm that all images are accessible to graders
3. Check that image metadata is preserved

## Troubleshooting

### Verification Won't Complete
- **Check all images are tagged**: Ensure every image has a laterality assignment
- **Review patient ID**: Verify patient ID is correctly formatted
- **Check date format**: Confirm capture date is valid

### Images Not Appearing in DR Queue
- **Verify process completed**: Confirm verification was successful
- **Check disease assignment**: System creates DR tasks specifically
- **Validate permissions**: Ensure graders have access to the images

### Cannot Unverify Encounter
- **Check task status**: If any grading tasks have moved beyond "pending", unverification is blocked
- **Contact administrator**: For system issues preventing unverification

## Best Practices

1. **Review all images** before starting the verification process
2. **Verify laterality carefully** as this significantly impacts grading accuracy
3. **Use consistent patient ID formats** across all encounters
4. **Process noDR encounters promptly** to maintain workflow efficiency
5. **Document any anomalies** in patient data for follow-up