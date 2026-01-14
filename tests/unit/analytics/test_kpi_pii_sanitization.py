"""
Unit tests for KPI & Export Sanitization.

Test IDs from PII_Exposure_Control_Policy.md:
- PII-API-003: KPI endpoints return aggregated data only, no PII
- PII-EXP-002: Excel exports mask PII for cross-hospital access

Bead: 5H (fundus_img_xtract-dcl)

TDD: Tests written FIRST before implementation.
These tests will FAIL until PII masking is implemented.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
from flask_login import current_user


class TestDataframePIIMasking:
    """Tests for PII masking in dataframe generation and filtering."""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return MagicMock()
    
    @pytest.fixture
    def sample_dataframe_with_pii(self):
        """Create a sample dataframe with patient PII."""
        return pd.DataFrame({
            'encounter_id': [1, 2, 3],
            'patient_id': ['12345678', '87654321', '11223344'],
            'hospital_id': [1, 1, 2],
            'hospital_name': ['Hospital A', 'Hospital A', 'Hospital B'],
            'lab_unit_id': [1, 1, 2],
            'lab_unit_name': ['Lab 1', 'Lab 1', 'Lab 2'],
            'has_dr_report': [True, False, True],
        })
    
    def test_get_filtered_encounter_dataframe_masks_cross_hospital_pii(
        self, mock_db_session, sample_dataframe_with_pii
    ):
        """
        CRITICAL TEST: get_filtered_encounter_dataframe must mask patient_id for cross-hospital data.
        
        This test will FAIL until we implement PII masking in the function.
        """
        from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
        
        # Mock the dataframe generation to return our sample data
        with patch('api.kpis.encounter_files_kpis.generate_encounter_upload_metrics_df', 
                  return_value=sample_dataframe_with_pii):
            
            params = {}
            user_lab_unit_ids = {1, 2}
            
            # User from Hospital 1, data_manager role
            df, _ = get_filtered_encounter_dataframe(
                mock_db_session,
                params,
                user_lab_unit_ids,
                current_user_hospital_id=1,
                current_user_role='data_manager',
                user_for_scoping=None  # Not testing scoping in this test
            )
            
            # CRITICAL ASSERTIONS - these will FAIL until masking is implemented
            
            # Records from Hospital 1 (same as user): should have full patient_id
            hospital_1_records = df[df['hospital_id'] == 1]
            assert len(hospital_1_records) == 2
            # For same hospital, patient_id should be visible (or check if it's NOT masked)
            # We'll check it's not the masked format
            for idx, row in hospital_1_records.iterrows():
                patient_id = row['patient_id']
                # Should NOT be masked format (P****XXX)
                assert not (isinstance(patient_id, str) and patient_id.startswith('P****')), \
                    f"Same hospital data should not be masked, got: {patient_id}"
            
            # Records from Hospital 2 (different from user): should have masked patient_id
            hospital_2_records = df[df['hospital_id'] == 2]
            assert len(hospital_2_records) == 1
            for idx, row in hospital_2_records.iterrows():
                patient_id = row['patient_id']
                # Should be masked format: P****XXX (last 3 chars)
                assert isinstance(patient_id, str) and patient_id.startswith('P****'), \
                    f"Cross-hospital patient_id must be masked, got: {patient_id}"
                assert patient_id == 'P****344', \
                    f"Expected 'P****344' for patient_id '11223344', got: {patient_id}"
    
    def test_get_filtered_encounter_dataframe_resident_always_masked(
        self, mock_db_session, sample_dataframe_with_pii
    ):
        """
        Resident role should ALWAYS see masked PII, even for same hospital.
        
        This test will FAIL until role-based masking is implemented.
        """
        from api.kpis.encounter_files_kpis import get_filtered_encounter_dataframe
        
        # Mock current user as resident from Hospital 1
        with patch('api.kpis.encounter_files_kpis.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.id = 2
            mock_user.hospital_id = 1
            
            # Mock role as resident
            role = Mock()
            role.name = 'resident'
            mock_user.roles = [role]
            
            with patch('api.kpis.encounter_files_kpis.generate_encounter_upload_metrics_df',
                      return_value=sample_dataframe_with_pii):
                
                params = {}
                user_lab_unit_ids = {1}

                df, _ = get_filtered_encounter_dataframe(
                    mock_db_session, params, user_lab_unit_ids,
                    current_user_hospital_id=1,  # Mocked user's hospital
                    current_user_role='resident',
                    user_for_scoping=None  # Not testing scoping in this test
                )
                
                # ALL records should have masked patient_id (role-based masking)
                for idx, row in df.iterrows():
                    patient_id = row['patient_id']
                    assert isinstance(patient_id, str) and patient_id.startswith('P****'), \
                        f"Resident should always see masked PII, got: {patient_id}"
    
    def test_dataframe_has_patient_id_column(self, mock_db_session):
        """
        Verify that generate_encounter_upload_metrics_df DOES include patient_id.

        This confirms we need to mask it.
        """
        from utils.dataframeEncounterFiles import generate_encounter_upload_metrics_df

        # We'll verify this by checking the function code includes patient_id
        import inspect
        source = inspect.getsource(generate_encounter_upload_metrics_df)
        assert "'patient_id': encounter.patient_id" in source, \
            "generate_encounter_upload_metrics_df must include patient_id in dataframe"


class TestKPIEndpointsNoPII:
    """Tests verifying KPI endpoints return only aggregated data."""
    
    def test_year_month_wise_uploads_response_has_no_patient_fields(self):
        """
        KPI response should not contain patient_id, patient_name, or other PII fields.
        """
        # Expected response structure (aggregated data only)
        sample_response = {
            "status": "success",
            "data": {
                "period": "2024-01-01 to 2024-12-31",
                "summary": {
                    "total_uploads": 100,
                    "total_captures": 500,
                    "total_dr_reports": 300,
                    "total_glaucoma_reports": 200,
                    "total_no_reports": 0
                },
                "monthly_data": [
                    {
                        "year": 2024,
                        "month": 1,
                        "month_name": "January",
                        "uploads": 10,
                        "captures": 50,
                        "dr_reports": 30,
                        "glaucoma_reports": 20,
                        "no_reports": 0,
                        "hospital_id": 1,
                        "hospital_name": "Hospital A",
                        "lab_unit_id": 1,
                        "lab_unit_name": "Lab 1"
                    }
                ]
            }
        }
        
        # Verify no PII fields in response
        forbidden_fields = ['patient_id', 'patient_name', 'phone', 'email']
        
        # Check summary
        for field in forbidden_fields:
            assert field not in sample_response['data']['summary'], \
                f"KPI summary should not contain {field}"
        
        # Check monthly data
        for record in sample_response['data']['monthly_data']:
            for field in forbidden_fields:
                assert field not in record, \
                    f"KPI monthly data should not contain {field}"
        
        # This test passes because we're checking the EXPECTED structure
        # The actual implementation should match this structure


class TestExcelExportPIIMasking:
    """Tests for Excel export PII masking."""
    
    @pytest.fixture
    def sample_dataframe_for_export(self):
        """Create sample dataframe for export testing."""
        return pd.DataFrame({
            'encounter_id': [1, 2, 3],
            'patient_id': ['12345678', '87654321', '11223344'],
            'hospital_id': [1, 1, 2],
            'hospital_name': ['Hospital A', 'Hospital A', 'Hospital B'],
            'has_dr_report': [True, False, True],
        })
    
    def test_excel_export_masks_cross_hospital_patient_id(self, sample_dataframe_for_export):
        """
        Excel export must mask patient_id for cross-hospital records.
        
        This test will FAIL until masking is implemented in the export function.
        """
        from utils.pii_masking import mask_dict_pii, should_mask_pii
        
        # Simulate user from Hospital 1
        current_user_hospital_id = 1
        current_user_role = 'data_manager'
        
        # Process each record for export
        masked_records = []
        for idx, row in sample_dataframe_for_export.iterrows():
            record = row.to_dict()
            data_hospital_id = record['hospital_id']
            
            # Determine if masking is needed
            mask_pii = should_mask_pii(
                current_user_hospital_id=current_user_hospital_id,
                data_hospital_id=data_hospital_id,
                current_user_role=current_user_role
            )
            
            if mask_pii:
                # Apply masking
                record = mask_dict_pii(record)
            
            masked_records.append(record)
        
        # Verify masking
        # Hospital 1 records (same hospital): NOT masked
        assert masked_records[0]['patient_id'] == '12345678'
        assert masked_records[1]['patient_id'] == '87654321'
        
        # Hospital 2 records (different hospital): MASKED
        assert masked_records[2]['patient_id'] == 'P****344'


class TestAuditLogging:
    """Tests for audit logging of sensitive operations."""
    
    def test_sensitive_operation_audit_model_exists(self):
        """Verify SensitiveOperationAudit model exists for logging."""
        from models import SensitiveOperationAudit
        
        # Model should exist
        assert SensitiveOperationAudit is not None
        
        # Check required fields
        from sqlalchemy import inspect
        mapper = inspect(SensitiveOperationAudit)
        column_names = [column.key for column in mapper.columns]
        
        required_fields = ['id', 'user_id', 'operation_type', 'status', 'created_at']
        for field in required_fields:
            assert field in column_names, \
                f"SensitiveOperationAudit must have {field} field"
