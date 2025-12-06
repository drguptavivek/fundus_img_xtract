# Direct Image Editing

This guide explains how to edit directly uploaded fundus images to remove or obscure patient information and improve image quality for grading.

## Overview

The image editing tool allows users to modify directly uploaded images to protect patient privacy and enhance image clarity. This is particularly important when images contain visible patient identifiers or require adjustments for optimal grading.

## Accessing Image Editing

### Required Permissions
- **Admin**: Full access to edit all images
- **Data Manager**: Can edit images within assigned lab units
- **File Uploader**: Can edit images they uploaded
- **Optometrist**: Can edit images based on permissions

### Navigation Path
1. Log in to the system
2. Navigate to **Direct Uploads** in the main menu
3. Select the image you want to edit
4. Click the **Edit** button in the image toolbar

## Image Editing Tools

### Available Tools
- **Brush**: Draw on the image to cover or highlight areas
- **Eraser**: Remove edits to restore original image areas
- **Crop**: Select an elliptical area to keep, removing everything else

### Tool Controls
- **Brush Size**: Adjust the size of the brush/eraser (1-50 pixels)
- **Brush Color**: Select color for the brush tool
- **Undo/Redo**: Navigate through editing history
- **Clear**: Remove all edits and restore original image

## Step-by-Step Editing Workflow

### Step 1: Open the Image Editor
1. Locate the image in Direct Uploads
2. Click the **Edit** button
3. The editor will load with the image displayed

### Step 2: Choose Your Tool
1. Select the appropriate tool for your task:
   - **Brush** for covering patient information
   - **Eraser** for correcting mistakes
   - **Crop** for focusing on specific areas

### Step 3: Make Your Edits
- **For Brush/Eraser**: Click and drag to draw on the image
- **For Crop**: Click and drag to create an elliptical selection

### Step 4: Review and Save
1. Use the preview to check your edits
2. Save the edited version when satisfied
3. The original image is preserved separately

## Common Editing Use Cases

### Removing Patient Information
- **Text Overlays**: Use the brush tool to cover patient names or IDs
- **Barcode Labels**: Cover or remove barcode labels
- **Date Stamps**: Obscure examination dates if needed
- **Institution Information**: Cover hospital or clinic names

### Improving Image Quality
- **Cropping**: Focus on the relevant anatomical structures
- **Removing Artifacts**: Cover dust spots or reflections
- **Enhancing Clarity**: Crop to eliminate peripheral distractions

### Privacy Protection
- **Face Protection**: Cover any visible facial features
- **Identifier Removal**: Obscure any unique identifying marks
- **Metadata Considerations**: Note that editing doesn't affect metadata

## Cropping Tool Details

### Creating a Crop Selection
1. Select the **Crop** tool
2. Click and drag on the image to create an ellipse
3. Adjust the size by dragging the handles

### Moving the Selection
- Click inside the ellipse and drag to move it
- Use the handles to resize the selection

### Applying the Crop
1. Click **Apply Crop** when satisfied with the selection
2. Everything outside the ellipse will be removed
3. The cropped image becomes the new base for further editing

## Editing Restrictions

### When Editing Is Blocked
- If grading tasks are already in progress for the image
- If the image is locked by another user
- If you don't have sufficient permissions

### Error Messages
- "Editing blocked. Grading tasks already in progress"
- "You don't have permission to edit this upload"
- "Image file not found on server"

## Saving and Managing Edits

### Saving Changes
1. Click **Save Image** to store your edits
2. The system creates an edited version alongside the original
3. A success message confirms the save

### Restoring Original
1. Click **Restore Original** to revert to the unedited image
2. This deletes the edited version permanently
3. The original image becomes the active version again

### Edit History
- The system maintains a record of editing sessions
- Original and edited versions are tracked separately
- Access to editing is logged for audit purposes

## Best Practices for Image Editing

### Before Editing
1. Identify all areas that need modification
2. Plan your editing approach
3. Ensure you have sufficient permissions

### During Editing
1. Use appropriate brush sizes for the task
2. Work systematically to avoid missing areas
3. Use undo if you make mistakes
4. Zoom in for precise work on small areas

### After Editing
1. Review the entire image carefully
2. Ensure all patient information is obscured
3. Verify that clinical information remains intact
4. Save when satisfied with the result

## Quality Considerations

### Maintaining Clinical Value
- Preserve all relevant anatomical structures
- Don't obscure pathology while removing identifiers
- Keep image quality sufficient for grading

### Privacy Protection
- Ensure all patient identifiers are completely obscured
- Check for reflected information in the eye
- Consider indirect identifiers (room numbers, etc.)

## Troubleshooting Common Issues

### Tool Not Working
- Check if editing is locked due to grading tasks
- Verify you have the necessary permissions
- Try refreshing the page

### Edits Not Visible
- Ensure you're using a contrasting color
- Check brush size isn't too small
- Verify you're on the correct layer

### Cannot Save
- Check your internet connection
- Verify the session hasn't timed out
- Try refreshing and re-applying edits

### Crop Not Applying
- Ensure the selection is completely within the image
- Check that the crop area isn't too small
- Try creating a new selection

## Integration with Grading Workflows

### Edited Images in Grading
- Graders see the edited version by default
- Original images are preserved for reference
- Edit status is indicated in the grading interface

### Quality Assurance
- Review edits before submitting for grading
- Ensure edits don't interfere with grading accuracy
- Document any unusual modifications

## Security and Privacy

### Access Control
- Only authorized users can edit images
- Edit access is logged for audit purposes
- Original images are preserved for reference

### Privacy Compliance
- Editing helps ensure compliance with privacy regulations
- Audit trails demonstrate privacy protection measures
- Access is restricted based on user roles

## Technical Limitations

### File Format Support
- Works with standard image formats (JPEG, PNG)
- Large images may load more slowly
- Very high resolutions may impact performance

### Browser Compatibility
- Works best with modern browsers
- Requires JavaScript to be enabled
- Touch devices support basic editing

## Contact Support

For editing issues:
- Check the troubleshooting section
- Contact your system administrator
- Report specific problems through the support channel
- Request additional training if needed