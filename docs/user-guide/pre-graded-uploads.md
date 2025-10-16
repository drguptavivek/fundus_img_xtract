# Pre-Graded Image Uploads

This guide explains how to upload images that have already been graded, either by AI systems or by human graders. Pre-graded uploads allow you to import existing grading data into the system for review, analysis, or training purposes.

## Types of Pre-Graded Uploads

The system supports two types of pre-graded uploads:

1. **AI Pre-Graded Images**: Images graded by artificial intelligence systems
2. **Human Pre-Graded Images**: Images graded by faculty, residents, or other medical professionals

## When to Use Pre-Graded Uploads

Pre-graded uploads are useful for:
- Importing grades from external AI systems
- Migrating data from legacy systems
- Creating training datasets with known ground truth
- Benchmarking AI performance against human graders
- Quality assurance and review processes
- Research and analysis projects

## AI Pre-Graded Images

### Overview
AI pre-graded images come with automated assessments from machine learning models. These can be imported for review, validation, or comparison with human graders.

### Supported AI Systems
- **Custom AI Models**: Any AI system that can export grades in compatible format
- **Third-Party AI Services**: External AI grading services
- **Research Models**: Experimental or research AI systems
- **Production AI Systems**: Deployed AI grading solutions

### AI Grade Formats
- **CSV Files**: Comma-separated values with image identifiers and grades
- **Excel Files**: XLSX format with structured grade data
- **JSON Files**: Structured data format for complex grading information
- **API Integration**: Direct API connection to AI systems

### AI Grade Data Structure
Required fields for AI grades:
- **Image Identifier**: Unique reference to each image
- **Disease Grade**: Assessment for specific diseases (DR, Glaucoma, AMD)
- **Confidence Score**: AI's confidence in the assessment (optional)
- **Timestamp**: When the AI grading was performed
- **Model Version**: Information about the AI model used

## Human Pre-Graded Images

### Overview
Human pre-graded images come with assessments from medical professionals. These can be imported for review, consensus building, or training purposes.

### Supported Human Grader Types
- **Faculty Grades**: Assessments from senior ophthalmologists
- **Resident Grades**: Assessments from medical residents
- **External Experts**: Assessments from external consultants
- **Multiple Graders**: Grades from multiple independent graders

### Human Grade Formats
- **Excel Files**: Structured spreadsheets with grade data
- **CSV Files**: Comma-separated grade information
- **Database Exports**: From other grading systems
- **Manual Entry**: Direct entry through the system interface

### Human Grade Data Structure
Required fields for human grades:
- **Grader Identifier**: Who performed the grading
- **Image Identifier**: Reference to each graded image
- **Disease Assessments**: Grades for each relevant disease
- **Grading Date**: When the assessment was performed
- **Qualifiers**: Any additional notes or qualifiers

## Accessing Pre-Graded Upload

1. Log in to the system with appropriate permissions
2. Navigate to "Upload" → "Pre-Graded Images"
3. Choose the appropriate upload type (AI or Human graded)
4. Follow the specific instructions for your upload type

## Duplicate Handling for Pre-Graded Uploads

The system handles duplicates carefully for pre-graded uploads:

### Image Duplicate Detection
- **MD5 Hash Check**: Images are checked against existing images
- **Content Verification**: Ensures image content hasn't been previously uploaded
- **Grade Comparison**: Compares new grades with existing grades for same images
- **Version Tracking**: Tracks multiple grade versions for the same image

### Grade Duplicate Handling
- **Grade Override**: New grades can override existing grades
- **Grade Addition**: Multiple grades can be stored for the same image
- **Conflict Resolution**: System flags conflicting grades for review
- **Audit Trail**: All grade changes are tracked with timestamps

### Import Strategy Options
1. **Skip Duplicates**: Don't import if image already exists
2. **Update Existing**: Replace existing grades with new ones
3. **Add Additional**: Keep existing grades and add new ones
4. **Create Conflicts**: Flag conflicts for manual resolution

## AI Pre-Graded Upload Process

### Step 1: Prepare Your Data
1. Export grades from your AI system in compatible format
2. Ensure image identifiers match the images you'll upload
3. Validate grade values are within expected ranges
4. Include confidence scores if available
5. Add model version information

### Step 2: Upload Images
1. Select "AI Pre-Graded Upload" option
2. Upload the image files (JPG, PNG format)
3. Upload the grade data file (CSV, Excel, or JSON)
4. Map fields from your data to system fields
5. Review mapping before proceeding

### Step 3: Import Grades
1. System validates image-grade associations
2. Grades are imported and linked to images
3. Confidence scores are stored if provided
4. Model information is recorded
5. Import results are displayed

### Step 4: Review and Verify
1. Review imported grades for accuracy
2. Check for any import errors or warnings
3. Verify image-grade associations
4. Make any necessary corrections
5. Approve the import

## Human Pre-Graded Upload Process

### Step 1: Prepare Grade Data
1. Compile human grades in structured format
2. Include grader identification information
3. Ensure consistent grading scales
4. Add grading dates and context
5. Validate data completeness

### Step 2: Upload Images
1. Select "Human Pre-Graded Upload" option
2. Upload the image files
3. Upload the grade data file
4. Specify grader type (faculty, resident, etc.)
5. Configure import options

### Step 3: Import and Associate
1. System processes images and grades
2. Grades are linked to appropriate graders
3. Multiple grades can be associated with images
4. Grading hierarchy is established
5. Quality checks are performed

### Step 4: Quality Assurance
1. Review imported grades for consistency
2. Check for grading anomalies or outliers
3. Verify grader credentials and permissions
4. Validate grade distributions
5. Approve or reject imports

## Grade Mapping and Validation

### Field Mapping
When uploading grade data, you'll need to map your fields to system fields:
- **Image ID**: Map your image identifier to system field
- **Grader ID**: Map grader identification
- **Disease Grades**: Map each disease grade field
- **Confidence**: Map confidence or certainty scores
- **Metadata**: Map additional information fields

### Validation Rules
The system validates imported grades:
- **Grade Range Check**: Ensures grades are within valid ranges
- **Format Validation**: Verifies data formats are correct
- **Completeness Check**: Ensures required fields are present
- **Consistency Check**: Validates data consistency
- **Quality Metrics**: Calculates basic quality metrics

### Error Handling
- **Validation Errors**: Clear error messages for invalid data
- **Mapping Errors**: Help with field mapping issues
- **Format Errors**: Guidance on correct data formats
- **Missing Data**: Identification of incomplete records
- **Warning System**: Non-critical issues are flagged as warnings

## Managing Pre-Graded Images

### Viewing Pre-Graded Images
1. Navigate to "Upload" → "Pre-Graded Dashboard"
2. Filter by grader type, disease, or date
3. View images with their associated grades
4. Compare multiple grades for the same image
5. Access detailed grading information

### Editing Pre-Graded Data
1. Select an image from the dashboard
2. Review existing grades and metadata
3. Update grades if permissions allow
4. Add notes or qualifiers
5. Save changes with audit trail

### Grade Comparison Tools
- **Side-by-Side View**: Compare different grades for same image
- **Discrepancy Analysis**: Identify significant grade differences
- **Consensus Building**: Tools for resolving grade conflicts
- **Statistics**: Grade distribution and agreement metrics
- **Export Options**: Export grade comparisons for analysis

## Quality Assurance for Pre-Graded Uploads

### Automated Quality Checks
- **Grade Distribution**: Analyzes grade patterns for anomalies
- **Outlier Detection**: Flags unusual grading patterns
- **Consistency Checks**: Validates grading consistency
- **Completeness Verification**: Ensures all required data is present
- **Format Validation**: Checks data format compliance

### Manual Review Process
1. **Review Queue**: Items needing review are flagged
2. **Quality Dashboard**: Overview of quality metrics
3. **Review Tools**: Interface for detailed review
4. **Approval Workflow**: Multi-level approval if needed
5. **Audit Trail**: Complete record of all reviews

### Quality Metrics
- **Grade Agreement**: Measures agreement between graders
- **Consistency Scores**: Evaluates grading consistency
- **Completion Rates**: Tracks grading completeness
- **Error Rates**: Monitors grading error frequency
- **Time Metrics**: Tracks grading time patterns

## Best Practices for Pre-Graded Uploads

### Data Preparation
1. **Consistent Formatting**: Use consistent data formats
2. **Complete Documentation**: Document grading criteria and scales
3. **Quality Validation**: Validate data before upload
4. **Backup Creation**: Keep backups of original data
5. **Test Imports**: Test with small samples first

### Upload Process
1. **Incremental Uploads**: Upload in manageable batches
2. **Verify Results**: Check each upload for accuracy
3. **Monitor Progress**: Track upload and import progress
4. **Error Resolution**: Address issues promptly
5. **Document Issues**: Record and document any problems

### Post-Upload Management
1. **Regular Reviews**: Periodically review imported data
2. **Quality Monitoring**: Monitor data quality over time
3. **User Training**: Train users on proper procedures
4. **Process Improvement**: Continuously improve processes
5. **Feedback Collection**: Gather feedback from users

## Common Issues and Solutions

### Data Format Issues
- **Inconsistent Formats**: Standardize data formats before upload
- **Missing Fields**: Ensure all required fields are present
- **Invalid Values**: Validate data ranges and values
- **Encoding Problems**: Use UTF-8 encoding for text data

### Image-Grade Mismatches
- **Missing Images**: Ensure all graded images are uploaded
- **Orphaned Grades**: Grades without corresponding images
- **Multiple Matches**: One grade matching multiple images
- **No Matches**: Grades that don't match any images

### Import Errors
- **Validation Failures**: Data doesn't meet validation rules
- **Permission Issues**: User lacks required permissions
- **System Limits**: Exceeding system capacity or limits
- **Network Issues**: Connection problems during upload

### Solutions
1. **Pre-Validation**: Validate data before upload
2. **Incremental Approach**: Upload in smaller batches
3. **Error Logging**: Keep detailed error logs
4. **Rollback Capability**: Ability to undo problematic uploads
5. **Support Contact**: Know when to contact support

## Security and Privacy

### Data Protection
- **Encrypted Transfer**: All data transfers are encrypted
- **Secure Storage**: Grades stored in secure database
- **Access Control**: Role-based access to grading data
- **Audit Logging**: All access and changes are logged

### Privacy Considerations
- **Grader Anonymization**: Option to anonymize grader information
- **Data Minimization**: Only collect necessary grading data
- **Retention Policies**: Appropriate data retention periods
- **Compliance**: HIPAA and other regulatory compliance

## Getting Help with Pre-Graded Uploads

### Error Messages
Common pre-graded upload error messages:
- "Invalid grade format": Use supported grade formats
- "Missing image reference": Ensure all grades reference uploaded images
- "Invalid grader information": Verify grader credentials
- "Grade out of range": Check grade values are within valid ranges
- "Duplicate grade detected": Handle duplicate grades appropriately

### Troubleshooting Steps
1. **Check Data Format**: Verify data meets format requirements
2. **Validate References**: Ensure image references are correct
3. **Review Permissions**: Confirm you have necessary permissions
4. **Test Sample**: Try with a small sample first
5. **Check System Status**: Verify system is operating normally

### Contact Support
If you need help with pre-graded uploads:
1. Note the error message and context
2. Record the upload ID and timestamp
3. Describe your data format and structure
4. Include information about the grading system
5. Contact your system administrator