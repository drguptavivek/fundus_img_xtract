# Dual Grading System Documentation

## Overview

The Dual Grading System is a comprehensive workflow designed to ensure quality control and inter-rater reliability in clinical image grading. Each image is independently assessed by two medical professionals: a resident and a consultant (ophthalmologist). This dual assessment approach helps identify discrepancies, improve diagnostic accuracy, and provide valuable training opportunities.

## Key Components

### 1. Role-Based Access Control

The system implements a clear role distinction:
- **Residents**: Users with the 'resident' system role, assigned the 'resident' grader role during grading
- **Consultants**: Users with the 'ophthalmologist' system role, assigned the 'consultant' grader role during grading
- **Administrators**: Users with the 'admin' system role, who can grade as either role based on context

### 2. Image Sources

The system supports grading of images from two sources:
1. **Remedio ZIP Files**: Images extracted from ZIP archives uploaded by Remedio FOP cameras
2. **Direct Uploads**: Individual images uploaded directly through the web interface

### 3. Disease Types

The system supports grading for multiple diseases:
- Glaucoma
- Diabetic Retinopathy (DR)
- Age-related Macular Degeneration (AMD)
- Other diseases with configurable gradings

## Workflow Process

### 1. Initial Grading

1. **Image Selection**: Users can select images to grade through various methods:
   - Start from the grading dashboard for random ungraded images
   - Enter a specific image UUID
   - Navigate through their previous gradings

2. **Role Assignment**: Based on the user's system role, they are automatically assigned the appropriate grader role:
   - Resident users → 'resident' grader role
   - Consultant users → 'consultant' grader role
   - Admin users → contextually assigned role

3. **Grading Interface**: Users are presented with:
   - Full-screen image viewer with zoom and pan capabilities
   - Image enhancement controls (brightness, contrast, color filters)
   - Disease-specific impression options
   - Optional remarks field

4. **Grade Submission**: Grades are saved using an upsert approach:
   - If the user has previously graded the same image, the existing grade is updated
   - If this is a new grade, a new record is created
   - Each user can have only one grade per image per condition

### 2. Matching Process

The matching process identifies pairs of resident and consultant gradings for the same image:

1. **Automatic Matching**: Runs periodically (every 2 hours) to identify image pairs that have been graded by both roles

2. **Locking Mechanism**: Once matched, images are locked to prevent further edits to the original gradings:
   - `is_locked` field is set to True
   - `matched_at` timestamp is recorded
   - Original gradings become non-editable

3. **Status Tracking**: The system tracks the grading status of each image:
   - Not Graded: No gradings by either role
   - Resident Only: Graded by resident but not consultant
   - Consultant Only: Graded by consultant but not resident
   - Both Graded: Graded by both resident and consultant

### 3. Discrepancy Analysis

After matching, the system analyzes paired gradings to identify discrepancies:

1. **Agreement Matrix**: Generates statistics showing overall agreement between residents and consultants
2. **Discrepancy List**: Identifies images where resident and consultant gave different impressions
3. **Inter-rater Reliability**: Calculates Kappa statistics for inter-rater reliability analysis

### 4. Arbitration Workflow

For images with discrepancies, a formal arbitration process is initiated:

1. **Arbitration Dashboard**: Consultants can view images requiring arbitration
2. **Arbitration Grading**: Consultants provide a final, arbitrated grade for discrepant images
3. **Arbitration Tracking**: The system tracks which images have been arbitrated:
   - `is_arbitration` field is set to True
   - `arbitrated_by` field records the consultant who performed arbitration
   - Arbitrated images disappear from the discrepancy list

## Database Schema

### Core Models

1. **ImageGrading Model**:
   - Stores individual gradings with references to images, graders, and roles
   - Tracks graded impressions, remarks, and timestamps
   - Supports both Remedio ZIP images and direct uploads

2. **EncounterFile Model** (Remedio ZIP images):
   - Extended with matching and arbitration fields:
     - `is_locked`: Indicates if the image is locked for editing
     - `matched_at`: Timestamp when the image was matched
     - `is_arbitration`: Indicates if the image has been arbitrated
     - `arbitrated_by`: Reference to the user who performed arbitration

3. **DirectImageUpload Model** (Direct uploads):
   - Extended with matching and arbitration fields:
     - `is_locked`: Indicates if the image is locked for editing
     - `matched_at`: Timestamp when the image was matched
     - `is_arbitration`: Indicates if the image has been arbitrated
     - `arbitrated_by`: Reference to the user who performed arbitration

## User Interface

### 1. Grading Dashboard

The main grading dashboard provides:
- Quick access to ungraded images
- Personal grading history
- Statistics on grading activities
- Navigation to specialized grading interfaces

### 2. Image Viewer

The image viewer offers:
- Full-screen display with zoom and pan
- Brightness and contrast controls
- Color filters for enhanced visualization
- Side-by-side comparison for difficult cases

### 3. Grading Forms

Disease-specific grading forms provide:
- Appropriate impression options for each disease
- Remarks field for additional notes
- "Save & Next" workflow for efficient grading

### 4. Dual Grading Dashboard

The dual grading dashboard includes:
- Overall statistics on grading progress
- Paired gradings view
- Discrepancy analysis with agreement percentages
- Matching dashboard with manual trigger

### 5. Arbitration Interface

The arbitration interface allows:
- Viewing of discrepant image pairs
- Comparison of resident and consultant impressions
- Submission of arbitrated grades
- Tracking of arbitration status

## Security and Compliance

### 1. Access Controls

- Role-based access control restricts users to appropriate functions
- Consultants can only access images from their own LabUnit (except admins)
- Residents have broader access for training purposes

### 2. Audit Trail

- All grading activities are logged with timestamps
- User identity, role, and actions are recorded
- Changes to grades are tracked with version history

### 3. Data Integrity

- CSRF protection on all grading forms
- Input validation on all grade submissions
- Database constraints to prevent duplicate gradings

## Reporting and Analytics

### 1. Inter-rater Reliability

The system provides reports to analyze agreement between residents and consultants:
- Overall agreement statistics
- Discrepancy analysis
- Kappa statistics for inter-rater reliability

### 2. Progress Tracking

Dashboards show:
- Grading progress by user and role
- Completion rates for different image sources
- Time-to-completion metrics

### 3. Quality Assurance

Reports highlight:
- Common discrepancy patterns
- Individual grader performance
- Training opportunities based on disagreement analysis

## Implementation Details

### 1. Backend Services

- **Matching Service**: Runs periodically to identify image pairs graded by both roles
- **Arbitration Service**: Manages the workflow for resolving discrepant gradings
- **Analytics Service**: Generates reports on inter-rater reliability and quality metrics

### 2. Frontend Components

- **Image Viewer**: Custom-built viewer with enhancement controls
- **Grading Forms**: Disease-specific interfaces with appropriate impression options
- **Dashboard Views**: Interactive displays of statistics and progress metrics

### 3. Data Models

- **ImageGrading**: Core model storing individual gradings
- **Extended Models**: EncounterFile and DirectImageUpload extended with matching/arbitration fields
- **Relationships**: Proper foreign key relationships to ensure data consistency

## Best Practices

### For Graders

1. **Thorough Assessment**: Take time to carefully evaluate each image
2. **Consistent Criteria**: Apply the same grading criteria consistently
3. **Detailed Remarks**: Use the remarks field to explain unusual findings
4. **Regular Calibration**: Participate in calibration exercises to maintain consistency

### For Administrators

1. **Role Management**: Assign appropriate roles to users based on their responsibilities
2. **Training Oversight**: Monitor resident progress and provide feedback
3. **Quality Assurance**: Regularly review discrepancy reports and arbitration outcomes
4. **System Monitoring**: Track system performance and user adoption metrics

## Future Enhancements

### 1. Advanced Analytics

- Machine learning models to predict discrepancy likelihood
- Automated flagging of potentially problematic cases
- Integration with AI-based grading as a third opinion

### 2. Enhanced Training

- Personalized training modules based on discrepancy analysis
- Virtual reality simulation for complex cases
- Gamification elements to encourage participation

### 3. Expanded Functionality

- Support for intra-rater agreement analysis
- Automated discrepancy resolution workflows
- Mobile interfaces for remote grading

## Conclusion

The Dual Grading System provides a robust framework for ensuring quality control in clinical image grading while supporting resident education and training. Through careful attention to role-based access control, systematic matching and arbitration workflows, and comprehensive reporting capabilities, the system helps maintain high diagnostic standards while fostering professional development.