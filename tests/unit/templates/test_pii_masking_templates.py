
import pytest
from flask import render_template
from unittest.mock import Mock, MagicMock

class TestTemplatePIIMasking:
    """Test that templates mask PII when data is restricted (None)."""

    @pytest.fixture
    def mock_encounter_no_pii(self):
        """Create a mock encounter with PII set to None."""
        encounter = Mock()
        encounter.id = 123
        encounter.name = None
        encounter.patient_id = None
        # Add other necessary fields to avoid render errors
        encounter.capture_date = "2023-01-01"
        encounter.capture_date_dt = None
        encounter.lab_unit = None
        encounter.zip_file = None
        encounter.encounter_file_pdfs = []
        return encounter

    def test_screenings_detail_masking(self, app, mock_encounter_no_pii):
        """Test screenings/detail.html masks PII."""
        with app.app_context():
            # Mock current_user to avoid errors
            user = Mock(id=1, is_authenticated=True) 
            user.has_role.return_value = False
            
            with app.test_request_context():
                # Inject user into template context
                with pytest.warns(None) as record: # Suppress unrelated warnings
                    html = render_template(
                        'screenings/detail.html',
                        encounter=mock_encounter_no_pii,
                        current_user=user,
                        back_url="#",
                        images=[],
                        dr_reports=[],
                        gl_reports=[]
                    )
                    
            assert "Anonymous" in html 
            assert "Hidden" in html
            # Ensure "None" string is NOT present for these fields
            assert "None" not in html.replace("display: None", "") # Ignore CSS

    def test_verify_remedio_dr_edit_masking(self, app, mock_encounter_no_pii):
        """Test verify_remedio_dr/edit.html masks PII."""
        with app.app_context():
            user = Mock(id=1, is_authenticated=True)
            
            with app.test_request_context():
                 html = render_template(
                    'verify_remedio_dr/edit.html',
                    encounter=mock_encounter_no_pii,
                    current_user=user,
                    form=Mock(), # Mock form
                    images=[]
                )
            assert "Anonymous" in html

    def test_verify_remedio_nodr_edit_masking(self, app, mock_encounter_no_pii):
        """Test verify_remedio_nodr/edit.html masks PII."""
        with app.app_context():
            user = Mock(id=1, is_authenticated=True)
            
            with app.test_request_context():
                 html = render_template(
                    'verify_remedio_nodr/edit.html',
                    encounter=mock_encounter_no_pii,
                    current_user=user,
                    form=Mock(),
                    images=[]
                )
            assert "Anonymous" in html

    def test_verify_remedio_glaucoma_edit_masking(self, app, mock_encounter_no_pii):
        """Test verify_remedio_glaucoma/edit.html masks PII."""
        with app.app_context():
            user = Mock(id=1, is_authenticated=True)
            
            with app.test_request_context():
                 html = render_template(
                    'verify_remedio_glaucoma/edit.html',
                    encounter=mock_encounter_no_pii,
                    current_user=user,
                    form=Mock(),
                    images=[]
                )
            assert "Anonymous" in html
