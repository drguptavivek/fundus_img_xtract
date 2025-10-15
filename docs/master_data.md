# Master Data Management

This document describes the core reference data (master data) that is essential for the operation of the Fundus Image Manager application. Master data includes entities that are relatively static and serve as reference points for various operations throughout the system.

## Core Master Data Entities

### Hospitals

Hospital entities represent the medical facilities where images are captured and patients are treated. The system tracks hospitals to organize data by institution and manage access control.

#### Current Hospitals (from setup_core_entities.py)
| ID | Name |
|----|------|
| 1 | RPC AIIMS |
| 2 | GTB Hospital |

### Laboratory Units (Lab Units)

Lab units are organizational subdivisions within hospitals that handle image processing and grading workflows. Each lab unit is associated with a specific hospital and serves as a scope for task assignment and workload management.

#### Current Lab Units (from setup_core_entities.py)
| ID | Name | Hospital ID |
|----|------|-------------|
| 1 | Community Ophthalmology | 1 (RPC AIIMS) |
| 2 | Retina Lab | 1 (RPC AIIMS) |
| 3 | Glaucoma Lab | 1 (RPC AIIMS) |
| 4 | Corena Lab | 2 (GTB Hospital) |
| 5 | Retina | 2 (GTB Hospital) |
| 6 | Glaucoma | 2 (GTB Hospital) |

### Cameras

Camera entities represent the various imaging devices used to capture fundus images. The system tracks camera types to support different image sources and processing requirements.

#### Current Cameras (from setup_core_entities.py)
| ID | Name |
|----|------|
| 1 | Remedio FOP |
| 2 | Zeiss Cirrus HD-OCT |
| 3 | Heidelberg Spectralis |
| 4 | Optos Daytona |
| 5 | Nidek RS-3000 Advance |
| 6 | Kowa VX-10 |
| 7 | Canon CR-2 AF |
| 8 | Carl Zeiss Meditec VISUCAM 500 |
| 9 | Topcon Maestro2 |

### Areas

Area entities represent anatomical regions of focus for fundus imaging. These help categorize images based on the primary area being examined.

#### Current Areas (from setup_core_entities.py)
| ID | Name |
|----|------|
| 1 | Retina Macular Focus |
| 2 | Retina Disc Focus |
| 3 | Cornea |
| 4 | Both Eyes |

### Diseases and Gradings

The system manages eye diseases with their corresponding grading categories for standardized evaluation. Each disease has multiple grading levels defined in the DiseaseGrading table.

#### Core Diseases
The system primarily manages three eye diseases:
- Diabetic Retinopathy (DR)
- Glaucoma
- Age-related Macular Degeneration (AMD)

Each disease has associated grading levels (impressions) that are used for standardized evaluation:
- Disease-specific severity levels
- Normal/No disease findings
- Not-gradable categories with specific reasons

### User Roles and Permissions

The system implements role-based access control with the following core roles:

| Role | Description |
|------|-------------|
| Admin | System administrator with full system access |
| Data Manager | Manages data uploads and exports |
| Resident Grader | Junior medical staff performing initial grading |
| Faculty Grader | Senior medical staff performing secondary grading |
| Arbitrator | Senior ophthalmologist resolving grading disputes |
| Viewer | Read-only access to reports and analytics |

#### User-Lab Unit Relationships
Users can be associated with multiple lab units, allowing them to work across different organizational units while maintaining proper access boundaries based on their roles and permissions.

## Master Data Setup Script

The `scripts/setup_core_entities.py` script initializes the database with essential master data. The script creates the following core entities:

```python
# Core hospitals
CORE_HOSPITALS = [
    {"id": 1, "name": "RPC AIIMS"},
    {"id": 2, "name": "GTB Hospital"}
]

# Core lab units (associated with hospitals)
CORE_LAB_UNITS = [
    {"id": 1, "name": "Community Ophthalmology", "hospital_id": 1},
    {"id": 2, "name": "Retina Lab", "hospital_id": 1},
    {"id": 3, "name": "Glaucoma Lab", "hospital_id": 1},
    {"id": 4, "name": "Corena Lab", "hospital_id": 2},
    {"id": 5, "name": "Retina", "hospital_id": 2},
    {"id": 6, "name": "Glaucoma", "hospital_id": 2}
]

# Core cameras
CORE_CAMERAS = [
    {"id": 1, "name": "Remedio FOP"},
    {"id": 2, "name": "Zeiss Cirrus HD-OCT"},
    {"id": 3, "name": "Heidelberg Spectralis"},
    {"id": 4, "name": "Optos Daytona"},
    {"id": 5, "name": "Nidek RS-3000 Advance"},
    {"id": 6, "name": "Kowa VX-10"},
    {"id": 7, "name": "Canon CR-2 AF"},
    {"id": 8, "name": "Carl Zeiss Meditec VISUCAM 500"},
    {"id": 9, "name": "Topcon Maestro2"}
]

# Core areas
CORE_AREAS = [
    {"id": 1, "name": "Retina Macular Focus"},
    {"id": 2, "name": "Retina Disc Focus"},
    {"id": 3, "name": "Cornea"},
    {"id": 4, "name": "Both Eyes"}
]
```

## Master Data Usage in the Application

### Direct Image Uploads
When users upload images directly, they must select from the master data:
- Hospital (from the hospitals table)
- Lab Unit (filtered by selected hospital)
- Camera (from the cameras table)
- Disease (from the diseases table)
- Area (from the areas table)

### Task Assignment
Grading tasks are assigned based on:
- Lab unit affiliation of the image
- User permissions for specific diseases and lab units
- Role-based grading workflow (resident → faculty → arbitrator)

### Access Control
- Users can only access images from their assigned lab units
- Role permissions determine what actions users can perform
- Hospital and lab unit relationships provide organizational boundaries

## Utility Functions and APIs for Master Data

### Master Data Utilities
Located in [`utils/masterUtils.py`](utils/masterUtils.py):

- **[`get_all_diseases()`](utils/masterUtils.py:12)**: Returns all diseases in the system
- **[`get_disease_gradings(disease_id)`](utils/masterUtils.py:33)**: Returns active gradings for a specific disease
- **[`fetch_active_disease_gradings(db, disease_id)`](utils/masterUtils.py:65)**: Fetches active disease gradings ordered by display
- **[`get_all_hospitals()`](utils/masterUtils.py:82)**: Returns all hospitals in the system
- **[`get_all_lab_units()`](utils/masterUtils.py:103)**: Returns all lab units with hospital information
- **[`get_hosp_lab_units(hospital_id)`](utils/masterUtils.py:126)**: Returns lab units for a specific hospital
- **[`get_all_areas()`](utils/masterUtils.py:153)**: Returns all areas in the system
- **[`get_all_cameras()`](utils/masterUtils.py:174)**: Returns all cameras in the system

### API Endpoints for Master Data

#### Hospital APIs
Located in [`api/hospitals.py`](api/hospitals.py):

- **[`GET /api/hospitals`](api/hospitals.py:19)**: Get all hospitals
- **[`GET /api/hospitals/<hospital_id>`](api/hospitals.py:41)**: Get a specific hospital by ID

#### Lab Unit APIs
Located in [`api/labUnits.py`](api/labUnits.py):

- **[`GET /api/hospitals/<hospital_id>/labunits`](api/labUnits.py:19)**: Get all lab units for a specific hospital
- **[`GET /api/labunits`](api/labUnits.py:49)**: Get all lab units with hospital information
- **[`GET /api/labunits/<lab_unit_id>`](api/labUnits.py:74)**: Get a specific lab unit by ID

#### Disease APIs
Located in [`api/disease.py`](api/disease.py):

- **[`GET /api/disease-grades/<disease_id>`](api/disease.py:9)**: Get grades applicable to a specific disease
- **[`GET /api/diseases-with-gradings`](api/disease.py:38)**: Get all diseases with their associated gradings

### Implementation Examples

#### Getting Master Data for Forms
```python
from utils.masterUtils import get_all_hospitals, get_all_lab_units, get_all_cameras

def get_upload_form_data():
    """Get master data for upload form"""
    return {
        'hospitals': get_all_hospitals(),
        'lab_units': get_all_lab_units(),
        'cameras': get_all_cameras()
    }
```

#### Getting Lab Units for a Hospital
```python
from utils.masterUtils import get_hosp_lab_units

def get_hospital_lab_units(hospital_id):
    """Get lab units for a specific hospital"""
    return get_hosp_lab_units(hospital_id)
```

#### Using API Endpoints
```javascript
// Get all hospitals
fetch('/api/hospitals')
  .then(response => response.json())
  .then(data => console.log(data));

// Get lab units for a hospital
fetch('/api/hospitals/1/labunits')
  .then(response => response.json())
  .then(data => console.log(data));
```

## Maintenance and Updates

### Adding New Entities
1. Update the appropriate list in `setup_core_entities.py`
2. Run the script to create/update the database
3. The script will create new entities or update existing ones

### Modifying Existing Entities
1. Update the entity definition in `setup_core_entities.py`
2. Run the script - it will update existing entities if they have different data
3. Changes are logged to the console during script execution

### Running the Setup Script
```bash
python -m scripts.setup_core_entities
```

The script handles both creation and updates, ensuring that the master data remains consistent across different environments.