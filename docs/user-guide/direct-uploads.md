# Direct Image Uploads

This guide explains how to upload individual retinal fundus images directly to the system. Direct uploads are ideal for single images or small batches from various camera systems.

## Accessing Direct Upload

1. Log in to the system with your uploader credentials
2. Click on "Upload" in the main menu
3. Select "Direct Upload" from the dropdown menu
4. Or navigate directly to `/direct/upload`

## Upload Form Fields

Complete the following information before uploading:

- **Hospital**: Select the hospital where the images were captured (buttons shown as pills)
- **Lab Unit**: Choose the specific unit or department (filtered based on hospital selection)
- **Camera**: Select the camera model used to capture the images
- **Disease**: Choose the primary disease being screened (DR, Glaucoma, AMD)
- **Area**: Select the anatomical area (left eye, right eye, or both)
- **Mydriatic**: Toggle between "Non Mydriatic" and "Mydriatic" based on whether mydriatic agents were used

## File Requirements

- **Supported formats**: JPG, JPEG, PNG (verified by MIME type checking)
- **Maximum file size**: 5MB per image (configurable via DIRECT_UPLOAD_MAX_FILE_SIZE_MB)
- **Maximum files per upload**: 100 images (configurable via DIRECT_UPLOAD_MAX_FILES)
- **Duplicate prevention**: System checks MD5 hash to prevent duplicate uploads

## Duplicate Handling

The system automatically prevents duplicate uploads:

### How Duplicates Are Detected
- **MD5 Hash Check**: Each uploaded file is hashed and compared against existing files
- **Content Comparison**: Files with identical content are identified as duplicates
- **Database Lookup**: System checks for existing files with the same hash

### Duplicate Prevention Process
1. When you select files, the system calculates MD5 hashes
2. Each hash is checked against the database
3. Duplicate files are flagged and prevented from upload
4. You'll receive a notification if duplicates are found
5. Only non-duplicate files proceed to upload

### Benefits of Duplicate Prevention
- **Storage Efficiency**: Prevents unnecessary storage usage
- **Data Integrity**: Ensures each image exists only once
- **Performance**: Improves database and storage performance
- **Audit Trail**: Clean record of unique images

## Upload Process

1. Select a hospital from the pill buttons at the top
2. Lab unit options will automatically filter based on selected hospital
3. Select lab unit, camera, disease, and area
4. Set mydriatic status using the toggle switch
5. Click "Choose Files" or drag and drop images onto the upload area
6. Review the file list to ensure all images are selected
7. Click "Upload Images" to begin the process
8. You'll be redirected to a processing page to track upload progress

## Upload Status and Processing

The system creates a job to track your upload:
- **Job Token**: Unique identifier for your upload batch
- **Processing Page**: Shows real-time status of each file
- **Results Page**: Displays successful uploads and any errors

## Viewing Upload Progress

After initiating an upload, you'll be automatically redirected to the processing page (`/direct/upload/processing/<job_id>`) where you can monitor progress in real-time:

### Processing Page Features
- **Job ID Display**: Shows the unique identifier for your upload batch
- **Overall Status Badge**: Indicates current job status (Processing, Completed, Error)
- **Progress Bar**: Visual representation of completion percentage
- **File Status List**: Detailed status for each individual file

### Real-Time Updates
- Page automatically refreshes every 3 seconds
- Progress bar updates as files are processed
- Individual file statuses change from:
  - **Queued**: File waiting to be processed
  - **Processing**: File currently being processed
  - **Completed**: File successfully uploaded
  - **Error**: File failed to upload

### Status Indicators
- **Blue Badge**: Processing in progress
- **Green Badge**: Successfully completed
- **Red Badge**: Error occurred
- **Gray Badge**: Queued and waiting

## Viewing Upload Results

Once processing completes (or if errors occur), you can view detailed results:

### Accessing Results
- Automatically redirected when processing completes
- Direct link: `/direct/upload/results/<job_id>`
- "View Results" button appears on completion

### Results Summary
- Overall job status (Completed/Error)
- Total files processed count
- Successfully uploaded files count
- Failed uploads count

### Error Details
For any failed uploads, the results page shows:
- **Filename**: Name of the file that failed
- **Error Reason**: Specific explanation of why it failed
  - "File too large (max 5MB)"
  - "Invalid file type: [mime_type]. Only JPG/PNG allowed."
  - "Duplicate file"
  - "Upload quota exceeded"
  - "No selected file"

## Job Management and Tracking

### Recent Jobs List
- Access via "Recent Jobs" link on upload pages
- Shows up to 100 most recent jobs
- Displays job creation time and status
- Shows rejection count for each job

### Job Status API
- Real-time status available at `/api/upload-jobs/<job_id>/status`
- Returns JSON with complete job details
- Used by processing page for live updates

### Job Details
- **Job Token**: Unique identifier for tracking
- **Status**: Current processing state
- **Items**: Array of all files with their statuses
- **Uploader Information**: User who initiated the upload
- **Timestamps**: Creation and completion times

## Troubleshooting Upload Jobs

### Common Job Issues

1. **Job Stuck in Processing**:
   - Jobs poll every 1.5-3 seconds for status updates
   - Manual refresh available with "Refresh now" button
   - Jobs may take longer for large batches
   - Processing continues in background even if browser closes
   - Contact admin if job shows "processing" for more than 30 minutes

2. **Partial Failures**:
   - Individual file failures don't stop processing of other files
   - Each file is processed independently
   - Review detailed error messages in job status page
   - Common errors: file corruption, invalid format, processing exceptions
   - Successfully processed files remain in system

3. **Complete Job Failure**:
   - Job status changes to "error" if critical failure occurs
   - Error message displayed in job status (e.g., "One or more files failed")
   - Check rejected summary for client-side validation failures
   - Verify form fields were complete and valid

### Job Status States
- **Queued**: Job created, waiting to start processing
- **Processing**: Actively processing files
- **Done**: All files processed successfully
- **Error**: Job failed during processing

### Error Recovery
- Individual file failures are isolated - other files continue processing
- Successfully uploaded files remain in system and are not affected
- Re-upload only the failed files with corrections
- Job records persist with full error details for troubleshooting
- Use the same job token to reference failed uploads when contacting support

## Managing Previous Uploads

1. Go to "Upload" → "Direct Upload Dashboard"
2. Use comprehensive filters to find specific uploads:
   - Date range (from/to)
   - Hospital, lab unit, camera, disease, area
   - Uploader (for admins/data managers)
   - Pre-graded status
3. View KPI cards showing upload statistics
4. Perform bulk operations on multiple files (max 50 at a time)

## Dashboard Features

### KPI Cards Display
- Total uploads (all time)
- Camera types with top 3 breakdown
- Diseases with top 3 breakdown
- Areas with top 3 breakdown

### Image Grid
- Thumbnail previews of uploaded images
- Toggle between original and edited versions (if available)
- Detailed metadata for each image
- Edit and grading revision options

### Bulk Operations
- Edit multiple files simultaneously
- Delete multiple files
- Select all visible uploads

## Upload Quotas and Limits

### Direct Upload Limits
- **Lifetime upload quota**: Configurable via MAX_FILES_PER_UPLOAD (default 50)
- **Per-request limit**: DIRECT_UPLOAD_MAX_FILES (default 100)
- **File size limit**: DIRECT_UPLOAD_MAX_FILE_SIZE_MB (default 5MB)
- **MIME type checking**: Only image/jpeg and image/png allowed

### Quota Tracking
- User's file_upload_count tracks total uploads
- Quota exceeded messages prevent further uploads
- Administrators can adjust limits as needed

## Image Editing Features

### Direct Upload Image Editing
1. From the dashboard, click "Edit Image" on any upload
2. Access image editing tools (if not pre-graded)
3. Make adjustments to image quality or orientation
4. Save edited version alongside original
5. Toggle between original and edited versions in dashboard

### Metadata Editing
1. Click "Edit" on any upload in the dashboard
2. Modify hospital, lab unit, camera, disease, area
3. Update mydriatic status
4. Save changes to update database records

## Best Practices

### Before Uploading
1. **Verify image quality**: Ensure images are clear and properly focused
2. **Check file formats**: Use only supported formats (JPG, JPEG, PNG)
3. **Organize files**: Group related images together
4. **Check for duplicates**: Review existing uploads to avoid duplicates
5. **Check quotas**: Verify you haven't exceeded your upload limits

### During Upload
1. **Stable connection**: Use a reliable internet connection
2. **Avoid interruptions**: Don't close the browser during upload
3. **Monitor progress**: Watch the status indicators on processing page
4. **Record job tokens**: Note job IDs for reference

### After Upload
1. **Verify results**: Check that all files uploaded successfully
2. **Review errors**: Investigate any failed uploads on results page
3. **Update records**: Make any necessary corrections to metadata
4. **Notify relevant staff**: Inform team members when uploads are complete

## Common Upload Issues

### File Rejection
Files may be rejected for these reasons:
- Unsupported file format (not JPG/JPEG/PNG)
- File size exceeds configured limits
- Corrupted or damaged files
- Duplicate content (same MD5 hash)
- Invalid MIME type detected

### Upload Failures
Common causes of upload failures:
- Unstable internet connection
- Browser timeout
- Server maintenance
- Exceeded quota limits
- Missing required form fields
- Invalid hospital/lab unit combination

### Solutions
1. **Check file requirements**: Verify format and size limits
2. **Stable connection**: Use wired connection if possible
3. **Smaller batches**: Upload fewer files at once
4. **Clear browser cache**: Remove old data
5. **Try different browser**: Test with an alternative browser
6. **Check permissions**: Ensure you have access to selected lab unit

## Viewing Uploaded Images

### Accessing Your Uploads
1. Go to "Upload" → "Direct Upload Dashboard"
2. Use filters to find specific images
3. Click on any image thumbnail to view details
4. Use the image viewer to zoom and examine

### Image Display Options
- **Thumbnail Grid**: Visual overview of all uploads
- **Original/Edited Toggle**: Switch between versions if edited
- **Detailed Metadata**: Comprehensive information about each upload
- **Grading Status**: See if images have been graded

### Editing Image Information
1. Select an image from the dashboard
2. Click "Edit" to modify metadata
3. Update any necessary fields
4. Save your changes

### Deleting Images
1. Select one or more images using checkboxes
2. Click "Delete Selected" from the action menu
3. Confirm the deletion
4. Note: Deleted images cannot be recovered

## Security Considerations

### Data Privacy
- All uploads are encrypted during transmission
- Patient information is protected according to HIPAA guidelines
- Access is restricted to authorized users only
- Upload metadata includes IP address and user agent for auditing

### Audit Trail
- All upload activities are logged with user information
- Changes to metadata are tracked with timestamps
- Job tokens provide traceability for batch operations
- File hash verification ensures data integrity

## Getting Help with Uploads

### Error Messages
Common error messages and their meanings:
- "File format not supported": Use JPG, JPEG, or PNG files
- "File size exceeds limit": Compress images or use smaller files
- "Upload quota exceeded": Contact administrator to increase quota
- "Duplicate file detected": File already exists in system
- "All fields are required": Complete all form fields before uploading
- "You don't have access to the selected lab unit": Choose a lab unit assigned to you

### Contact Support
If you need help with uploads:
1. Note the error message
2. Record the job ID and timestamp
3. Describe the steps you took
4. Include browser and device information
5. Contact your system administrator