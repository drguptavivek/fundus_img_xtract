# Dual Grading (Resident + Resident2) with Arbitration — Overview

Purpose: Introduce a normalized, extensible grading workflow where each image can be graded independently per disease by a Resident and Resident2; disagreements are resolved by a third Ophthalmologist (Arbitrator). Eligibility to grade/arbitrate is controlled per user, per disease, and per lab unit. Only anonymized/verified images enter the grading flow.

Status: ✅ Core implementation complete, 🔄 Dashboard/UX improvements in progress

Scope and Principles
- Per-disease tasks: Exactly one grading task per image×disease globally. The optional `lab_unit_id` on a task is for grading assignment and queue scoping only (which graders see/work the task); it does not redefine image identity. Once any image×disease task reaches a final consensus (agreement or adjudication) in any lab unit, the gold standard is established and the image must not be re-tasked for the same disease in another lab unit.
- Dual independent grading: Resident and Resident2 submit independently and are masked from each other.
- Arbitration: If Resident and Resident2 disagree, a third Ophthalmologist adjudicates; adjudicator sees grader identities (per requirement).
- Eligibility model: No new global roles. Slot permissions derive from existing `user_roles` (resident/ophthalmologist) AND a new grading eligibility matrix per user×disease×lab_unit.
- Verification gating: Only anonymized/verified images are eligible for task creation and grading selection.
- Extensible: Images can be graded for multiple diseases at different times (e.g., DR today, AMD later), each as its own task.
- Auditable: Full history of grade attempts is retained; consensus recorded per task.
- Revision capability: Users can revise their own gradings before task finalization, with appropriate validation.
- Role-based exclusivity: A user cannot grade the same task in multiple roles (e.g., as both resident and resident2).
- 2-week restriction: Users cannot be assigned the same task for grading within a 2-week period, regardless of slot. After 2 weeks, users can grade the same image in a different slot of the same task.

Key Entities (Normalized)
- grading_task: Anchor for an image-per-disease. Holds lab_unit, state.
- grade: Individual grade attempt tied to a task with slot `resident|resident2|arbitrator` and a `DiseaseGrading` label.
- consensus: Final decision per task, method is `match` (resident/resident2 agree) or `adjudication` (arbitrator decided).
- user_disease_unit_role: Eligibility flags per user×disease×lab_unit: `can_grade_resident`, `can_grade_resident2`, `can_arbitrate`.
- ai_grade (optional): AI model outputs per image-per-disease; decoupled from human consensus.

Verification Rules (Entry Criteria)
- Direct uploads: require `direct_image_verifications.verified_status = 'verified'`.
- Remed.io DR: require `patient_encounters.dr_verified_status = 'verified'`.
- Remed.io Glaucoma: require `patient_encounters.glaucoma_verified_status = 'verified'`.
- Future diseases (e.g., AMD): add equivalent verification flag, or only create tasks on-demand once defined.

Auto Task Creation
- Direct: When a direct image is verified, auto-create a task for its native `disease_id` and lab unit.
- Remed.io DR/Glaucoma: When an encounter is verified for that disease, auto-create tasks for each image in the encounter for that disease.
- Additional diseases: Create tasks later via an idempotent `ensure_task(image_uuid, disease_id)` workflow or via admin/batch job.

What Stays the Same
- Existing global roles remain untouched (admin/auditor/ophthalmologist/resident/etc.).
- Existing `user_lab_units` controls upload/write access; grading eligibility is separate.
- Existing `Disease` and `DiseaseGrading` remain the source of truth for diseases and labels.

What Changes
- Introduction of a dedicated grading workflow model (tasks, grades, consensus) with per-slot enforcement and arbitration.
- New eligibility matrix to control who can grade which disease in which lab unit (independent of uploads mapping).
- Grading UI/UX routes enforce verification gating and eligibility; arbitrator views prior labels with grader identities.
- Added revision capability allowing users to edit their previous gradings before task finalization.
- Implemented 2-week restriction to prevent users from grading the same task multiple times within a short period.

Security & Compliance
- Mask PHI in grading views; serve images by UUID-only endpoints.
- CSRF on all forms; strict enum validation; ORM-bound parameters.
- Logging via app success/error loggers for submissions and state transitions.
- Revision functionality includes appropriate validation to prevent unauthorized access.
- 2-week restriction prevents over-grading and ensures diverse grader participation.

Out of Scope (Initial)
- Confidence scores (not required).
- Intra-rater reliability resurfacing (can be added later without schema changes).


## Mermaid Diagram — End-to-End Flow

```mermaid
flowchart TD
    %% Verification gating before any task creation
    S[Start] --> VG{Verification Gating}
    VG -->|Direct Upload| VGD[DirectImageVerify.verified == 'verified'?]
    VG -->|Remed.io DR| VDR[PatientEncounters.dr_verified_status == 'verified'?]
    VG -->|Remed.io Glaucoma| VGL[PatientEncounters.glaucoma_verified_status == 'verified'?]

    VGdNo[Block: not verified]:::stop
    VdrNo[Block: not verified]:::stop
    VglNo[Block: not verified]:::stop

    VGdYes[OK]:::ok
    VdrYes[OK]:::ok
    VglYes[OK]:::ok

    VGD -->|No| VGdNo
    VGD -->|Yes| VGdYes
    VDR -->|No| VdrNo
    VDR -->|Yes| VdrYes
    VGL -->|No| VglNo
    VGL -->|Yes| VglYes

    %% Task creation (native disease or ensure_task)
    VGdYes --> CT["Create or Get GradingTask (image,disease,lab)"]
    VdrYes --> CT
    VglYes --> CT

    %% Eligibility check per slot prior to grading
    CT --> EC{Eligibility Check}
    EC -->|Resident slot| ER{user_roles has 'resident' AND
    user_disease_unit_role.can_grade_resident}
    EC -->|Resident2 slot| EF{user_roles has 'ophthalmologist' AND
    user_disease_unit_role.can_grade_resident2}
    EC -->|Arbitration| EA{user_roles has 'ophthalmologist' AND
    user_disease_unit_role.can_arbitrate AND
    user not prior grader}

    ER -->|Fail| BR[Block]
    EF -->|Fail| BF[Block]
    EA -->|Fail| BA[Block]
    ER -->|Pass| GR["Submit Grade role=resident"]
    EF -->|Pass| GF["Submit Grade role=resident2"]
    EA -->|Pass| GA["Submit Grade role=arbitrator"]

    %% Dual grading convergence
    GR --> CK{"Resident & Resident2 present?"}
    GF --> CK
    CK -->|No| WAIT["State = resident_done or resident2_done"]
    CK -->|Yes| MATCH{Labels match?}
    MATCH -->|Yes| CM["Consensus - method=match; State=final"]
    MATCH -->|No| ARB["State=arbitration; build arbitrator pool"]
    ARB --> GA
    GA --> CA["Consensus - method=adjudication; State=final"]

    %% Revision functionality
    GR --> REV[User can revise their grade]
    GF --> REV
    GA --> REV
    REV -->|Before final state| REVSUB[Submit revised grade]
    REVSUB --> CK

    %% 2-week restriction logic
    EC -->|Task Assignment| TWOR{Graded within<br/>last 2 weeks?}
    TWOR -->|Yes| BLOCK2W[Block Assignment - <br/>2-week restriction]
    TWOR -->|No| ASSIGN[Assign Task for Grading]

    classDef stop fill:#fdd,stroke:#c33,stroke-width:1px,color:#600
    classDef ok fill:#dfd,stroke:#393,stroke-width:1px,color:#060
```

## Mermaid Diagram — Admin Eligibility & Auto-Tasks

```mermaid
flowchart LR
    A["Admin UI: Assign Eligibility"] --> F1["Select User"]
    F1 --> F2["Select Diseases"]
    F2 --> F3["Select Grading Lab Units"]
    F3 --> F4["Toggle Slot Flags <br/> resident resident2 arbitrator"]
    F4 --> API["POST api/grading-eligibility/users/user_id <br/> items: disease_id, lab_unit_id, flags"]
    API --> DUR[(user_disease_unit_role)]

    subgraph Verification Triggers
      V1[DirectImageVerify → verified]
      V2[Encounter DR verified]
      V3[Encounter Glaucoma verified]
    end

    V1 --> SVC1["create_or_get_task <br/> (direct_image_upload_id, native disease, lab)"]
    V2 --> SVC2["create_or_get_task <br/> (for each image, DR disease, lab)"]
    V3 --> SVC3["create_or_get_task <br/> (for each image, Glaucoma disease, lab)"]

    SVC1 --> GT[(grading_tasks)]
    SVC2 --> GT
    SVC3 --> GT

    subgraph Optional Admin Backfill
      B1["Select Disease + Lab Unit"]
      B2["Scan verified images without tasks"]
      B3["Bulk create missing tasks"]
    end
    B1 --> B2 --> B3 --> GT

    GT --> Q["Grading Queues <br/> (visible only if user eligible via DUR + user_roles)"]

    %% Dashboard and Revision
    Q --> DASH["Dashboard with My Gradings"]
    DASH --> REV["Revise Button for existing grades"]
    REV --> REVFUNC["revise_grading route"]
    REVFUNC --> REVCHECK["Validate user is original grader<br/>and task not finalized"]
    REVCHECK -->|Pass| REVFLOW["Load grading task with<br/>existing grade pre-filled"]
    REVCHECK -->|Fail| ERROR["Show error message"]

    %% 2-Week Restriction Logic
    Q -->|Task Assignment| TWOR{_has_user_graded_task_recently?}
    TWOR -->|Yes| BLOCK["Block Assignment - <br/>User graded this task<br/>within last 2 weeks"]
    TWOR -->|No| ASSIGN["Assign Task for Grading<br/>(After 2 weeks, user can<br/>grade in different slot)"]

    %% Reporting/Exports
    GT -.-> VIEW[["Denormalized View <br/> image×disease: resident, resident2, final, method"]]
    VIEW --> CSV["CSV Exports / Dashboards"]

    classDef db fill:#eef,stroke:#66f,stroke-width:1px
    classDef svc fill:#efe,stroke:#393,stroke-width:1px
    class DUR,GT,VIEW,REVFLOW db
    class SVC1,SVC2,SVC3 svc
```
