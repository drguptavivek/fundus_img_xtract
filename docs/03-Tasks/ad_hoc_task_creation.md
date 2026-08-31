# Ad-hoc task creation

Ad-hoc task creation is an exceptional, web-only workflow for creating additional grading targets from existing classical image sources.

## Authorization

- The caller must hold the global `data_manager` role and may use only classical sources in their assigned Lab Units.
- `admin` is break-glass, but project records remain excluded because configured project EncounterSet packages are created by the project workflow.
- Project grants, including project `data_manager` and `project_admin`, confer no ad-hoc authority.
- Search, preview, creation, batch listing, and batch detail are restricted to classical records.

## Creation contract

- The browser supplies only a source kind (`direct` or `zip`) and source ID.
- The server resolves the source and derives its Hospital and Lab Unit. Client-supplied lineage is never trusted or persisted.
- Missing lineage, inconsistent lineage, a project association, an unauthorized Lab Unit, or any invalid reference denies the complete request.
- Linked diseases cannot be selected or expanded by this workflow. The root disease task is created first; linked follow-up remains part of the grading workflow.
- All references and diseases are validated before the batch or any task is inserted. Duplicate tasks return a conflict and the whole transaction rolls back.
- Created tasks are image-level original-source tasks with `task_source="ad_hoc"`.

Configured EncounterSet packages, encounter-level targets, individual EncounterSet-image scopes, and their linked disease scopes are not modified here.
