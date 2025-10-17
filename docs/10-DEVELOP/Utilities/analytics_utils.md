# Analytics Utilities Documentation

This document provides an overview of the utility functions available in the analytics module. These utilities are designed to help retrieve and process data related to encounters, tasks, and images.

## Table of Contents
- [General Utilities (`utils.py`)](#general-utilities-utilspy)
- [Encounter Utilities (`encounterUtils.py`)](#encounter-utilities-encounterutilspy)

## General Utilities (`utils.py`)

### Data Classes

#### `GradeSummary`
Render-friendly view of a single grade slot with fields for role, impression, grader, comment, and updated timestamp.

#### `ConsensusSummary`
Compact representation of consensus metadata with fields for impression, method, decided_by, and decided_at.

#### `AIGradeSummary`
Summarizes AI inference metadata for display with fields for model_name, model_version, impression, confidence, and run_id.

### Core Functions

#### `_summarize_grade(grade: Grade | None) -> Optional[GradeSummary]`

Converts a Grade object to a presentation-friendly GradeSummary object.

**Parameters:**
- `grade` (Grade | None): The Grade object to summarize

**Returns:**
- `Optional[GradeSummary]`: Summarized grade information or None if grade is None

#### `_summarize_consensus(consensus: Consensus | None) -> Optional[ConsensusSummary]`

Converts a Consensus object to a presentation-friendly ConsensusSummary object.

**Parameters:**
- `consensus` (Consensus | None): The Consensus object to summarize

**Returns:**
- `Optional[ConsensusSummary]`: Summarized consensus information or None if consensus is None

#### `fetch_image_task_details(db: SASession, tasks: Sequence[GradingTask]) -> List[Dict[str, Any]]`

Collects enriched details for the provided grading tasks.

**Parameters:**
- `db` (SASession): Active SQLAlchemy session
- `tasks` (Sequence[GradingTask]): Grading tasks to be enriched with related data

**Returns:**
- `List[Dict[str, Any]]`: A list of dictionaries, each containing presentation-ready data for one task

#### `_latest_glaucoma_cleaned(glaucoma_rows: Sequence[GlaucomaResultsCleaned]) -> Optional[Dict[str, Any]]`

Retrieves the most recent glaucoma results from a sequence of glaucoma results.

**Parameters:**
- `glaucoma_rows` (Sequence[GlaucomaResultsCleaned]): Sequence of glaucoma results

**Returns:**
- `Optional[Dict[str, Any]]`: Dictionary containing the latest glaucoma result data or None

#### `_latest_dr_report(dr_rows: Sequence[DiabeticRetinopathyReport]) -> Optional[Dict[str, Any]]`

Retrieves the most recent diabetic retinopathy report from a sequence of reports.

**Parameters:**
- `dr_rows` (Sequence[DiabeticRetinopathyReport]): Sequence of DR reports

**Returns:**
- `Optional[Dict[str, Any]]`: Dictionary containing the latest DR report data or None

#### `group_task_details_by_image(task_details: Sequence[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]`

Groups task details by image ID for organized display.

**Parameters:**
- `task_details` (Sequence[Dict[str, Any]]): Sequence of task detail dictionaries

**Returns:**
- `Dict[int, List[Dict[str, Any]]]`: Mapping of image IDs to lists of task details

#### `build_encounter_result_payload(encounters: Sequence[PatientEncounters], task_details: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]`

Builds a complete payload for encounter results display.

**Parameters:**
- `encounters` (Sequence[PatientEncounters]): Sequence of patient encounters
- `task_details` (Sequence[Dict[str, Any]]): Sequence of task detail dictionaries

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing complete encounter result data

## Encounter Utilities (`encounterUtils.py`)

Fetches a summary list of encounters with basic information. This can be used for the simplified analytics/encounters view.

**Parameters:**
- `filters` (dict, optional): Filters to apply to the query

**Returns:**
- `list`: A list of dictionaries with basic encounter information

### `get_encounters_with_non_pending_tasks()`

Fetches encounters that have images with associated non-pending tasks.

**Returns:**
- `list`: A list of dictionaries with encounter ID and associated task IDs, including disease and status for each task

### `get_direct_image_summary(uuid_str: str)`

Fetches a comprehensive summary for a direct image upload, including:
- All tasks associated with the image
- Task status and disease
- All gradings for each task
- Consensus for each task

**Parameters:**
- `uuid_str` (str): The UUID of the direct image upload

**Returns:**
- `dict`: A dictionary containing all the requested data for the direct image

## General Utilities (`utils.py`)

### `fetch_image_task_details(db: SASession, tasks: Sequence[GradingTask])`

Collects enriched details for the provided grading tasks.

**Parameters:**
- `db` (SASession): Active SQLAlchemy session
- `tasks` (Sequence[GradingTask]): Grading tasks that should be enriched with related data

**Returns:**
- `List[Dict[str, Any]]`: A list of dictionaries, each containing presentation-ready data for one task

### `group_task_details_by_image(task_details: Sequence[Dict[str, Any]])`

Groups task details by image ID.

**Parameters:**
- `task_details` (Sequence[Dict[str, Any]])`: Sequence of task details

**Returns:**
- `Dict[int, List[Dict[str, Any]]]`: A dictionary mapping image IDs to lists of task details

### `build_encounter_result_payload(encounters: Sequence[PatientEncounters], task_details: Sequence[Dict[str, Any]])`

Builds a payload containing encounter data with associated task details.

**Parameters:**
- `encounters` (Sequence[PatientEncounters]): Sequence of patient encounters
- `task_details` (Sequence[Dict[str, Any]])`: Sequence of task details

**Returns:**
- `List[Dict[str, Any]]`: A list of dictionaries containing encounter data with associated task details

## Data Classes

### `GradeSummary`
Render-friendly view of a single grade slot containing:
- role: the grading role (resident, faculty, arbitrator)
- impression: the grade impression
- grader: the username of the person who did the grading
- comment: any comment associated with the grade
- updated_at: timestamp when the grade was updated

### `ConsensusSummary`
Compact representation of consensus metadata containing:
- impression: the final impression
- method: the method used to reach consensus
- decided_by: the username of the person who made the decision
- decided_at: timestamp when the decision was made

### `AIGradeSummary`
Summarize AI inference metadata for display containing:
- model_name: the name of the AI model
- model_version: the version of the AI model
- impression: the AI's impression
- confidence: the confidence level in the grading
- run_id: the ID of the AI run