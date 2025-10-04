# Image Search Utilities Documentation

Calling functions should  use db_context_manager 

This module provides centralized functions for searching images across both direct uploads and ZIP uploads with various filters and task status information. It supports both direct image uploads and images from ZIP uploads with proper scoping based on user's lab units and role-based access controls.

## Functions

### `search_images`

Search images across both direct uploads and ZIP uploads with specified filters.

#### Parameters:
- `db_session`: Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to filter by
- `disease_ids` (Optional[List[int]]): List of disease IDs to filter by
- `camera_ids` (Optional[List[int]]): List of camera IDs to filter by
- `area_ids` (Optional[List[int]]): List of area IDs to filter by
- `is_mydriatic` (Optional[bool]): Filter for mydriatic status (True for mydriatic, False for non-mydriatic)
- `has_task_for_diseases` (Optional[List[int]]): List of disease IDs to check if tasks exist for
- `exclude_task_for_diseases` (Optional[List[int]]): List of disease IDs to exclude if tasks exist for
- `image_type` (Optional[str]): Filter for image type ('direct' or 'zip'), None for both
- `search_query` (Optional[str]): Search term to match against patient IDs, filenames, etc.

#### Returns:
Tuple of (list of image dictionaries, total count)

Each image dictionary contains:
- `id` (int): Image ID
- `uuid` (str): Image UUID
- `type` (str): Image type ('direct' or 'zip')
- `filename` (str): Name of the image file
- `file_path` (str): Full path to file (for direct uploads)
- `lab_unit` (str): Name of the lab unit
- `hospital` (str): Name of the hospital (for direct uploads)
- `camera` (str): Name of the camera (for direct uploads)
- `disease` (str): Name of the disease (for direct uploads)
- `area` (str): Name of the area (for direct uploads)
- `is_mydriatic` (bool): Whether the image is from a mydriatic capture (for direct uploads)
- `created_at` (datetime): When the image was created
- `has_tasks` (dict): Dictionary mapping disease names to whether a task exists for that disease

#### Access Control:
- Non-admin users can only see images in their assigned lab units
- Admin users can see all images regardless of lab unit

---

### `search_direct_images`

Search direct image uploads with specified filters.

#### Parameters:
- `db_session`: Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to filter by
- `disease_ids` (Optional[List[int]]): List of disease IDs to filter by
- `camera_ids` (Optional[List[int]]): List of camera IDs to filter by
- `area_ids` (Optional[List[int]]): List of area IDs to filter by
- `is_mydriatic` (Optional[bool]): Filter for mydriatic status (True for mydriatic, False for non-mydriatic)
- `has_task_for_diseases` (Optional[List[int]]): List of disease IDs to check if tasks exist for
- `exclude_task_for_diseases` (Optional[List[int]]): List of disease IDs to exclude if tasks exist for
- `search_query` (Optional[str]): Search term to match against patient IDs, filenames, etc.

#### Returns:
Tuple of (list of image dictionaries, total count)

Each image dictionary contains the same fields as in `search_images`, specifically for direct uploads.

#### Access Control:
- Non-admin users can only see images in their assigned lab units
- Admin users can see all images regardless of lab unit

---

### `search_zip_images`

Search images from ZIP uploads with specified filters.

#### Parameters:
- `db_session`: Database session to use for queries
- `page` (int): Page number for pagination (1-indexed), default is 1
- `per_page` (int): Number of items per page, default is 50
- `lab_unit_ids` (Optional[List[int]]): List of lab unit IDs to filter by
- `search_query` (Optional[str]): Search term to match against patient IDs, filenames, etc.

#### Returns:
Tuple of (list of image dictionaries, total count)

Each image dictionary contains the same fields as in `search_images`, specifically for ZIP uploads with patient information.

#### Access Control:
- Non-admin users can only see images in their assigned lab units
- Admin users can see all images regardless of lab unit

---

### `get_image_task_status`

Get task status for all diseases for a specific image.

#### Parameters:
- `db_session`: Database session to use for queries
- `image_id` (int): ID of the image
- `image_type` (str): Type of image ('direct' or 'zip')

#### Returns:
Dictionary mapping disease names to whether a task exists for that disease

#### Access Control:
- Non-admin users can only check images in their assigned lab units
- Admin users can check any image regardless of lab unit

---

### `bulk_create_tasks`

Create grading tasks for specified images and diseases.

#### Parameters:
- `db_session`: Database session to use for queries
- `image_ids` (List[int]): List of image IDs to create tasks for
- `image_type` (str): Type of image ('direct' or 'zip')
- `disease_ids` (List[int]): List of disease IDs to create tasks for
- `lab_unit_id` (int): Lab unit ID to associate with the tasks

#### Returns:
Dictionary with summary of created tasks:
- `created_tasks` (List[dict]): List of created task details
- `skipped_tasks` (List[dict]): List of skipped tasks (due to already existing)
- `total_created` (int): Total number of tasks created
- `total_skipped` (int): Total number of tasks skipped

#### Access Control:
- Only admin users or users with appropriate permissions can create tasks for images in their lab units