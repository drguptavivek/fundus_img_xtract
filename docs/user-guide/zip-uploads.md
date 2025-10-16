# ZIP Archive Uploads

This guide explains how to upload ZIP archives containing retinal fundus images and reports to the system. ZIP uploads are ideal for batch uploads from Remedio camera systems and other sources that export data as ZIP archives.

## When to Use ZIP Uploads

ZIP uploads are designed for:
- Images from Remedio camera systems that export as ZIP archives
- Batch uploads containing multiple patient records
- Archives that include both images and PDF reports
- Large-scale data imports from screening programs

## REMEDIO Camera System Compatibility

The system is specifically optimized for Remedio-FOP camera systems:

### Supported REMEDIO Features
- **Direct ZIP Import**: Download ZIP files directly from the Remedio dashboard
- **Structured Data Extraction**: Automatically extracts patient information and metadata
- **PDF Report Processing**: Processes DR and Glaucoma screening reports included in ZIP files
- **Image Organization**: Automatically organizes images by patient and screening type

### REMEDIO ZIP Structure Requirements
- ZIP files downloaded from Remedio dashboard are fully compatible
- No manual restructuring of ZIP contents required
- System automatically detects and processes:
  - Fundus images (left/right eye)
  - DR screening PDF reports
  - Glaucoma screening PDF reports
  - Patient metadata and demographics

### Processing Workflow for REMEDIO ZIPs
1. **Download**: Export ZIP files from your Remedio dashboard
2. **Upload**: Select hospital/lab unit and upload ZIP file
3. **Automatic Extraction**: System processes all contents without manual intervention
4. **Data Verification**: Review extracted data for accuracy
5. **Image Anonymization**: PII is automatically hidden/removed from images
6. **Ready for Grading**: Processed images appear in grading queues

### Benefits of REMEDIO Integration
- **Time Saving**: Eliminates manual data entry
- **Accuracy**: Reduces transcription errors
- **Completeness**: Preserves all screening data and reports
- **Workflow Efficiency**: Seamless integration with existing Remedio workflow

### Troubleshooting REMEDIO Uploads
- **Corrupted ZIPs**: Re-download from Remedio dashboard
- **Missing Reports**: Verify all reports were included in the export
- **Data Extraction Errors**: Check Remedio dashboard for complete patient information
- **Processing Delays**: Large ZIP files may take longer to process

## Accessing ZIP Upload

1. Log in to the system with appropriate permissions
2. Navigate to `/upload_files`
3. This page is specifically for ZIP file uploads

## Upload Form Fields

- **Hospital**: Select from available hospitals (buttons shown as pills)
- **Lab Unit**: Choose from lab units associated with selected hospital
- **Files**: Select one or more .zip files (multi-file selection supported)

## File Requirements

- **Maximum file size**: Configurable via PER_FILE_MAX_BYTES (default 64MB)
- **Maximum files per upload**: Configurable via MAX_FILES_PER_UPLOAD (default 50)
- **Required format**: .zip files only
- **Security**: Files are scanned for malicious content

## Duplicate Handling in ZIP Uploads

The system handles duplicates differently for ZIP uploads:

### ZIP-Level Duplicate Prevention
- **ZIP Hash Check**: Each ZIP file is hashed to prevent uploading the same ZIP multiple times
- **Job Tracking**: ZIP processing jobs are tracked to prevent duplicate processing
- **Content Awareness**: System checks if ZIP contents have been previously processed

### File-Level Duplicate Handling
- **Image Duplicates**: Individual images within ZIPs are checked against existing images
- **MD5 Verification**: Each extracted image is hashed and compared to database
- **Selective Processing**: Only new images are added; duplicates are logged but skipped
- **Report Handling**: PDF reports are also checked for duplicates

### Duplicate Reporting
- **Processing Log**: Detailed log shows which files were duplicates
- **Summary Report**: Final report indicates number of duplicates found
- **Selective Success**: ZIP upload succeeds even if some contents are duplicates
- **Audit Trail**: All duplicate detection events are logged for reference

## ZIP Upload Process

1. Select hospital and lab unit
2. Choose one or more ZIP files from your computer
3. Click "Upload & Queue" to begin processing
4. System validates files and creates a job
5. You'll be redirected to job status page
6. Background processing extracts and organizes files

## ZIP Processing Workflow

1. **Validation**: Checks file format, size, and security
2. **Extraction**: Processes ZIP contents in background
3. **Organization**: Extracts patient information and organizes files
4. **Database Creation**: Creates appropriate database records
5. **File Storage**: Saves files to appropriate directories
6. **Duplicate Check**: Identifies and handles duplicate content
7. **Data Verification**: Validates extracted information
8. **Anonymization**: Applies privacy protection to images

## ZIP Structure Requirements

### Expected ZIP Contents
- **Images**: Fundus images in standard formats (JPG, PNG)
- **Reports**: PDF files containing screening results
- **Metadata**: Patient information and screening details
- **Organization**: Logical folder structure (if present)

### Supported Folder Structures
- **Flat Structure**: All files in root directory
- **Patient Folders**: Files organized by patient ID/name
- **Date Folders**: Files organized by screening date
- **Mixed Structure**: Combination of organization methods

### File Naming Conventions
- System is flexible with file naming
- Patient ID extraction from filenames when possible
- Date parsing from filename patterns
- Eye laterality detection (left/right) from naming

## Job Tracking

- **Job Token**: Unique identifier for tracking
- **Status Page**: Real-time updates on processing progress
- **Results**: Summary of processed files and any errors
- **Detailed Logs**: Comprehensive processing information

## ZIP Processing Details

### Extraction Process
1. **Security Scan**: ZIP file scanned for malicious content
2. **Structure Analysis**: System analyzes ZIP folder structure
3. **File Inventory**: Creates list of all files in ZIP
4. **Content Type Detection**: Identifies images, PDFs, and other files
5. **Metadata Extraction**: Pulls patient and screening information
6. **File Processing**: Processes each file according to its type

### Image Processing
- **Format Validation**: Ensures images are in supported formats
- **Quality Check**: Basic image quality assessment
- **Metadata Extraction**: Pulls EXIF data when available
- **Duplicate Check**: Compares against existing images
- **Storage**: Saves to appropriate storage location

### PDF Report Processing
- **OCR Extraction**: Text extraction from PDF reports
- **Data Structuring**: Organizes extracted information
- **Report Type Detection**: Identifies DR vs Glaucoma reports
- **Quality Assessment**: Checks for readable text
- **Database Storage**: Saves structured report data

### Data Verification
- **Cross-Reference**: Links images to corresponding reports
- **Validation**: Ensures data consistency
- **Quality Checks**: Verifies completeness of information
- **Error Reporting**: Logs any data inconsistencies

## Upload Quotas and Limits

### ZIP Upload Limits
- **Per-file size limit**: PER_FILE_MAX_BYTES (default 64MB)
- **Files per request**: MAX_FILES_PER_UPLOAD (default 50)
- **Format restriction**: Only .zip files accepted
- **Processing limits**: Background processing may have additional constraints

### Quota Tracking
- ZIP uploads count against user quotas
- Individual files within ZIP may have separate limits
- Administrators can adjust limits as needed
- Large ZIP files may require special permissions

## Managing ZIP Uploads

### Viewing Upload History
1. Go to "Upload" → "Uploaded ZIPs"
2. View list of all ZIP uploads
3. Check processing status and results
4. Access detailed job information

### ZIP Upload Dashboard
- **Upload Summary**: Overview of all ZIP uploads
- **Processing Status**: Current state of each upload
- **Error Reports**: Details of any processing issues
- **Success Metrics**: Statistics on successful processing

### Bulk Operations
- **Reprocess Failed ZIPs**: Retry processing for failed uploads
- **Delete Uploads**: Remove entire ZIP uploads and contents
- **Export Reports**: Generate reports on ZIP upload activity

## Data Verification and Review

### Verification Workflow
1. **Automatic Verification**: System validates extracted data
2. **Manual Review**: Users review extracted information
3. **Correction Process**: Update any incorrect data
4. **Approval**: Mark data as verified and complete

### Verification Tools
- **Data Preview**: Preview extracted information before finalizing
- **Edit Capabilities**: Correct extracted data as needed
- **Validation Checks**: System flags potential issues
- **Audit Trail**: Track all changes and verifications

## Image Anonymization

### Automatic Anonymization
- **PII Detection**: Identifies potential personally identifiable information
- **Text Blurring**: Blurs text regions that may contain sensitive data
- **Metadata Removal**: Strips EXIF data that could identify patients
- **Quality Preservation**: Maintains image quality for grading

### Manual Review
- **Anonymization Preview**: Review anonymized images before approval
- **Adjustment Tools**: Fine-tune anonymization settings
- **Override Options**: Mark regions as safe or needing anonymization
- **Quality Control**: Ensure images remain usable for grading

## Common ZIP Upload Issues

### ZIP File Issues
- **Corrupted ZIPs**: Files cannot be opened or read
- **Password Protection**: Password-protected ZIPs are not supported
- **Size Limits**: ZIP files exceeding size limits
- **Format Issues**: Non-standard ZIP formats

### Content Issues
- **Unsupported Files**: Files in unsupported formats
- **Missing Data**: Incomplete patient information
- **Corrupted Images**: Image files that cannot be read
- **PDF Reading Errors**: PDFs that cannot be processed

### Processing Issues
- **Time Outs**: Large ZIPs may exceed processing time limits
- **Memory Issues**: Very large ZIPs may exceed memory limits
- **Network Interruption**: Upload interrupted during transfer
- **Server Load**: High server load may slow processing

### Solutions
1. **Validate ZIPs**: Test ZIP files before uploading
2. **Check Contents**: Ensure all files are in supported formats
3. **Compress Appropriately**: Balance size and quality
4. **Stable Connection**: Use reliable internet connection
5. **Monitor Progress**: Watch processing status for issues

## Best Practices for ZIP Uploads

### Preparation
1. **Organize Content**: Structure ZIP contents logically
2. **Validate Files**: Ensure all files are valid and readable
3. **Check Size**: Verify ZIP files are within size limits
4. **Test Structure**: Test with small samples first
5. **Document Contents**: Keep track of ZIP contents

### During Upload
1. **Monitor Progress**: Watch processing status
2. **Check Errors**: Review any error messages promptly
3. **Verify Results**: Confirm processing completed successfully
4. **Record Job IDs**: Keep track of job tokens
5. **Validate Content**: Review extracted data

### After Upload
1. **Review Data**: Verify all information was extracted correctly
2. **Fix Issues**: Address any processing errors
3. **Verify Anonymization**: Check PII was properly hidden
4. **Update Records**: Make any necessary corrections
5. **Notify Team**: Inform relevant team members of completion

## Security Considerations

### Data Protection
- **Encryption**: All transfers are encrypted
- **Access Control**: Only authorized users can upload
- **Audit Trail**: All activities are logged
- **Secure Storage**: Files stored in secure environment

### Privacy Compliance
- **HIPAA Compliance**: Handles protected health information
- **Anonymization**: Automatic PII protection
- **Access Logs**: Detailed access tracking
- **Data Retention**: Appropriate data retention policies

## Getting Help with ZIP Uploads

### Error Messages
Common ZIP upload error messages:
- "Invalid ZIP format": Use standard ZIP format
- "ZIP file too large": Compress or split into smaller files
- "Corrupted ZIP file": Re-create ZIP file
- "Unsupported file in ZIP": Remove unsupported files
- "Processing timeout": Try with smaller ZIP file

### Troubleshooting Steps
1. **Check ZIP File**: Verify ZIP can be opened normally
2. **Validate Contents**: Ensure all files are supported
3. **Check Size**: Verify within size limits
4. **Review Structure**: Ensure logical organization
5. **Test Sample**: Try with smaller sample first

### Contact Support
If you need help with ZIP uploads:
1. Note the error message
2. Record the job ID and timestamp
3. Describe ZIP contents and structure
4. Include browser and device information
5. Contact your system administrator