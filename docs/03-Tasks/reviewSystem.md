# Review System for Grading Tasks

## Overview

The Review System provides a quality control mechanism for the dual grading workflow. It allows authorized users (Resident2 and Arbitrators) to add review grades to tasks that have already been graded, providing an additional layer of quality assurance and enabling retrospective analysis of grading decisions.

## Purpose

The Review System serves several important purposes:

1. **Quality Control**: Allows senior graders to review and validate grading decisions
2. **Training Support**: Enables feedback on resident and resident2 grading performance
3. **Audit Trail**: Creates a permanent record of review assessments
4. **Discrepancy Resolution**: Provides a mechanism to document disagreements with original grades
5. **Dataset Curation**: Helps identify high-quality grades for training AI models

## Role Slot Types

The grading system supports multiple role slots, each with a specific purpose:

### Core Grading Slots

1. **`resident`**
   - Initial grading performed by resident ophthalmologists
   - First step in the dual grading workflow
   - Can be performed by users with `can_grade_resident` permission

2. **`resident2`**
   - Secondary grading performed by resident2 ophthalmologists
   - Second step in the dual grading workflow
   - Can be performed by users with `can_grade_resident2` permission

3. **`arbitrator`**
   - Final decision when resident and resident2 grades disagree
   - Only created when there's a discrepancy between resident and resident2 grades
   - Can be performed by users with `can_arbitrate` permission

### Special Slots

4. **`ai`**
   - Grades submitted by AI models
   - Automatically populated when AI models process images
   - Includes model metadata (name, version) for traceability
   - Used for AI-human comparison studies

5. **`review`**
   - Review grades added by resident2 or arbitrators for quality control
   - Can be added to any task regardless of its current state
   - Provides retrospective assessment of grading quality
   - Used for training, audit, and quality improvement

## Review System Features

### 1. Discrepancy Review Interface

Located at `/review/discrepancy-review`, this interface provides:

- **AI Grade Filtering**: Filter tasks based on presence of AI grades
  - "Has AI Grade": Shows tasks with AI model predictions
  - "No AI Grade": Shows tasks without AI predictions
  - "All Tasks": Shows all tasks regardless of AI status

- **AI Model Filtering**: Multi-select filter to show tasks graded by specific AI models
  - Displays model names with versions (e.g., "WadwaniAI vsep_2026")
  - Allows comparison between different AI models

- **Grade Filtering**: Filter by resident, resident2, arbitrator, and final grades
  - Only visible when a disease is selected
  - Helps identify specific grading patterns

### 2. Task Detail Review Interface

Located at `/review/reviewTaskDetails/<task_id>`, this interface provides:

- **Review Grade Form**: Allows authorized users to add review grades
  - Only visible to users with Resident2 or Arbitrator permissions
  - Shows all available disease grading options
  - Includes optional comment field for detailed feedback

- **Permission Checking**: Uses existing `dualGradingEligibility` functions
  - Verifies user has appropriate permissions for the disease-lab_unit combination
  - Ensures only qualified users can add review grades

- **Grade History**: Displays all grades associated with the task
  - Shows resident, resident2, arbitrator, AI, and existing review grades
  - Includes timestamps and grader information

## Implementation Details

### Database Schema

The `Grade` model supports all role slots through the `role_slot` field:

```python
role_slot: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
# Valid values: 'resident', 'resident2', 'arbitrator', 'ai', 'review'
```

### Permission Model

Review grades use the same permission model as the dual grading system:

- **Resident2 Review**: Users with `can_grade_resident2` permission can add review grades
- **Arbitrator Review**: Users with `can_arbitrate` permission can add review grades
- **Disease-Specific**: Permissions are specific to disease-lab_unit combinations

### API Endpoints

1. **`/api/ai-models`**
   - Returns list of available AI models
   - Used for AI model filtering in discrepancy review
   - Response format:
     ```json
     [
       {"id": 1, "name": "WadwaniAI", "version": "vsep_2026"},
       {"id": 2, "name": "MadhuNetraAI", "version": "vSep2025"}
     ]
     ```

2. **`POST /review/reviewTaskDetails/<task_id>`**
   - Handles review grade submission
   - Validates permissions and grade data
   - Creates or updates review grades

## Usage Patterns

### Quality Control Workflow

1. **Identify Tasks**: Use discrepancy review to find tasks needing review
   - Filter by specific diseases, grades, or AI model results
   - Focus on cases with discrepancies or unusual patterns

2. **Review Task**: Open task detail view to examine all grades
   - Compare resident, resident2, and AI grades
   - Review image and clinical context

3. **Add Review Grade**: Submit review assessment with comments
   - Select appropriate grade from disease options
   - Add detailed comments explaining reasoning
   - Comments are valuable for training and audit

### Training Support

1. **Resident Training**: Resident2 can review resident grades
   - Provide feedback on grading accuracy
   - Document areas for improvement

2. **AI Model Evaluation**: Compare AI grades with human graders
   - Identify strengths and weaknesses of AI models
   - Collect data for model improvement

### Audit and Compliance

1. **Quality Audit**: Regular review of grading patterns
   - Ensure consistency between graders
   - Identify systematic biases or issues

2. **Compliance Documentation**: Review grades serve as audit trail
   - Document quality control processes
   - Provide evidence of oversight

## Integration Points

### Dual Grading System

The Review System integrates seamlessly with the existing dual grading workflow:

- Does not interfere with normal grading progression
- Can be applied to tasks at any state (pending to final)
- Uses existing permission and scoping mechanisms

### AI Model Integration

Review System works with AI model grades:

- AI grades are displayed alongside human grades
- Filtering capabilities focus on AI model performance
- Supports AI-human comparison studies

### Reporting and Analytics

Review grades can be used for:

- Grading quality metrics
- Inter-grader consistency analysis
- AI model performance evaluation
- Training effectiveness measurement

## Best Practices

### Adding Review Grades

1. **Provide Detailed Comments**: Explain reasoning behind review grade
2. **Be Constructive**: Focus on educational value for training
3. **Stay Objective**: Base reviews on clinical evidence and guidelines
4. **Document Uncertainty**: Note when image quality affects grading

### Using Review Data

1. **Regular Reviews**: Schedule periodic review sessions
2. **Focus on Learning**: Use reviews to improve grading quality
3. **Track Patterns**: Identify systematic issues or training needs
4. **Feedback Loop**: Share insights with graders and AI teams

## Security Considerations

1. **Permission Enforcement**: Only authorized users can add review grades
2. **Audit Trail**: All review actions are logged with user and timestamp
3. **Data Integrity**: Review grades cannot be deleted, only updated
4. **Access Control**: Review interfaces respect existing scoping rules

## Future Enhancements

1. **Batch Review**: Interface for reviewing multiple tasks simultaneously
2. **Review Analytics**: Dashboard showing review statistics and trends
3. **Review Templates**: Pre-defined comments for common findings
4. **Review Workflows**: Automated review assignments based on criteria
5. **Integration with Training**: Link reviews to training modules and resources