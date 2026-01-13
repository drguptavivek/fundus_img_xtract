# RBAC & ABAC Access Control

This document provides a comprehensive overview of the Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC) systems in the Fundus Image Manager.

The system implements a **Hybrid Access Control** model:
- **RBAC (Role-Based)**: Defines *what* a user can do (e.g., upload, grade, export) based on assigned roles.
- **ABAC (Attribute-Based)**: Defines *which* specific data instances a user can access based on attributes of the User, the Resource, and the Environment (Scoping).

For detailed technical implementation of isolation, see [Scoping.md](03-Tasks/Scoping.md).

---

## Role Matrix

| Role | Responsibility | Scoping Type | PII Access |
| :--- | :--- | :--- | :--- |
| `admin` | System-wide management | Master (Unrestricted) | Full |
| `local_admin` | Hospital-wide management | Hospital-Bound | Full |
| `optometrist` | Verification & Anonymization | Lab (Hospital-Bound) | Full |
| `ophthalmologist` | Grading & Arbitration | Slot (Cross-Hospital) | **None (Anonymized)** |
| `dataset_creator` | AI Training & Research | Cross-Hospital Ops | Partial (Masked) |
| `data_manager` | Operational oversight | Hospital-Bound | Full |
| `fileUploader` | Standard image ingestion | Lab (Hospital-Bound) | Full |
| `data_exporter` | Exporting datasets | Hospital-Bound | Partial (Masked) |
| `analytics_viewer` | KPI monitoring | Hospital-Bound | **None (Anonymized)** |
| `discrepancy_reviewer` | Quality assurance review | Hospital-Bound | **None (Masked)** |

---

## Detailed Role Descriptions

### System Administration

#### `admin` (Master Admin)
- **Permissions**: Full access to all system features including configuration, bulk data operations, and global audit logs.
- **Scoping**: Bypasses all filters. Can toggle between hospitals.
- **Workflow**: Assigned by developers or during initial seeding.

#### `local_admin` (Site Admin)
- **Permissions**: Full administrative control within a single hospital. Can create/edit users for their hospital.
- **Scoping**: Hospital-bound. Sees all lab units and images within their assigned hospital.
- **Workflow**: Manages the local operational team.

---

### Medical & Grading

#### `optometrist` (Verification Gatekeeper)
- **Permissions**: Responsible for reviewing uploaded images for quality and **anonymizing PII** (Step 2 of the workflow).
- **Scoping**: Lab-unit bound.
- **Security Role**: Acts as the firewall between PII-heavy ingestion and PII-free grading.

#### `ophthalmologist` / `resident`
- **Permissions**: Accesses the grading interface to provide diagnostic grades and perform arbitration.
- **Scoping**: **Slot-LabUnit scoping** (Cross-hospital). Assigned tasks based on disease expertise.
- **PII Protection**: Never sees patient names, MRNs, or source hospital identity.

---

### Research & Analytics

#### `dataset_creator`
- **Permissions**: Creates and manages datasets for AI training. Can trigger cross-hospital curation jobs.
- **Scoping**: Cross-hospital access explicitly for `dataset_creation`, `research`, and `training` operations.

#### `analytics_viewer`
- **Permissions**: Accesses the analytics dashboards to view KPIs and encounter statistics.
- **Scoping**: Hospital-bound. Access only to their own hospital's data.
- **PII Protection**: Analytics results are pre-sanitized/masked.

---

### Operations & Support

#### `data_manager`
- **Permissions**: General oversight of hospital operations. Can manage verification tasks and view reports.
- **Scoping**: Hospital-bound.

#### `fileUploader`
- **Permissions**: Core ingestion role. Uploads images to specific lab units.
- **Scoping**: Lab-unit bound.

#### `data_exporter`
- **Permissions**: Authorized to generate and download CSV/Excel/ZIP exports of data.
- **Scoping**: Hospital-bound. Filenames are automatically anonymized in exports.

#### `discrepancy_reviewer`
- **Permissions**: Involved in the QA process where human grades disagree, before finalization. Settles medical conflicts.
- **Scoping**: Hospital-bound.
- **PII Protection**: Operates on anonymized encounter IDs and masked metadata. Patient names/MRNs are hidden to prevent bias.

---

## Role-Blueprint PII Matrix

The following matrix defines where PII (Patient Name, MRN, Phone) is visible (`✅`), masked (`M`), or hidden (`❌`) across the system's core blueprints.

| Role | `direct_uploads` | `screenings` | `verification` | `review` | `analytics` | `grading` | `jobs` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `admin` (Master) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `local_admin` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | M |
| `data_manager` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | M |
| `optometrist` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | M |
| `discrepancy_reviewer`| ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | M |
| `ophthalmologist` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `analytics_viewer` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `dataset_creator` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `data_exporter` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `fileUploader` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | M |

> [!NOTE]
> **Blueprint Definitions**:
> - `verification`: Includes Remedio ZIP verification and post-upload quality checks.
> - `review`: Includes Discrepancy Review and Dataset Exports.
> - `analytics`: Includes Performance Dashboards and Dataset Curation.
> - `jobs`: Monitoring payloads for background operations (sanitized by default).

> [!NOTE]
> **PII Inconsistency**: `local_admin` and `data_manager` only see PII in ingestion and verification stages. Once data moves to `review` or `analytics`, it is masked for everyone except Master Admins.

---

## PII Access Rationale

The system follows a "PII Firewall" model where most clinical staff work anonymized, but certain operational roles require PII access for specific ingestion and compliance tasks:

| Role | Why they need PII? | Silo Boundary |
| :--- | :--- | :--- |
| **Data Manager** | Must resolve ingestion errors and EMR mismatches during the raw upload phase. | Own Hospital Only |
| **Local Admin** | Responsible for hospital-level legal compliance and patient follow-up requests. | Own Hospital Only |
| **Optometrist** | Required to verify patient identity *before* performing the anonymization step. | Own Hospital Only |
| **fileUploader** | Handles initial ingestion where PII is naturally present in source files/EMR. | Own Hospital Only |

> [!IMPORTANT]
> **Discrepancy Reviewer**: Unlike early ingestion roles, the Discrepancy Reviewer does **not** need PII. They use anonymous UUIDs and masked clinical metadata to reach a "ground truth" without the risk of bias or data leakage.

> [!WARNING]
> While these roles have *functional* access to PII in specific modules, the system still applies **scoping isolation**. A Data Manager at Hospital A can never see PII from Hospital B.

---

---

## Attribute-Based Access Control (ABAC)

While roles grant functional permissions, ABAC (implemented as "Scoping") restricts access to specific data records.

### Key Security Attributes

| Attribute Type | Name | Purpose |
| :--- | :--- | :--- |
| **User** | `hospital_id` | Primary organizational boundary for data isolation. |
| **User** | `lab_units` | Granular operational access within an assigned hospital. |
| **User** | `is_master_admin` | Boolean flag that bypasses attribute-based checks. |
| **Permission** | `UserDiseaseUnitRole` | Mapping of expertise (Disease + Lab Unit + Slot Capacity). |
| **Resource** | `lab_unit_id` | Identifies the origin of an image or task. |
| **Environment** | `created_at` | Used for the **2-Week Cooling-Off** temporal restriction. |

### ABAC Logic Implementation

1. **Hospital Isolation**: A user with role `fileUploader` can only upload to lab units where `lab_unit.hospital_id == user.hospital_id`.
2. **Dynamic Task Filtering**: An `ophthalmologist` only sees grading tasks where they have a matching `UserDiseaseUnitRole` entry for the specific `disease_id` and `lab_unit_id`.
3. **Temporal Constraint (Cooling-Off)**: Even if a user has the `ophthalmologist` role and correct `UserDiseaseUnitRole` attributes, the system denies access to a specific task if `current_time - last_grade.created_at < 14 days` for that same user.

---

## Role Assignment Logic

1. **Hierarchy**: Master Admins can assign any role. Site Admins can assign any role *except* `admin` to users within their hospital.
2. **Assignments**: Roles are assigned in the user management interface (`/admin/users/add`).
3. **Multi-Role Capability**: A single user account can hold multiple roles (e.g., a Site Admin who also performs Data Management).
4. **Consistency**: Role constants are defined in `auth/roles.py` and are enforced by the `@roles_required` decorator in Flask routes.
