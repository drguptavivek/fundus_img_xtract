# Image Search Utilities Documentation

This document provides an overview of the utility functions available in the image search utilities module. These utilities are designed for searching images across direct uploads and ZIP uploads with various filters and proper scoping based on user access rights.

## Module Overview

This module provides centralized functions for searching images with various filters and determining if they already have grading tasks for different diseases. It supports both direct image uploads and images from ZIP uploads with proper scoping based on user's lab units and role-based access controls.

**Key Features:**
- Strict filter separation (direct filters exclude ZIP images and vice versa)
- UUID-based returns (no original filenames)
- Task disease information for grading workflow
- Proper user lab unit scoping
- Comprehensive error handling and logging

## Classes

### `ImageSearchError(Exception)`

Custom exception for image search errors.

## Functions

### `validate_search_filters(filters: Dict[str, Any], image_type: Optional[str] = None) -> str`

Validate all filters and determine search scope.

**Parameters:**
- `filters` (Dict[str, Any]): Dictionary of search filters
- `image_type` (Optional[str]): Explicit image type restriction ('direct', 'zip', or None)

**Returns:**
- `str`: Search scope: 'direct_only', 'zip_only', or 'both'

**Raises:**
- `ImageSearchError`: If filters are invalid or conflicting

### `validate_pagination(page: int, per_page: int) -> Tuple[int, int]`

Validate and normalize pagination parameters.

**Parameters:**
- `page` (int): Page number (1-indexed)
- `per_page` (int): Items per page

**Returns:**
- `Tuple[int, int]`: Tuple of validated (page, per_page)

**Raises:**
- `ImageSearchError`: If pagination parameters are invalid

### `get_user_search_scope(user_id: int, db_session: Session) -> Tuple[Set[int], bool]`

Get user's lab unit IDs and admin status for search scoping.

**Parameters:**
- `user_id` (int): User ID for scoping
- `db_session` (Session): Database session

**Returns:**
- `Tuple[Set[int], bool]`: Tuple of (lab_unit_ids, is_admin)

### `build_direct_query(db_session: Session, filters: Dict[str, Any], user_lab_unit_ids: Set[int], is_admin: bool)`

Build query for direct images with all applicable filters.

**Parameters:**
- `db_session` (Session): Database session
- `filters` (Dict[str, Any]): Dictionary of filters to apply
- `user_lab_unit_ids` (Set[int]): Set of lab unit IDs user can access
- `is_admin` (bool): Whether user is admin

**Returns:**
- SQLAlchemy query object for direct images

### `build_zip_query(db_session: Session, filters: Dict[str, Any], user_lab_unit_ids: Set[int], is_admin: bool)`

Build query for ZIP images with all applicable filters.

**Parameters:**
- `db_session` (Session): Database session
- `filters` (Dict[str, Any]): Dictionary of filters to apply
- `user_lab_unit_ids` (Set[int]): Set of lab unit IDs user can access
- `is_admin` (bool): Whether user is admin

**Returns:**
- SQLAlchemy query object for ZIP images

### `get_tasks_for_multiple_images(db_session: Session, image_ids: List[int], image_type: str) -> Dict[int, List[Dict[str, str]]]`

Get task diseases with status for multiple images efficiently.

**Parameters:**
- `db_session` (Session): Database session
- `image_ids` (List[int]): List of image IDs
- `image_type` (str): Type of image ('direct' or 'zip')

**Returns:**
- `Dict[int, List[Dict[str, str]]]`: Dictionary mapping image_id to list of dictionaries with disease name and task status

### `format_direct_image_with_tasks(item: DirectImageUpload, task_diseases: List[str]) -> Dict[str, Any]`

Format direct image with pre-fetched task information.

**Parameters:**
- `item` (DirectImageUpload): DirectImageUpload object
- `task_diseases` (List[str]): List of disease names with tasks for this image

**Returns:**
- `Dict[str, Any]`: Formatted image dictionary with fields:
  - `uuid` (str): Image UUID
  - `type` (str): 'direct'
  - `upload_date` (datetime): Upload date
  - `capture_date` (datetime): Capture date
  - `hospital` (str): Hospital name
  - `lab_unit` (str): Lab unit name
  - `camera` (str): Camera name
  - `disease` (str): Disease name
  - `area` (str): Area name
  - `is_mydriatic` (bool): Whether the image is mydriatic
  - `tasks_for_diseases` (List[str]): List of diseases with tasks for this image
  - `uploader` (str): Uploader username
  - `file_hash` (str): File hash if available

### `format_zip_image_with_tasks(item: EncounterFile, task_diseases: List[str], db_session: Session) -> Dict[str, Any]`

Format ZIP image with pre-fetched task information.

**Parameters:**
- `item` (EncounterFile): EncounterFile object
- `task_diseases` (List[str]): List of disease names with tasks for this image
- `db_session` (Session): Database session

**Returns:**
- `Dict[str, Any]`: Formatted image dictionary with fields:
  - `uuid` (str): Image UUID
  - `type` (str): 'zip'
  - `upload_date` (datetime): Upload date
  - `capture_date` (datetime): Capture date
  - `hospital` (str): Hospital name
  - `lab_unit` (str): Lab unit name
  - `has_dr_report` (bool): Whether the image has a DR report
  - `has_glaucoma_report` (bool): Whether the image has a glaucoma report
  - `tasks_for_diseases` (List[str]): List of diseases with tasks for this image
  - `encounter_id` (int): Encounter ID for ZIP images

### `log_search_request(user_id: int, filters: Dict[str, Any], search_scope: str, page: int, per_page: int) -> None`

Log search request for debugging and audit.

**Parameters:**
- `user_id` (int): User ID making the request
- `filters` (Dict[str, Any]): Applied filters
- `search_scope` (str): Determined search scope
- `page` (int): Page number
- `per_page` (int): Items per page

### `log_search_results(user_id: int, search_scope: str, total_count: int, execution_time: float) -> None`

Log search results for performance monitoring.

**Parameters:**
- `user_id` (int): User ID making the request
- `search_scope` (str): Search scope used
- `total_count` (int): Total results found
- `execution_time` (float): Query execution time in seconds

### `log_search_error(user_id: int, error: Exception, filters: Dict[str, Any]) -> None`

Log search errors for debugging.

**Parameters:**
- `user_id` (int): User ID making the request
- `error` (Exception): Exception that occurred
- `filters` (Dict[str, Any]): Filters that were applied

### `search_images_strict(db_session: Session, page: int = 1, per_page: int = 50, hospital_id: Optional[int] = None, lab_unit_ids: Optional[List[int]] = None, upload_start: Optional[_date] = None, upload_end: Optional[_date] = None, camera_ids: Optional[List[int]] = None, disease_ids: Optional[List[int]] = None, area_ids: Optional[List[int]] = None, is_mydriatic: Optional[bool] = None, has_dr_report: Optional[bool] = None, has_glaucoma_report: Optional[bool] = None, capture_start: Optional[_date] = None, capture_end: Optional[_date] = None, search_query: Optional[str] = None, user_id: Optional[int] = None, image_type: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]`

Search images with strict filter separation and UUID-based returns.

This function implements strict filter separation:
- Direct filters (camera, disease, area, is_mydriatic) exclude ZIP images
- ZIP filters (has_dr_report, has_glaucoma_report, capture_date) exclude Direct images
- Global filters (hospital, lab_unit, upload dates) apply to both when no specific filters

**Parameters:**
- `db_session` (Session): Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `hospital_id` (Optional[int]): Hospital ID to filter by (global filter)
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to filter by (global filter)
- `upload_start` (Optional[_date]): Filter for upload date start (global filter)
- `upload_end` (Optional[_date]): Filter for upload date end (global filter)
- `camera_ids` (Optional[List[int]]): List of camera IDs to filter by (direct filter)
- `disease_ids` (Optional[List[int]]): List of disease IDs to filter by (direct filter)
- `area_ids` (Optional[List[int]]): List of area IDs to filter by (direct filter)
- `is_mydriatic` (Optional[bool]): Filter for mydriatic status (direct filter)
- `has_dr_report` (Optional[bool]): Filter for DR report status (ZIP filter)
- `has_glaucoma_report` (Optional[bool]): Filter for Glaucoma report status (ZIP filter)
- `capture_start` (Optional[_date]): Filter for capture date start (ZIP filter)
- `capture_end` (Optional[_date]): Filter for capture date end (ZIP filter)
- `search_query` (Optional[str]): Search term to match against UUIDs and other fields
- `user_id` (Optional[int]): User ID for scoping (defaults to current_user)

**Returns:**
- `Tuple[List[Dict[str, Any]], int]`: Tuple of (list of image dictionaries, total count)

**Raises:**
- `ImageSearchError`: If filters are invalid or conflicting

## Module Constants

### `__all__`

List of public module members: ['search_images_strict', 'ImageSearchError']