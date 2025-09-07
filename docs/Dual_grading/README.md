# Dual Grading System Documentation

This directory contains comprehensive documentation for the Dual Grading System implemented in the Fundus Image Manager application.

## Overview

The Dual Grading System requires each image to be independently graded by both a resident and a consultant (ophthalmologist). This approach ensures quality control and provides valuable training opportunities for residents.

## Documentation Files

1. **[current_state_summary.md](current_state_summary.md)** - High-level summary of the current implementation status
2. **[dual_grading_system.md](dual_grading_system.md)** - Comprehensive overview of the entire dual grading system
3. **[dual_grading_resident_role_implementation_summary.md](dual_grading_resident_role_implementation_summary.md)** - Summary of changes made to implement "resident" as a unique system role
4. **[dual_grading_role_distinction_summary.md](dual_grading_role_distinction_summary.md)** - Summary of role distinctions between residents and optometrists
5. **[technical_documentation.md](technical_documentation.md)** - Detailed technical documentation of algorithms and implementation
6. **[TODO.md](TODO.md)** - Implementation plan and current status (now complete)
7. **[user_guide.md](user_guide.md)** - User-facing guide for system operation
8. **[workflow_design_document.md](workflow_design_document.md)** - Detailed workflow design documentation

## System Components

### Key Features
- **Role-Based Grading**: Clear distinction between residents ('resident' role) and consultants ('ophthalmologist' role)
- **Image Source Support**: Works with both Remedio ZIP file images and direct uploads
- **Multi-Disease Coverage**: Supports grading for Glaucoma, Diabetic Retinopathy, AMD, and other diseases
- **Automatic Matching**: Periodically matches resident and consultant gradings for the same images
- **Image Locking**: Prevents editing of original gradings after matching
- **Discrepancy Analysis**: Identifies and analyzes disagreements between resident and consultant impressions
- **Formal Arbitration**: Provides workflow for resolving discrepant gradings
- **Comprehensive Reporting**: Detailed statistics and analytics on inter-rater reliability
- **Audit Trail**: Complete logging of all grading activities

### Technical Implementation
- **Database Extensions**: Added locking and arbitration fields to EncounterFile and DirectImageUpload models
- **Background Processing**: Automatic matching process runs every 2 hours
- **Security**: Role-based access control with appropriate restrictions
- **Data Integrity**: Comprehensive validation and protection mechanisms

## User Roles

1. **Residents**: Medical professionals in training with the 'resident' system role
2. **Consultants**: Experienced ophthalmologists with the 'ophthalmologist' system role
3. **Administrators**: Users with the 'admin' system role who have unrestricted access

## Workflow

1. **Independent Grading**: Residents and consultants independently grade the same images
2. **Automatic Matching**: System periodically identifies image pairs graded by both roles
3. **Image Locking**: Matched images are locked to prevent further edits to original gradings
4. **Discrepancy Analysis**: System analyzes paired gradings to identify disagreements
5. **Formal Arbitration**: Consultants can arbitrate discrepant images through a dedicated workflow
6. **Reporting**: Comprehensive statistics and analytics on inter-rater reliability

## Status

The Dual Grading System has been fully implemented with all planned functionality operational:
- ✅ Role-based grading with resident/consultant distinction
- ✅ Support for multiple image sources (Remedio ZIP files and direct uploads)
- ✅ Support for multiple disease types
- ✅ Automatic matching of resident/consultant gradings
- ✅ Image locking mechanism to preserve original gradings
- ✅ Discrepancy analysis with agreement statistics
- ✅ Formal arbitration workflow for discrepant cases
- ✅ Comprehensive audit trail of all activities
- ✅ User-friendly dashboard with progress tracking
- ✅ Role-based access control with appropriate restrictions

## Additional Resources

For more information about the Fundus Image Manager application, see the main documentation in the [/docs](..) directory.