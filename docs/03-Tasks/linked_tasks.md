# Linked Task Management

Linked task management ensures that whenever a task is created for a primary disease, all associated linked disease tasks are automatically generated and maintained.

## Task Creation Workflow

### Automatic Propagation
In `services/taskCreationServices.py`, the `create_or_get_task` function uses a recursive-style approach:
1. It creates/retrieves the requested disease task.
2. If `create_linked=True` (the default), it fetches all linked disease IDs via `get_linked_disease_ids`.
3. It calls itself for each linked disease ID with `create_linked=False` to prevent infinite loops.

### Verification Gating
Verification is centralized at the primary disease level:
- When checking if an image is verified for a disease (`_is_verified_for_disease`), the system first resolves the **primary disease ID**.
- The verification status of the primary disease (e.g., `dr_verified_status`) determines the availability of both the primary and all its linked tasks.
- This ensures that if DR is verified, DME grading is automatically enabled.

## Idempotency and Integrity
- **Global Uniqueness**: Tasks are unique per `(image, disease)`. The system will never create duplicate tasks for the same disease on the same image, even if triggered multiple times via different linked paths.
- **Lab Unit Stability**: Once a task is created for a lab unit, its `lab_unit_id` is never mutated, preserving the ownership of the grading task even in linked workflows.
- **State Independence**: While tasks are created together, they maintain independent states (`pending`, `resident_done`, etc.) and require individual grading, though they are usually submitted together in the UI.

## On-Demand Creation Policy
- The grading UI does not create linked tasks on-demand.
- Only the task creation service creates linked tasks at primary task creation time.
- Legacy primaries created before a link existed remain unlinked unless backfilled.

## Dashboard Visibility Rules

### Task Filtering by Role and State

**For Resident & Resident2 Graders:**
- Show task if primary disease is in 'pending' or 'resident2_done' state (resident) / 'resident_done' state (resident2)
- Show all primary tasks regardless of linked disease state (both need to grade everything)

**Linked mismatch exclusion (resident/resident2):**
- Primary tasks are excluded when linked tasks exist for the same image and a mismatch state is detected:
  - Primary `resident_done` + linked `pending`
  - Primary `resident2_done`/`final` + linked `resident_done`

**For Arbitrators:**
- Show task ONLY if any disease (primary OR linked) is in 'arbitration' state
- Hide task if all diseases (primary AND linked) are in 'final' state
- This prevents arbitrators from seeing fully-matched/consensused tasks

### Task State Transitions

Tasks move through states independently:
- Primary: `pending` → `resident_done` → `arbitration` → `final`
- Linked: `pending` → `resident_done` → `arbitration` → `final`
- States can differ: primary in `arbitration` while linked in `final` (already matched)
- Consensus is determined separately for each disease

### Submission Behavior
- **Resident/Resident2**: Submit grades for all diseases in linked group (bulk submission)
- **Arbitrator**: Submit decisions for editable diseases only (based on state), read-only diseases shown for context
- Each disease's consensus is resolved based on its own grades (resident, resident2, arbitrator)

### Linked Follow-up Submissions
- Follow-up UI submits only editable linked panels (read-only panels are excluded).
- Client and server enforce that all editable linked panels are graded before submission.
