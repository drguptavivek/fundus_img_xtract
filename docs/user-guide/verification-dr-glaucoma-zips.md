# Verification of DR/Glaucoma ZIPs

This guide explains the verification process for Diabetic Retinopathy (DR) and Glaucoma ZIP archives uploaded from REMEDIO and compatible camera systems.

## Overview

After ZIP files are uploaded and processed, they create patient encounters with DR and/or Glaucoma reports. The verification process ensures that all screening data is properly captured, validated, and made available for grading.

## Accessing Verification Tools

### Required Permissions
- **Admin**: Full access to all verification tools
- **Data Manager**: Access to encounters within assigned lab units
- **Optometrist**: Access to verification for assigned encounters

### Navigation Path for DR Verification
1. Log in to the system
2. Navigate to **Verify DR** in the main menu
3. View the list of DR reports organized by date
4. Click on any report to view or edit details

### Navigation Path for Glaucoma Verification
1. Log in to the system
2. Navigate to **Verify Glaucoma** in the main menu
3. View the list of Glaucoma results organized by date
4. Click on any result to view or edit details

## DR Verification Process

### Step 1: Locate DR Reports
1. In the DR verification list, browse reports by date
2. Use filters to show:
   - All reports
   - Only verified reports
   - Only unverified reports
3. Click "Recent Unverified" to jump to the latest date with unverified reports

### Step 2: Review Report Details
When viewing a DR report, check:
- **Patient Information**: ID, examination date
- **Report Results**: Qualitative and quantitative results
- **Images**: All fundus images included in the encounter
- **PDF Reports**: The original DR screening report

### Step 3: Edit Report Information
In edit mode, you can:
- Update patient ID
- Modify capture date
- Adjust result values
- Mark image laterality (right/left/cannot tell)

### Step 4: Verify the Report
After ensuring all information is correct:
1. Click the **Verify** button
2. The system will:
   - Mark the encounter as verified
   - Record who verified it and when
   - Automatically create grading tasks for all images
   - Add images to the DR grading queue

## Glaucoma Verification Process

### Step 1: Locate Glaucoma Results
1. In the Glaucoma verification list, browse results by date
2. Use filters to show:
   - All results
   - Only verified results
   - Only unverified results
3. Click "Recent Unverified" to jump to the latest date with unverified results

### Step 2: Review Result Details
When viewing a Glaucoma result, check:
- **Patient Information**: ID, examination date
- **VCDR Values**: Vertical Cup-to-Disc Ratio for right and left eyes
- **Report Results**: Qualitative and quantitative results
- **Images**: All fundus images included in the encounter
- **PDF Reports**: The original Glaucoma screening report

### Step 3: Edit Result Information
In edit mode, you can:
- Update patient ID
- Modify capture date
- Adjust VCDR values (numeric format)
- Update result classifications
- Mark image laterality (right/left/cannot tell)

### Step 4: Verify the Result
After ensuring all information is correct:
1. Click the **Verify** button
2. The system will:
   - Mark the encounter as verified
   - Record who verified it and when
   - Automatically create grading tasks for all images
   - Add images to the Glaucoma grading queue

## Image Laterality Tagging

### Why It's Important
- Ensures proper image identification for grading
- Required before verification can be completed
- Helps graders understand which eye they're evaluating

### How to Tag Images
1. In the edit view, locate each image
2. Select the appropriate laterality:
   - **Right**: Right eye (OD)
   - **Left**: Left eye (OS)
   - **Cannot Tell**: When laterality cannot be determined
3. The system saves your selection automatically

### Verification Requirements
- All images must be tagged with laterality before verification
- The system will prevent verification if any images are untagged
- You'll see a warning message if images need tagging

## Verification Status Management

### Verifying Encounters
- Marks the encounter as reviewed and approved
- Creates grading tasks for all images
- Records verifier identity and timestamp
- Makes images available in the grading queue

### Unverifying Encounters
- Removes verification status
- Deletes pending grading tasks (only if tasks are still pending)
- Allows for corrections and re-verification
- Requires appropriate permissions

### Verification History
- System tracks who verified each encounter
- Timestamps are recorded for audit purposes
- Recent verification history is available for each user

## Common Verification Issues

### Missing Image Laterality
- **Symptom**: System prevents verification with message about untagged images
- **Solution**: Tag all images with appropriate laterality before verifying

### Invalid Data Values
- **Symptom**: System rejects invalid VCDR values or other data
- **Solution**: Ensure all numeric values are within valid ranges

### Access Denied
- **Symptom**: Cannot access verification for certain encounters
- **Solution**: Check that you have permissions for the lab unit

### Tasks Already in Progress
- **Symptom**: Cannot unverify because grading has started
- **Solution**: Contact graders to complete or release tasks

## Best Practices for Verification

1. **Systematic Review**: Follow the same review process for each report
2. **Image Quality Check**: Ensure images are clear and show required structures
3. **Data Validation**: Double-check all numeric values and classifications
4. **Complete Tagging**: Tag all images before attempting verification
5. **Documentation**: Add notes for any unusual findings or issues

## Integration with Grading Workflows

### Automatic Task Creation
- Verification automatically creates grading tasks
- Tasks are assigned to the appropriate disease (DR or Glaucoma)
- All images in the encounter receive grading tasks

### Quality Assurance
- Verified encounters have priority in grading queues
- Verification status is visible to graders
- Graders can access verification details for context

## Data Cleaning (Glaucoma Only)

The Glaucoma module includes a data cleaning workflow:
- Extracts numeric VCDR values from text fields
- Stores cleaned values in a separate table
- Maintains original values for reference
- Provides metrics on cleaning effectiveness

## Reporting and Analytics

### Verification Statistics
- Track verification progress by date
- Monitor unverified report backlogs
- View individual verification history

### Quality Metrics
- Image tagging completion rates
- Data validation error rates
- Verification processing times

## Security and Compliance

- **Access Control**: Only authorized users can verify reports
- **Audit Trail**: All verification actions are logged
- **Data Integrity**: Verification status ensures data consistency
- **Privacy Controls**: Patient data is handled according to regulations

## Contact Support

For verification issues:
- Check the troubleshooting section in this guide
- Contact your system administrator
- Report specific problems through the support channel
- Request additional training if needed