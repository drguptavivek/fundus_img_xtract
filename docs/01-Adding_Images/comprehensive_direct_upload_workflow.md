# Direct Upload Workflow - Comprehensive Guide

## Overview

The Direct Upload system allows authorized users to upload individual retinal fundus images directly through a web interface, bypassing the ZIP archive processing workflow. This is designed for clinics that have individual images rather than batch archives from Remedio cameras.

## Current Implementation

### 1. Upload Interface

**Entry Points:**
- `/direct/upload` - Upload form with metadata selection
- `/direct/dashboard` - Management interface for uploaded images

**Access Control:**
- Roles: `fileUploader`, `optometrist`, `data_manager`, `admin`
- User-scoped access (users see only their uploads unless admin/data_manager)

**Form Fields:**
- `hospital_id`: Hospital selection (dropdown)
- `lab_unit_id`: Lab unit selection (filtered by hospital)
- `camera_id`: Camera type selection
- `disease_id`: Disease selection for grading
- `area_id`: Anatomical area (left/right eye)
- `is_mydriatic`: Mydriatic agent usage checkbox
- `files`: Multiple file selection (up to 100 files)

### 2. File Processing Workflow

**Validation Steps:**
1. **Form Validation:**
   - Required field completeness
   - Lab unit belongs to selected hospital
   - Entity existence validation

2. **File Validation:**
   - File size limit: 5MB per file
   - MIME type validation: JPEG, PNG only
   - MD5 hash calculation for duplicate detection
   - Upload quota enforcement

3. **User Quotas:**
   - Per-request limit: 100 files
   - Lifetime quota: 50 files per user (configurable)
   - Database tracking of upload counts

**Processing Steps:**
1. **Job Creation:**
   - Database job entry for tracking
   - Job item entries for each file
   - Upload metadata logging

2. **Directory Setup:**
   - User-specific upload directories
   - Date-based organization
   - Separate directories for originals, edited files, duplicates

3. **File Handling:**
   - Original files saved to upload directory
   - MD5 hash calculation
   - Duplicate detection and separation
   - Database record creation (DirectImageUpload)

4. **Task Creation:**
   - GradingTask creation for each image
   - Disease-specific task assignment
   - Lab unit scoping

### 3. Image Management Features

**Image Editing:**
- `/direct/upload/edit_image/<int:upload_id>` - Image editing interface
- Cropping, rotation, brightness/contrast adjustment
- Original file preservation
- Edited file version tracking

**Metadata Management:**
- `/direct/upload/edit/<int:upload_id>` - Metadata editing
- Hospital, lab unit, camera updates
- Disease and area modifications
- Verification status management

**Verification System:**
- DirectImageVerify records for quality control
- Status tracking: 'verified', 'unverified', 'pending'
- Automatic verification for pre-graded uploads
- Admin review capabilities

### 4. Dashboard and Management

**Main Dashboard:**
- Pagination of uploaded files
- Advanced filtering capabilities
- KPI displays and statistics
- Bulk operations (delete up to 30 files)

**Filtering Options:**
- Date range selection
- Hospital and lab unit filtering
- Updater and camera filtering
- Disease and area filtering
- Verification status filtering

**KPI and Analytics:**
- Upload statistics by camera type
- Disease distribution metrics
- Area breakdown analytics
- User upload tracking

### 5. API Integration

**Status API:**
- `/api/direct/upload/status/<int:job_id>` - Real-time job status
- JSON response format
- Processing progress tracking

**Integration Points:**
- Grading system integration
- Analytics data population
- Materialized view updates

## Database Schema Integration

### Key Models Involved

1. **DirectImageUpload** - Primary image upload record
2. **DirectImageVerify** - Verification status tracking
3. **GradingTask** - Grading workflow tasks
4. **Job/JobItem** - Background processing tracking
5. **User** - Upload quota and scoping

### Data Flow

```
Image Upload → Validation → File Storage → Database Record → Task Creation → Grading Workflow
```

### Key Relationships

- DirectImageUpload → GradingTask (1:many)
- DirectImageUpload → DirectImageVerify (1:1)
- DirectImageUpload → User (many:1)
- GradingTask → Grade (1:many)

## Configuration

### File Upload Limits
- `DIRECT_UPLOAD_MAX_FILES`: 100 files per request
- `DIRECT_UPLOAD_MAX_FILE_SIZE_MB`: 5MB per file
- `DIRECT_UPLOAD_ALLOWED_MIMETYPES`: image/jpeg,image/png

### User Quotas
- `MAX_FILES_PER_UPLOAD`: 50 files lifetime quota
- `file_upload_count`: Persistent user counter
- `file_upload_quota`: Configurable user quota field

### Storage Organization
- User-specific directories
- Date-based folder structure
- Separate areas for originals, edits, duplicates

## Security Features

### Access Control
- Role-based upload permissions
- User-scoped data access
- Lab unit-based restrictions
- Administrative override capabilities

### File Security
- MIME type validation
- Magic byte verification
- Size limit enforcement
- Path traversal protection

### Data Integrity
- MD5 hash duplicate detection
- Database transaction integrity
- Audit trail maintenance
- Upload tracking and logging

## Workflow Variations

### Standard Upload
- Individual image selection
- Manual metadata entry
- Immediate processing
- Task creation for grading

### Pre-graded Upload
- Images with existing grades
- Excel file import capability
- Automatic verification
- Review task creation

### Bulk Upload
- Multiple files per request
- Shared metadata application
- Batch job processing
- Progress tracking

## Integration with Other Systems

### Grading System
- Automatic task creation
- Disease-specific routing
- Lab unit assignment
- Priority management

### Analytics System
- Real-time KPI updates
- Materialized view population
- Upload metrics tracking
- Quality assurance data

### Verification Workflows
- Quality control integration
- Review queue population
- Status tracking
- Audit trail maintenance

## Error Handling

### Upload Errors
- File validation failures
- Quota exceeded scenarios
- Network interruptions
- Invalid metadata combinations

### Processing Errors
- File storage failures
- Database constraint violations
- Task creation failures
- System resource limitations

### Recovery Mechanisms
- Error logging and reporting
- Retry capabilities
- Administrative intervention
- Manual processing options

## Performance Considerations

### Scalability
- Concurrent upload handling
- File system optimization
- Database indexing
- Cache utilization

### Optimization
- Image compression options
- Thumbnail generation
- Progressive loading
- Background processing

### Monitoring
- Upload success rates
- Processing time metrics
- Storage usage tracking
- User activity patterns

## Best Practices

### Upload Preparation
- Image format optimization
- Metadata preparation
- File size optimization
- Batch organization

### Quality Assurance
- Image quality verification
- Metadata accuracy
- Duplicate prevention
- Standardization compliance

### User Training
- Interface familiarization
- Workflow understanding
- Error handling procedures
- Quality standards

## Troubleshooting

### Common Issues
1. **Upload failures**: Check file size and format
2. **Quota exceeded**: Review user limits
3. **Metadata errors**: Validate form inputs
4. **Processing delays**: Monitor job queues

### Debug Tools
- Upload status interface
- Error log review
- Database validation
- File system checks

## Future Enhancements

### Planned Features
- Advanced image processing
- AI-assisted metadata extraction
- Enhanced validation
- Mobile interface support

### Scalability Improvements
- Cloud storage integration
- Distributed processing
- Load balancing
- Performance optimization

### User Experience
- Drag-and-drop interface
- Progress indicators
- Batch operations
- Advanced filtering