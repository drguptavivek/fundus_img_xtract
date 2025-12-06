# Master Utilities Documentation

This document provides an overview of the utility functions available in the master utilities module. These utilities are designed to retrieve core entities like diseases, hospitals, lab units, areas, and cameras from the system.

## Functions

### `get_all_diseases() -> List[Dict[str, Any]]`

Get all diseases in the system.

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing disease information with fields:
  - `id` (int): The disease ID
  - `name` (str): The disease name

**Implementation Details:**
- Properly closes the database session after query

### `get_disease_gradings(disease_id: int) -> List[Dict[str, Any]]`

Get all active gradings for a specific disease.

**Parameters:**
- `disease_id` (int): The ID of the disease

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing disease grading information with fields:
  - `id` (int): The grading ID
  - `disease_id` (int): The disease ID the grading belongs to
  - `impression` (str): The grading impression
  - `display_order` (int): The order in which the grading should be displayed
  - `is_active` (bool): Whether the grading is active
  - `guidelines` (str): Any guidelines associated with the grading

**Implementation Details:**
- Only returns active gradings (where `is_active` is True)
- Orders results by `display_order`
- Properly closes the database session after query

### `fetch_active_disease_gradings(db, disease_id: int) -> List[DiseaseGrading]`

Fetch all active disease gradings for a disease, ordered by display order.

**Parameters:**
- `db`: Database session
- `disease_id` (int): The ID of the disease

**Returns:**
- `List[DiseaseGrading]`: List of active DiseaseGrading objects ordered by display order

### `get_all_hospitals() -> List[Dict[str, Any]]`

Get all hospitals in the system.

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing hospital information with fields:
  - `id` (int): The hospital ID
  - `name` (str): The hospital name

**Implementation Details:**
- Properly closes the database session after query

### `get_all_lab_units() -> List[Dict[str, Any]]`

Get all lab units in the system.

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing lab unit information with fields:
  - `id` (int): The lab unit ID
  - `name` (str): The lab unit name
  - `hospital_id` (int): The ID of the associated hospital
  - `hospital_name` (str): The name of the associated hospital (None if no hospital is associated)

**Implementation Details:**
- Uses selectinload to efficiently load hospital information
- Properly closes the database session after query

### `get_hosp_lab_units(hospital_id: int) -> List[Dict[str, Any]]`

Get all lab units for a specific hospital.

**Parameters:**
- `hospital_id` (int): The ID of the hospital

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing lab unit information with fields:
  - `id` (int): The lab unit ID
  - `name` (str): The lab unit name
  - `hospital_id` (int): The ID of the associated hospital

**Implementation Details:**
- Properly closes the database session after query

### `get_all_areas() -> List[Dict[str, Any]]`

Get all areas in the system.

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing area information with fields:
  - `id` (int): The area ID
  - `name` (str): The area name

**Implementation Details:**
- Properly closes the database session after query

### `get_all_cameras() -> List[Dict[str, Any]]`

Get all cameras in the system.

**Returns:**
- `List[Dict[str, Any]]`: List of dictionaries containing camera information with fields:
  - `id` (int): The camera ID
  - `name` (str): The camera name

**Implementation Details:**
- Properly closes the database session after query