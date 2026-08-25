from uuid import uuid4

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from models import DirectImageUpload, EncounterFile
from review.discrepancy_export import ExportTaskRow

@pytest.mark.security
def test_load_direct_paths_prioritizes_edited(app, db_session):
    """
    Verify that _load_direct_paths uses edited_filename if available.
    """
    from review.discrepancy_export import _load_direct_paths
    
    # 1. Setup mock data
    unique_folder1 = "unique_folder_for_anonymization_test_1"
    unique_folder2 = "unique_folder_for_anonymization_test_2"
    
    img1 = DirectImageUpload(
        uuid="test-uuid-prioritize-edited",
        filename="original1.jpg",
        edited_filename="edited1.jpg",
        folder_rel=unique_folder1,
        file_hash="hash1_unique",
        uploader_id=1, hospital_id=1, lab_unit_id=1, camera_id=1, disease_id=1, area_id=1
    )
    img2 = DirectImageUpload(
        uuid="test-uuid-no-edited",
        filename="original2.jpg",
        edited_filename=None,
        folder_rel=unique_folder2,
        file_hash="hash2_unique",
        uploader_id=1, hospital_id=1, lab_unit_id=1, camera_id=1, disease_id=1, area_id=1
    )
    db_session.add_all([img1, img2])
    db_session.flush()
    db_session.refresh(img1)
    db_session.refresh(img2)
    # 2. Call the function
    mapping = _load_direct_paths([img1.id, img2.id])
    
    # 3. Verify
    assert img1.id in mapping
    path1, ext1 = mapping[img1.id]
    assert unique_folder1 in str(path1)
    assert "edited/edited1.jpg" in str(path1).replace("\\", "/")
    assert ext1 == ".jpg"
    
    assert img2.id in mapping
    path2, ext2 = mapping[img2.id]
    assert unique_folder2 in str(path2)
    assert "original2.jpg" in str(path2).replace("\\", "/")
    assert "edited" not in str(path2)
    assert ext2 == ".jpg"

@pytest.mark.security
def test_dashboard_image_list_export_anonymization(app, db_session):
    """
    Verify that dashboard image_list export uses UUID filenames and seeds no PII.
    """
    from dashboard.routes import image_list
    from flask import request
    import pandas as pd
    import io

    # 1. Setup data
    img = DirectImageUpload(
        uuid="secret-uuid-123",
        filename="PATIENT_NAME_PII.jpg", # <--- PII
        folder_rel="files/direct/1",
        file_hash="hash1",
        uploader_id=1, hospital_id=1, lab_unit_id=1, camera_id=1, disease_id=1, area_id=1
    )
    db_session.add(img)
    db_session.commit()

    # The dashboard now authorizes and scopes before exporting, so this needs a
    # logged-in user holding the image's lab unit. The assertions below are
    # about PII in the export, not about access control.
    from flask_login import login_user
    from models import LabUnit
    from tests.helpers.factories import UserFactory

    lab_unit = db_session.get(LabUnit, 1)
    exporter = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"anonymization_exporter_{uuid4().hex[:8]}",
        lab_units=[lab_unit] if lab_unit else [],
    )
    db_session.commit()

    # 2. Simulate export request
    with app.test_request_context('/dashboard/images?export=csv'):
        login_user(exporter)
        # We need to mock get_db_session or ensure the test session is used
        # Since the route uses get_db_session which is a context manager
        # In tests, we often mock it or rely on the app context.
        
        from dashboard.routes import image_list
        response = image_list()
        
        assert response.status_code == 200
        assert response.mimetype == 'text/csv'
        
        # Parse CSV
        csv_data = response.data.decode('utf-8')
        df = pd.read_csv(io.StringIO(csv_data))
        
        # 3. Assertions
        assert len(df) >= 1
        row = df[df['UUID'] == 'secret-uuid-123'].iloc[0]
        
        # Legitimate data
        assert row['UUID'] == 'secret-uuid-123'
        
        # ANONYMIZED data
        assert row['Filename'] == 'secret-uuid-123.jpg'
        assert 'PATIENT_NAME_PII' not in csv_data, "PII filename leaked in dashboard export!"

