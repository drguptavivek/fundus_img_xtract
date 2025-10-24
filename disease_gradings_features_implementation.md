# Implementation Plan for /diseases-gradings-features Route

## Overview
Add a new route to `api/disease.py` that returns a hierarchical JSON structure containing all gradings and their associated features for a given disease_id.

## Route Details
- **Path**: `/diseases-gradings-features/<int:disease_id>`
- **Method**: GET
- **Roles Required**: "admin", "data_manager", "ophthalmologist", "resident", "optometrist"
- **Response Format**: JSON

## Implementation Code

```python
@api_bp.route("/diseases-gradings-features/<int:disease_id>", methods=["GET"])
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_disease_gradings_features(disease_id: int):
    """API endpoint to get all gradings and features associated with a disease."""
    db = Session()
    try:
        # Get the disease
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if not disease:
            return jsonify({'error': 'Disease not found'}), 404
        
        # Get all gradings for this disease
        gradings = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id
        ).order_by(DiseaseGrading.display_order).all()
        
        # Build the hierarchical structure
        gradings_with_features = []
        for grading in gradings:
            # Get features for this grading
            features = db.query(GradingsFeatures).filter(
                GradingsFeatures.disease_grading_id == grading.id
            ).order_by(GradingsFeatures.sr_no).all()
            
            grading_data = {
                'id': grading.id,
                'impression': grading.impression,
                'display_order': grading.display_order,
                'is_active': grading.is_active,
                'guidelines': grading.guidelines,
                'features': [
                    {
                        'id': feature.id,
                        'sr_no': feature.sr_no,
                        'label': feature.label
                    } for feature in features
                ]
            }
            gradings_with_features.append(grading_data)
        
        # Build the final response
        response_data = {
            'disease': {
                'id': disease.id,
                'name': disease.name,
                'gradings': gradings_with_features
            }
        }
        
        return jsonify(response_data)
    finally:
        db.close()
```

## JSON Response Structure

The endpoint will return a JSON object with the following structure:

```json
{
  "disease": {
    "id": 1,
    "name": "Diabetic Retinopathy",
    "gradings": [
      {
        "id": 1,
        "impression": "No DR",
        "display_order": 1,
        "is_active": true,
        "guidelines": "No signs of diabetic retinopathy",
        "features": [
          {
            "id": 1,
            "sr_no": 1,
            "label": "Microaneurysms"
          },
          {
            "id": 2,
            "sr_no": 2,
            "label": "Hemorrhages"
          }
        ]
      }
    ]
  }
}
```

## Implementation Steps

1. Add the new route function to `api/disease.py`
2. Import the `GradingsFeatures` model (if not already imported)
3. Test the endpoint with a valid disease_id
4. Test error handling with an invalid disease_id
5. Verify the JSON structure matches the expected format

## Error Handling

- Returns 404 with error message if disease_id doesn't exist
- Database errors are handled by the try/finally pattern
- Proper session cleanup is ensured with the finally block

## Security

- Uses the same role-based access control as other disease endpoints
- Only allows users with appropriate roles to access the data
- Follows the same authentication pattern as existing routes