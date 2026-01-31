# Linked Grading Administration

The administration interface allows system managers to define and maintain relationships between diseases.

## Management Interface

Accessible via `/admin/linked-disease-gradings`, the admin interface provides full CRUD capabilities:

### Creating Links
1. **Primary Disease**: Select the main disease (e.g., Diabetic Retinopathy).
2. **Linked Disease**: Select the disease to be associated (e.g., DME).
3. **Display Order**: Define the sequence (important for the grading carousel).
4. **Active Status**: Enable or disable the link.

### Validation Rules
- **Non-Duplicate Links**: The system prevents creating a link that already exists.
- **Single Parent Constraint**: A disease cannot be linked to more than one primary disease. If you attempt to link a disease that is already linked elsewhere, the system will require you to delete the existing link first.
- **Different Diseases**: You cannot link a disease to itself.

## Audit Logging
All administrative actions are tracked in the `admin.audit` logger:
- **Created**: Logs primary/linked names, order, and status.
- **Updated**: Logs changes to display order or active status.
- **Deleted**: Logs the removal of the relationship.

All logs include the username of the administrator who performed the action.
