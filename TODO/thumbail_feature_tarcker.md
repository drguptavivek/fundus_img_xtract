# Thumbnail Feature Tracker

## Overview
Implement thumbnail generation for both DirectImageUpload and EncounterFile models using file-based storage with `thm_uuid.filetype` naming convention.

## Requirements Summary
- **Thumbnail Size**: 180px × 180px
- **Quality**: 85% JPEG compression
- **Storage**: Same folder as original image, named `thm_uuid.filetype`
- **Processing**: Async background generation
- **Cleanup**: Automatic deletion when parent image deleted
- **Direct Images**: Generate thumbnails for both original AND edited images
- **Serving**: New routes similar to existing image serving routes

## Implementation Tasks

### Phase 1: Database Schema Updates ✅ COMPLETED
- [x] Add `thumbnail_filename` field (nullable) to DirectImageUpload model
- [x] Add `edited_thumbnail_filename` field (nullable) to DirectImageUpload model
- [x] Add `thumbnail_filename` field (nullable) to EncounterFile model
- [x] Create Alembic migration for schema updates
- [x] Test migration with sample data

### Phase 2: Image Processing Utility ✅ COMPLETED
- [x] Create `utils/image_processing.py`
- [x] Implement `generate_thumbnail()` function (180x180px, 85% quality)
- [x] Add support for multiple image formats (JPEG, PNG, etc.)
- [x] Include proper error handling and validation
- [x] Add logging for thumbnail generation operations

### Phase 3: File Management ✅ COMPLETED
- [x] Update `utils/fileUtils.py` with thumbnail path utilities
- [x] Add thumbnail path security validation
- [x] Implement path traversal prevention for thumbnail files
- [x] Add thumbnail existence checking functions
- [x] Test thumbnail file operations

### Phase 4: Background Job System
- [ ] Create thumbnail generation job type
- [ ] Implement async thumbnail worker using existing Job/JobItem models
- [ ] Add job queue monitoring
- [ ] Implement retry logic for failed thumbnail generation
- [ ] Add job status tracking and reporting

### Phase 5: Integration Points
- [ ] Trigger thumbnail generation after direct upload completion
- [ ] Trigger thumbnail generation after ZIP processing completion
- [ ] Trigger thumbnail generation after image editing
- [ ] Handle both original and edited images for DirectImageUpload
- [ ] Implement fallback to original image if thumbnail missing

### Phase 6: Thumbnail Serving Routes
- [ ] Add `/encounter/img/<uuid>/thumbnail` route for ZIP images
- [ ] Add `/direct_upload/org_img/<uuid>/thumbnail` route for original direct uploads
- [ ] Add `/direct_upload/ed_img/<uuid>/thumbnail` route for edited direct uploads
- [ ] Update `utils/utilsImgServe.py` with thumbnail serving logic
- [ ] Add proper cache headers and MIME type validation
- [ ] Implement access control for thumbnail endpoints

### Phase 7: Automatic Cleanup System
- [ ] **CRITICAL**: Add thumbnail cleanup to DirectImageUpload deletion
- [ ] **CRITICAL**: Add thumbnail cleanup to EncounterFile deletion
- [ ] **CRITICAL**: Add thumbnail cleanup to PatientEncounters cascade deletion
- [ ] Handle cleanup for edited image thumbnails when original deleted
- [ ] Implement database event handlers for automatic cleanup
- [ ] Test all deletion scenarios thoroughly

### Phase 8: Maintenance Workers
- [ ] Implement orphaned thumbnail cleanup worker
- [ ] Add thumbnail regeneration utility for corrupted thumbnails
- [ ] Create admin interface for thumbnail management
- [ ] Add monitoring and alerting for thumbnail failures
- [ ] Schedule periodic cleanup workers

### Phase 9: Batch Processing for Existing Images
- [ ] Create admin utility to generate thumbnails for existing images
- [ ] Implement batch processing with progress tracking
- [ ] Add resume capability for interrupted batch jobs
- [ ] Clean up any pre-existing orphaned thumbnails
- [ ] Monitor batch processing performance

### Phase 10: Testing & Validation
- [ ] Unit tests for image processing functions
- [ ] Integration tests for thumbnail generation workflow
- [ ] Performance tests for async processing
- [ ] Security tests for path validation and access control
- [ ] Cleanup verification tests
- [ ] Load testing for thumbnail serving

## Technical Decisions Made

### Storage Strategy
- **File-based**: Store as files, not BLOBs in database
- **Naming Convention**: `thm_uuid.filetype` in same directory as source
- **Direct Images**: Generate separate thumbnails for original and edited versions
- **Compression**: 85% quality for optimal size/quality balance

### Processing Strategy
- **Async Generation**: Background processing to avoid upload delays
- **Job Queue**: Use existing Job/JobItem infrastructure
- **Error Handling**: Retry logic with exponential backoff
- **Monitoring**: Job status tracking and failure alerts

### Cleanup Strategy
- **Automatic Deletion**: Thumbnails deleted when parent images deleted
- **Cascade Cleanup**: Handle all deletion paths (manual, automated, cascade)
- **Orphan Cleanup**: Periodic worker to clean orphaned thumbnails
- **Regeneration**: Ability to regenerate missing/corrupted thumbnails

## Security Considerations
- [ ] Path traversal prevention for thumbnail files
- [ ] MIME type validation for generated thumbnails
- [ ] Access control matching parent image permissions
- [ ] Rate limiting for thumbnail generation requests
- [ ] Input validation for thumbnail processing parameters

## Performance Considerations
- [ ] Async processing to avoid upload delays
- [ ] Efficient memory usage for large image processing
- [ ] Proper caching headers for thumbnail serving
- [ ] Batch processing optimization for existing images
- [ ] Monitoring for thumbnail generation bottlenecks

## Rollout Strategy
1. **Phase 1-3**: Core infrastructure (database, utilities, file management)
2. **Phase 4-5**: Async processing and integration
3. **Phase 6-7**: Serving routes and cleanup system
4. **Phase 8-9**: Maintenance and batch processing
5. **Phase 10**: Testing and production deployment

## Blocked Items
- None currently

## Notes
- Maximum image size: 6MB
- Maximum images per upload: 50
- Storage capacity: Not an issue per requirements
- Must maintain backward compatibility
- Original images should be served if thumbnails missing

## Dependencies
- PIL/Pillow library (already available)
- Existing Job/JobItem infrastructure
- Current file serving utilities
- Database migration system (Alembic)

---

**Last Updated**: 2025-11-11
**Status**: Phase 1-3 Complete ✅ | Phase 4: Background Jobs (Next)

## Completed Work

### Phase 1-3 Summary
✅ **Database Schema**: Added thumbnail fields to DirectImageUpload and EncounterFile models
✅ **Migration**: Successfully applied Alembic migration (8b273099d1c0)
✅ **Image Processing**: Created comprehensive thumbnail generation utility (180x180px, 85% quality)
✅ **File Management**: Added secure thumbnail path utilities with proper validation
✅ **Testing**: All utilities tested and working in Docker environment

### Key Features Implemented
- **Thumbnail Generation**: PIL-based with proper aspect ratio handling and center cropping
- **Security**: Path traversal prevention and filename validation
- **Format Support**: JPEG, PNG, WebP, BMP, GIF with automatic format optimization
- **File Management**: Separate utilities for direct uploads and ZIP upload images
- **Cleanup**: Orphaned thumbnail detection and removal
- **Naming Convention**: `thm_uuid.filetype` as specified

### Next Steps
Ready to proceed with Phase 4: Background Job System for async thumbnail generation.