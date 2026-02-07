# Tasks Documentation

This directory contains documentation related to task management and grading workflows in the Fundus Image Manager application.

## Documents

### [Scoping.md](Scoping.md)
Describes the two primary scoping mechanisms used in the application:
- User-LabUnit Scoping for general operations
- Slot-LabUnit Scoping for grading operations

### [taskCreationServices.md](taskCreationServices.md)
Documents the Task Creation Services that:
- Map verified fundus images to GradingTask records
- Enforce verification gates and data integrity
- Provide helpers for creating or removing tasks

### [reviewSystem.md](reviewSystem.md)
Comprehensive documentation for the Review System including:
- Quality control mechanisms for graded tasks
- Role slot types and their purposes
- Discrepancy review and task detail interfaces
- Usage patterns and best practices

### [linked_tasks.md](linked_tasks.md)
Details how linked tasks are created, allocated, and routed through linked follow-up flows.

### [regrade_tasks.md](regrade_tasks.md)
Details the regrade task queue, assignment rules, and submission flow for regrade adjudicators.

## Overview

The task management system handles the complete lifecycle of grading tasks, from creation through the dual grading workflow to final review. Key components include:

1. **Task Creation**: Automated creation of grading tasks from verified images
2. **Dual Grading**: Three-tier grading system (resident → resident2 → arbitrator)
3. **Review System**: Quality control and retrospective analysis
4. **Scoping**: Access control mechanisms for data and operations

## Role Slots in Grading System

The grading system supports multiple role slots, each with specific purposes:

| Role Slot | Purpose | Users |
|-----------|---------|--------|
| `resident` | Initial grading by residents | Users with `can_grade_resident` permission |
| `resident2` | Secondary grading by resident2 | Users with `can_grade_resident2` permission |
| `arbitrator` | Final decision for discrepancies | Users with `can_arbitrate` permission |
| `ai` | AI model predictions | Automated system processes |
| `review` | Quality control reviews | Resident2 and Arbitrators |

## Related Code Locations

- **Task Creation**: `/services/taskCreationServices.py`
- **Dual Grading**: `/grading/dual_grading.py`
- **Review Routes**: `/review/route_discrepancy_review.py`, `/review/task_review.py`
- **Permission Utils**: `/utils/dualGradingEligibility.py`
