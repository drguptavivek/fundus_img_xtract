# Analytics Utilities Documentation

This document provides an overview of the utility functions available in the analytics module. These utilities are designed to help retrieve and process data related to encounters, tasks, and images.

## Table of Contents
- [Task Utilities (`taskUtils.py`)](#task-utilities-taskutilspy)
- [Image Task Utilities (`imageTasks.py`)](#image-task-utilities-imagetaskspy)
- [Encounter Utilities (`encounterUtils.py`)](#encounter-utilities-encounterutilspy)
- [General Utilities (`utils.py`)](#general-utilities-utilspy)

## Task Utilities (`taskUtils.py`)

### `get_task_summary(task_id: int)`

Fetches a summary for a specific grading task, including:
- Task status
- Disease
- All grades for the task
- Consensus information if it exists

**Parameters:**
- `task_id` (int): The ID of the grading task

**Returns:**
- `dict`: A dictionary containing task status, disease, grades, and consensus

## Image Task Utilities (`imageTasks.py`)

### `get_tasks_for_image_uuid(uuid_str: str)`

Fetches all tasks associated with a specific image UUID. The function checks both encounter files and direct image uploads.

**Parameters:**
- `uuid_str` (str): The UUID of the image

**Returns:**
- `dict`: A dictionary containing all tasks associated with the image

### `get_tasks_for_encounter_image_uuid(uuid_str: str)`

Fetches all tasks associated with a specific encounter image UUID.

**Parameters:**
- `uuid_str` (str): The UUID of the encounter image

**Returns:**
- `dict`: A dictionary containing all tasks associated with the encounter image

### `get_tasks_for_direct_image_uuid(uuid_str: str)`

Fetches all tasks associated with a specific direct image upload UUID.

**Parameters:**
- `uuid_str` (str): The UUID of the direct image upload

**Returns:**
- `dict`: A dictionary containing all tasks associated with the direct image

### `get_task_ids_for_image_uuid(uuid_str: str)`

Fetches only the task IDs associated with a specific image UUID. The function checks both encounter files and direct image uploads.

**Parameters:**
- `uuid_str` (str): The UUID of the image

**Returns:**
- `list`: A list of task IDs associated with the image

## Encounter Utilities (`encounterUtils.py`)

### `get_encounter_summary(encounter_id: int, with_encounter_object: bool = False)`

Fetches a comprehensive summary for a given encounter, including:
- Image UUIDs
- Report PDF UUIDs
- Glaucoma results cleaned with their UUIDs
- Diabetic retinopathy reports with their UUIDs
- All tasks with their status, disease, and associated image
- All gradings for each task
- Consensus for each task
- Images with their associated task IDs and disease names

**Parameters:**
- `encounter_id` (int): The ID of the encounter to fetch summary for
- `with_encounter_object` (bool): Whether to include the full encounter object (may cause DetachedInstanceError if session closes)

**Returns:**
- `dict`: A dictionary containing all the requested data for the encounter

### `get_encounters_summary_list(filters=None)`

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