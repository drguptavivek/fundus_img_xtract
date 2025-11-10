# ZIP Upload Workflow - Comprehensive Guide

## Overview

The Fundus Image Manager supports processing ZIP archives from Remedio FOP cameras containing retinal fundus images and PDF reports. The workflow handles secure ingestion, validation, extraction, OCR processing, and database population.

## Current Implementation

### 1. Upload Process

**Entry Points:**
- `/upload_files` - Upload form for authorized users
- `/upload` - POST endpoint for file processing

**Access Control:**
- Roles: `admin`, `fileUploader`
- File size limits: 64MB per file (configurable)
- Maximum files: 50 per upload (configurable)

**File Validation:**
- ZIP file extension required
- MD5 hash calculation for duplicate detection
- Rejection of macOS resource fork files (._*)
- Metadata recording with uploader information

### 2. Background Processing

**Job Creation:**
- Database job entry created for each upload
- Background processing queued
- Status tracking via Job and JobItem models

**Security Validation:**
- Path traversal protection (blocks ../ and absolute paths)
- File type allowlist (.pdf, .jpg, .jpeg only)
- Magic byte verification for content validation
- Malicious file detection and deletion

### 3. ZIP Extraction Process

**Main Processing Function:** `process_zip_file(zip_path, session)`

**Workflow Steps:**

1. **Duplicate Detection:**
   - Calculate MD5 hash of ZIP file
   - Check database for existing hash
   - Move duplicates to `dupmd5` directory with date stamp

2. **Security Validation:**
   - Extract file list from ZIP
   - Validate file extensions against allowlist
   - Check for path traversal attempts
   - Verify file content with magic bytes
   - Delete malicious files and log attempts

3. **Metadata Extraction:**
   - Identify primary data directory
   - Parse patient information from directory name format: `PatientName_PatientID_CaptureDate`
   - Extract patient ID, name, and capture date

4. **File Processing:**
   - Extract allowed files to appropriate directories
   - Rename files to standardized format: `{patient_id}_{name}_{capture_date}_{original_filename}`
   - Images → `files/images/`
   - PDFs → `files/pdfs/`

5. **Database Operations:**
   - Create ZipFile record with MD5 hash and metadata
   - Create PatientEncounters record with parsed metadata
   - Create EncounterFile records for each image with UUID generation
   - Create EncounterFilePDF records for each PDF with UUID generation
   - Link all records to organizational structure (Hospital, LabUnit)

6. **File Management:**
   - Success: Move ZIP to `files/processed/`
   - Processing Error: Move ZIP to `files/processing_error/`
   - Malicious: Delete ZIP file immediately

### 4. OCR Processing

**PDF Processing:**
- Extract text from PDF reports using OCR
- Parse structured data for DR and Glaucoma reports
- Create corresponding database records (DiabeticRetinopathyReport, GlaucomaReport)
- Store extracted data with linking to patient encounters

### 5. Task Creation

**Grading Task Generation:**
- Create GradingTask records for eligible images
- Link tasks to diseases and lab units
- Initialize task state as 'pending'
- Support for multiple disease grading per image

## Database Schema Integration

### Key Models Involved

1. **ZipFile** - Tracks uploaded ZIP archives
2. **PatientEncounters** - Patient visit/session data
3. **EncounterFile** - Individual image files
4. **EncounterFilePDF** - PDF report files
5. **DiabeticRetinopathyReport** - Structured DR report data
6. **GlaucomaReport** - Structured Glaucoma report data
7. **GradingTask** - Tasks created for grading workflows
8. **Job/JobItem** - Background processing tracking

### Data Flow

```
ZIP Upload → Security Validation → Extraction → OCR → Database Population → Task Creation
```

## Configuration

**Environment Variables:**
- `PER_FILE_MAX_BYTES`: Max file size (default: 64MB)
- `MAX_FILES_PER_UPLOAD`: Max files per upload (default: 50)
- `UPLOAD_DIR`: Upload directory location
- `POSTGRES_*`: Database connection settings

**File Organization:**
- `uploads/`: Incoming ZIP files
- `files/processed/`: Successfully processed ZIPs
- `files/processing_error/`: Failed processing ZIPs
- `files/images/`: Extracted image files
- `files/pdfs/`: Extracted PDF files
- `dupmd5/`: Duplicate ZIP files by date

## Security Features

### Upload Security
- File type validation
- Size limits enforcement
- Metadata logging (uploader, IP, timestamp)
- CSRF protection

### Processing Security
- Path traversal protection
- Magic byte verification
- Malicious file detection
- Comprehensive audit logging

### Data Integrity
- MD5 hash duplicate detection
- Transactional database operations
- UUID generation for file tracking
- Audit trail for all operations

## Error Handling

### Upload Errors
- File type rejection
- Size limit exceeded
- Too many files
- Network interruptions

### Processing Errors
- Malformed ZIP files
- Missing metadata
- Security violations
- Database constraint failures

### Recovery
- Error files moved to processing_error directory
- Detailed logging for troubleshooting
- Admin interface for reviewing failed uploads
- Manual reprocessing capabilities

## Monitoring and Maintenance

### Job Status
- Real-time job tracking via `/jobs` routes
- Detailed error logging
- Processing metrics and KPIs

### File Management
- Automated cleanup of old files
- Storage usage monitoring
- Duplicate detection statistics

### Audit Trail
- Complete logging of all operations
- User action tracking
- Security event logging
- Performance metrics

## Integration Points

### with Direct Uploads
- Shared database models
- Common task creation logic
- Unified grading workflows

### with Verification Workflows
- PDF data extracted for verification
- Report linking to encounters
- Structured data population

### with Analytics
- Source data for KPI calculations
- Processing metrics
- Quality assurance tracking

## Best Practices

### Upload Preparation
- Ensure ZIP files follow expected structure
- Validate file contents before upload
- Use appropriate file compression
- Check file size limits

### Monitoring
- Monitor job queue regularly
- Review error logs
- Track processing metrics
- Validate data quality

### Security
- Regular security audits
- Monitor for malicious uploads
- Update allowlists as needed
- Review access permissions

## Troubleshooting

### Common Issues
1. **ZIP not processing**: Check security validation logs
2. **Duplicate files**: Verify MD5 hash handling
3. **OCR failures**: Review PDF quality and format
4. **Task creation issues**: Validate database constraints

### Debug Tools
- Job status interface
- Processing logs
- Error file review
- Database validation queries

## Future Enhancements

### Planned Improvements
- Enhanced file type support
- Improved OCR accuracy
- Real-time processing feedback
- Advanced duplicate detection
- Enhanced security scanning

### Scalability Considerations
- Distributed processing
- Cloud storage integration
- Load balancing
- Performance optimization