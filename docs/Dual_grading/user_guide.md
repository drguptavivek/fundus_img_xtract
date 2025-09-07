# Dual Grading System - User Guide

## Overview

This guide provides instructions for using the Dual Grading System, which requires each image to be independently graded by both a resident and a consultant (ophthalmologist). This approach ensures quality control and provides valuable training opportunities for residents.

## User Roles

### 1. Residents
- Medical professionals in training with the 'resident' system role
- Can grade images from any source (Remedio ZIP files or direct uploads)
- Have access to all images for training purposes
- Their gradings are paired with consultant gradings for analysis

### 2. Consultants
- Experienced ophthalmologists with the 'ophthalmologist' system role
- For direct uploads, can only grade images from their own LabUnit
- For Remedio ZIP files, have access to all images
- Their gradings are paired with resident gradings for analysis

### 3. Administrators
- Users with the 'admin' system role
- Have unrestricted access to all images and grading functions
- Can perform grading as either role based on context

## Getting Started

### 1. Accessing the System
1. Log in to the Fundus Image Manager application
2. Navigate to the "Grading" section from the main menu
3. Select the appropriate grading interface based on image source:
   - "Start Glaucoma Grading" for Remedio ZIP file images
   - "Start DR Grading" for Remedio ZIP file images
   - "Start [Disease] Grading" for direct uploads

### 2. Grading Process
1. Review the image using the full-screen viewer with zoom and pan capabilities
2. Adjust brightness, contrast, and color filters as needed
3. Select the appropriate impression from the provided options
4. Add optional remarks in the remarks field
5. Click "Save & Next" to save the grading and proceed to another image, or "Save & Close" to save and return to the dashboard

## Dual Grading Workflow

### 1. Independent Grading
Each image must be graded independently by both a resident and a consultant:
- Residents provide their initial assessment of the image
- Consultants provide their expert assessment of the same image
- Both gradings are preserved for analysis and training purposes

### 2. Grading Status
The system tracks the grading status of each image:
- **Not Graded**: No gradings by either role
- **Resident Only**: Graded by resident but not consultant
- **Consultant Only**: Graded by consultant but not resident
- **Both Graded**: Graded by both resident and consultant

### 3. Save & Next Feature
The "Save & Next" feature prioritizes images for grading based on:
1. Images graded by the other role but not by the current user's role
2. Images not yet graded by any role
3. Random selection among eligible images

## Dual Grading Dashboard

### 1. Accessing the Dashboard
Navigate to the "Dual Grading" section from the main menu to access the dual grading dashboard.

### 2. Dashboard Features
The dual grading dashboard provides:
- **Statistics**: Overview of grading progress and completion rates
- **Paired Gradings**: List of images that have been graded by both resident and consultant
- **Discrepancy Analysis**: Analysis of images with different impressions from resident and consultant
- **Matching Dashboard**: Status of the matching process with manual trigger option

### 3. Inter-rater Reliability
The dashboard displays inter-rater reliability statistics:
- Overall agreement percentages between residents and consultants
- Detailed discrepancy analysis
- Kappa statistics for inter-rater reliability

## Matching Process

### 1. Automatic Matching
The system automatically identifies pairs of resident and consultant gradings every 2 hours:
- Images with gradings from both roles are flagged as "matched"
- Matched images are locked to prevent further edits to original gradings
- Consultants can perform arbitration on discrepant images

### 2. Locking Mechanism
Once an image is matched:
- It becomes locked for editing
- Original gradings cannot be modified
- A new arbitration grading can be added if needed
- The locking status is clearly displayed in the grading interface

### 3. Manual Matching Trigger
Administrators and consultants can manually trigger the matching process:
- Navigate to the "Matching" tab in the dual grading dashboard
- Click "Run Matching Process" to initiate matching immediately
- View statistics on the matching process progress

## Arbitration Workflow

### 1. Discrepancy Identification
Images with different impressions from resident and consultant are flagged as discrepant:
- Automatically identified after matching
- Displayed in the discrepancy analysis section of the dual grading dashboard
- Available for arbitration by consultants

### 2. Arbitration Process
Consultants can arbitrate discrepant images:
1. Navigate to the "Arbitration Dashboard" from the main menu
2. Review the discrepant image and compare resident and consultant impressions
3. Provide a final, arbitrated grade
4. The image is marked as arbitrated and disappears from the discrepancy list

### 3. Arbitration Status
The system tracks arbitration status:
- Images requiring arbitration are listed in the arbitration dashboard
- Once arbitrated, images are marked and removed from the discrepancy list
- Arbitration gradings are preserved separately from original gradings

## Best Practices

### For Residents
1. **Take Time**: Carefully evaluate each image before providing an impression
2. **Be Thorough**: Use all available image enhancement tools (zoom, brightness, contrast, filters)
3. **Document Uncertainty**: Use the remarks field to explain any uncertainties or unusual findings
4. **Seek Feedback**: Review discrepancy analysis to understand areas for improvement

### For Consultants
1. **Mentor Residents**: Use discrepancy analysis as teaching opportunities
2. **Be Consistent**: Apply the same grading criteria consistently across all images
3. **Perform Arbitration Promptly**: Address discrepant images in a timely manner
4. **Document Reasoning**: Use the remarks field to explain arbitration decisions

### For All Users
1. **Maintain Independence**: Grade images without knowledge of other gradings
2. **Follow Protocols**: Adhere to established grading protocols for each disease
3. **Report Issues**: Notify administrators of any technical problems or concerns
4. **Participate in Calibration**: Engage in calibration exercises to maintain consistency

## Troubleshooting

### Common Issues
1. **Cannot Edit Grading**: If you see a "locked" message, the image has been matched and cannot be edited
2. **No Images Available**: If "Save & Next" doesn't find images, all eligible images may have been graded
3. **Access Denied**: If you receive an access denied error, verify you have appropriate permissions

### Getting Help
Contact your system administrator for:
- Role assignment or permission issues
- Technical problems with the grading interface
- Questions about grading protocols or procedures
- Assistance with discrepancy analysis or arbitration

## Conclusion

The Dual Grading System provides a robust framework for ensuring quality control in clinical image grading while supporting resident education and training. By following the workflows and best practices outlined in this guide, users can maximize the benefits of the system while contributing to improved diagnostic accuracy and professional development.