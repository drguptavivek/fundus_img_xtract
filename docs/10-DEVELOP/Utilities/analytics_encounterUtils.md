# Encounter Analytics Utilities Documentation

This document provides an overview of the utility functions available in the encounter analytics module. These utilities are designed to help retrieve and process encounter-related data for analytics purposes.

## Functions

### `get_encounter_summary(encounter_id: int, with_encounter_object: bool = False) -> dict`

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


### `get_encounters_summary_list(filters=None) -> list`

Fetches a summary list of encounters with basic information.
This can be used for the simplified analytics/encounters view.

**Parameters:**
- `filters` (dict, optional): Filters to apply to the query

**Returns:**
- `list`: A list of dictionaries with basic encounter information


### `get_encounters_with_non_pending_tasks(user_lab_unit_ids=None, is_admin_like=False) -> list`

Fetches encounters that have images with associated non-pending tasks.

**Parameters:**
- `user_lab_unit_ids` (set): Set of lab unit IDs the user has access to
- `is_admin_like` (bool): Whether the user has admin-like permissions

**Returns:**
- `list`: A list of dictionaries with encounter ID and associated task IDs, including disease and status for each task


### `get_direct_image_summary(uuid_str: str) -> dict`

Fetches a comprehensive summary for a direct image upload, including:
- All tasks associated with the image
- Task status and disease
- All gradings for each task
- Consensus for each task

**Parameters:**
- `uuid_str` (str): The UUID of the direct image upload

**Returns:**
- `dict`: A dictionary containing all the requested data for the direct image