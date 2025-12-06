# Upload Eligibility Utilities Documentation

This document provides an overview of the utility functions available in the upload eligibility module. These utilities are designed to help determine user eligibility for uploading and verifying images in specific lab units and hospitals.

## Functions

### `get_user_uploadVerify_eligibility(user_id: int) -> Dict[str, Any]`

Return upload eligibility details for the given user.

The payload contains the user identity and a hospital → lab unit mapping describing where the user is permitted to upload images. Data is read from the `user_lab_units` association table via the `User.lab_units` relationship.

**Parameters:**
- `user_id` (int): The primary key of the user.

**Returns:**
- `Dict` containing user identity information (`user_id`, `username`, `full_name`) and a `hospitals` collection. When the user does not exist or has no associated lab units, the mapping will contain an empty `hospitals` list.

**Return Structure:**
- `user_id` (int): The ID of the user
- `username` (str): The username of the user
- `full_name` (str): The full name of the user
- `hospitals` (List[Dict]): A list of hospitals with associated lab units, where each hospital entry contains:
  - `hospital_id` (int): The ID of the hospital
  - `hospital_name` (str): The name of the hospital
  - `lab_units` (List[Dict]): A list of associated lab units, where each lab unit entry contains:
    - `lab_unit_id` (int): The ID of the lab unit
    - `lab_unit_name` (str): The name of the lab unit

**Implementation Details:**
- Admin users have access to all lab units in the system
- Non-admin users have access only to their assigned lab units
- The function properly closes database sessions to prevent connection leaks
- Lab units are sorted by ID for deterministic output

### `get_user_lab_unit_ids(user_id: int) -> Set[int]`

Return the set of lab unit IDs the user is allowed to access.

**Parameters:**
- `user_id` (int): The ID of the user

**Returns:**
- `Set[int]`: A set of lab unit IDs that the user is allowed to access

**Implementation Details:**
- Admin users have access to all lab units in the system
- Non-admin users have access only to their assigned lab units
- The function properly closes database sessions to prevent connection leaks