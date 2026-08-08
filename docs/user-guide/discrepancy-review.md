# Discrepancy Review Feature

This guide explains how to use the Discrepancy Review feature, which allows administrators and data managers to review grading tasks where there are disagreements or discrepancies between different graders.

## Overview

The Discrepancy Review feature provides a centralized interface for examining grading tasks with potential discrepancies between:
- Resident grades vs. Resident2 grades
- AI grades vs. Human grades
- Arbitrator decisions vs. initial grades
- Review grades added for quality control

This tool is designed to help identify patterns, ensure quality, and perform quality assurance activities across the grading workflow.

## Accessing Discrepancy Review

### Required Permissions
- **Admin**: Full access to all discrepancy reviews across all lab units
- **Data Manager**: Access to discrepancy reviews for assigned lab units only

### Navigation Path
1. Log in to the system with appropriate permissions
2. Navigate to **Review** in the main menu
3. Select **Discrepancy Review** from the submenu
4. Or navigate directly to `/review/discrepancy-review`

## Using the Discrepancy Review Interface

### Main Interface Overview

The discrepancy review page displays:
- Filter controls for refining the results
- A table of grading tasks with discrepancies
- Pagination controls for navigating results
- Summary statistics about the current view

### Available Filters

The system offers several filters to refine the displayed tasks:

#### Disease Filter
- Select one or more diseases to review (e.g., Diabetic Retinopathy, Glaucoma, AMD)
- Useful for focusing on specific disease types

#### Lab Unit Filter
- Select specific lab units to review
- Admin users see all lab units
- Data managers only see their assigned lab units

#### Grade Filters
- **Resident Grade**: Filter tasks based on the resident's grade
- **Resident2 Grade**: Filter tasks based on the resident2's grade
- **Arbitrator Grade**: Filter tasks based on arbitrator's grade
- **Final Grade**: Filter tasks based on the final consensus grade

#### AI Grade Filter
- **Has AI Grade**: Show only tasks that include an AI grade
- **No AI Grade**: Show only tasks without an AI grade

#### Review Grade Filter
- **Has Human Review**: Show only tasks that have a `review`-role human grade
- **No Human Review**: Show only tasks without a `review`-role human grade. AI-model feedback alone does not count as a human review.

### Submitting AI Feedback and Human Review

- AI-model quality status/comments and a human review grade are independent actions.
- Prefilled AI feedback is not resubmitted unless its status or comment actually changes.
- Clearing an existing AI status/comment is an explicit saved change.
- Updating a human review requires selecting the intended grade again; an existing review is displayed for reference but is never selected implicitly.
- When an AI grade is visible and a human grade is selected, the reviewer must record whether the update was based on the AI result.

#### AI Model Filter
- Select specific AI models to filter by
- Useful for comparing AI model performance

### Interpreting Task Data

Each task row displays:

#### Basic Information
- **Task ID**: Unique identifier for the grading task
- **Disease**: The disease being assessed
- **Lab Unit**: The lab unit where the image originated
- **Hospital**: The hospital associated with the lab unit
- **State**: Current state of the task (pending, resident_done, resident2_done, arbitration, final)

#### Grade Information
- **Resident Grade**: The grade assigned by the resident
- **Resident2 Grade**: The grade assigned by the resident2 member
- **AI Grade**: The grade assigned by AI, including model name and version
- **Arbitrator Grade**: The grade assigned by the arbitrator
- **Final Grade**: The consensus grade

#### Image Information
- **Image UUID**: Unique identifier for the image being graded
- Links to view the original image

### Identifying Discrepancies

The system does not automatically highlight discrepancies, but you can identify them by comparing grades in the table:
- When resident and resident2 grades differ
- When AI grade is significantly different from human grades
- When review grades differ from original grades

## Common Use Cases

### Quality Assurance Review
1. Filter by lab unit to focus on a specific area
2. Apply grade filters to find specific grade combinations
3. Review tasks with AI grades to compare AI vs. human performance
4. Look for patterns in grading disagreements

### AI Model Performance
1. Use the AI Model filter to focus on specific models
2. Compare AI grades with human grades
3. Identify cases where AI performed well or poorly
4. Note common error patterns for model improvement

### Training and Calibration
1. Focus on resident vs. resident2 disagreements
2. Identify residents who may need additional training
3. Review arbitrator decisions to understand complex cases
4. Use findings to improve training materials

### Consensus Analysis
1. Filter to show final grades that required arbitration
2. Understand why initial grades disagreed
3. Identify common areas of disagreement
4. Improve grading guidelines based on findings

## Best Practices

### Before Starting a Review Session
1. Define your specific objectives (quality assurance, model comparison, training needs)
2. Plan your filtering strategy to focus on the most relevant tasks
3. Set aside sufficient time for thorough review

### During Review
1. Look for patterns rather than focusing on individual cases
2. Document interesting cases for future reference
3. Take notes about common issues or trends
4. Consider creating follow-up tasks for complex cases

### After Review
1. Share findings with relevant stakeholders
2. Update training materials if appropriate
3. Consider implementing process improvements
4. Schedule follow-up reviews to track changes

## Tips for Effective Review

### Efficient Filtering
- Start broad and narrow your filters as needed
- Use the AI grade filter to quickly identify AI vs. human comparisons
- Use grade filters to focus on specific grade combinations

### Analyzing Results
- Compare AI model performance across different diseases
- Look for consistency in grading patterns
- Note cases where AI outperformed humans or vice versa
- Identify potential areas for guideline clarification

### Documentation
- Keep records of your findings for future reference
- Document patterns or trends you identify
- Note any system issues encountered during review

## Troubleshooting

### Limited Results
- If you receive few results, try removing some filters
- Check that you have permissions for the lab units you're trying to access

### Performance Issues
- The page displays 50 tasks at a time to maintain performance
- Use filters to focus on the most relevant tasks
- If performance is still an issue, contact your system administrator

### Missing Data
- Ensure all filters are correctly applied
- Check that your user account has the appropriate permissions
- Some grade types may not be available for all tasks depending on workflow
