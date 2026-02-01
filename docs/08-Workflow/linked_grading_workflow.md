# Linked Grading Workflow

The Linked Grading workflow optimizes the user experience by bundling related diseases into a single grading session.

## User Experience (UI/UX)

### Dashboard Visibility by Role

**Resident & Resident2:**
- See "Grade [PRIMARY]" button for each primary task
- Button shown regardless of linked disease state (both grading for consensus)

**Arbitrator:**
- See "Adjudicate [PRIMARY]" button ONLY if any disease (primary or linked) is in 'arbitration' state
- Button HIDDEN if all diseases are 'final' (fully matched/consensused, nothing to arbitrate)
- This ensures arbitrators don't see tasks that are already complete

### Primary Task Redirection
If a user attempts to access a grading task for a **linked** disease directly (e.g., via a link or bookmark), the system automatically identifies the **primary** disease and redirects the user to the primary task's view. This ensures that the primary disease is always the entry point for the group.

### The Grading Carousel
When linked diseases are detected, the grading interface switches to **Linked Mode**:
- **Carousel UI**: Each disease (primary + all linked) is presented as a separate slide in a carousel.
- **Dynamic Content**: Guidelines and features update automatically as the user navigates between slides or changes selections.
- **Unified Controls**: Navigation buttons (Next/Previous) allow the user to cycle through all diseases.

### Role-Based Editability in Carousel

**Resident & Resident2:**
- All diseases (primary + linked) shown as editable
- Consensus tracking happens independently per disease
- Both submit grades for all diseases together

**Arbitrator:**
- Disease editability based on task state:
  - **'arbitration' state** → Editable (arbitrator decision needed)
  - **'final' state** → Read-only (already matched, unless revising recent decision)
  - **Other states** → Read-only (context for decision-making)
- Arbitrator only edits diseases needing arbitration
- Linked read-only diseases shown for clinical context

### Features and Guidelines
- **Feature Selection**: Relevant clinical features are dynamically loaded based on the selected grade for each specific disease in the carousel.
- **Guidelines**: Instruction panels are specific to the disease currently visible in the carousel.

## Submission Logic

### Bulk Submission
When the user clicks "Save & Close" or "Save & Next", the form submits data for **all** tasks in the linked group simultaneously:
1. The system iterates through all tasks in the carousel.
2. It validates that each task has a selection (unless it was already graded).
3. It creates or updates `Grade` records for every task in the group.
4. It updates task states and creates consensus records independently for each disease.

### Navigation (Save & Next)
The "Save & Next" button intelligently finds the next eligible task for the user, prioritizing the primary disease type they were just working on, ensuring a smooth transition between different patient images.
