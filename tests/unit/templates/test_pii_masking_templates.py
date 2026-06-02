
import pytest
from flask import render_template
from unittest.mock import Mock, MagicMock


class NoneReturningMock:
    """Mock that returns None for undefined attributes instead of creating new Mocks."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        return None

    def __str__(self):
        return "NoneReturningMock"

    def __repr__(self):
        return f"<NoneReturningMock>"

class TestTemplatePIIMasking:
    """Test that templates mask PII when data is restricted (None)."""

    @pytest.fixture
    def mock_encounter_no_pii(self):
        """Create a mock encounter with PII set to None."""
        encounter = NoneReturningMock(
            id=123,
            name=None,
            patient_id='',  # Use empty string instead of None to avoid |length errors in template
            capture_date="2023-01-01",
            capture_date_dt=None,
            lab_unit=None,
            zip_file=None,
            encounter_file_pdfs=[],
            encounter_files=[],
            encounter_verified_status='not_verified',
            dr_verified_status='not_verified',
            glaucoma_verified_status='not_verified',
            dr_verified_by=None,
            glaucoma_verified_by=None,
            encounter_verified_by=None,
            encounter_verified_at=None
        )
        return encounter

    @pytest.fixture
    def mock_dr_report_row_no_pii(self, mock_encounter_no_pii):
        """Create a mock DR report row with PII set to None."""
        row = NoneReturningMock(
            id=456,
            patient_encounter=mock_encounter_no_pii,
            result=None,
            qualitative_result=None,
            uuid=None,
            report_file_name=None,
            vcdr_right=None,
            vcdr_left=None,
            vcdr_right_num=None,
            vcdr_left_num=None
        )
        return row

    @pytest.fixture
    def mock_glaucoma_report_row_no_pii(self, mock_encounter_no_pii):
        """Create a mock Glaucoma report row with PII set to None."""
        row = NoneReturningMock(
            id=789,
            patient_encounter=mock_encounter_no_pii,
            result=None,
            qualitative_result=None,
            report_uuid=None,
            report_file_name=None,
            vcdr_right=None,
            vcdr_left=None,
            vcdr_right_num=None,
            vcdr_left_num=None
        )
        return row

    def test_screenings_detail_masking(self, app, mock_encounter_no_pii):
        """Test screenings/detail.html masks PII."""
        with app.app_context():
            # Mock current_user to avoid errors
            user = Mock(id=1, is_authenticated=True)
            user.has_role.return_value = False

            with app.test_request_context():
                html = render_template(
                    'screenings/detail.html',
                    encounter=mock_encounter_no_pii,
                    current_user=user,
                    back_url="#",
                    source_context={"intake_label": "Manual", "intake_class": "text-bg-light", "workflow_label": None, "workflow_class": None},
                    images=[],
                    dr_reports=[],
                    gl_reports=[]
                )

            assert "Anonymous" in html
            assert "Hidden" in html
            # Ensure PII fields show masked values in HTML
            assert '>Anonymous<' in html or 'value="Anonymous"' in html
            assert '>Hidden<' in html or 'value="Hidden"' in html
            # Exclude filter UI section and CSS from "None" check
            # (The "None" button label is for image filters, not masked data)
            # Remove the entire sv-filters section
            import re
            html_without_filters = re.sub(r'<div class="sv-filters.*?</div>', '', html, flags=re.DOTALL)
            html_cleaned = html_without_filters.replace("display: None", "")
            # Verify no "None" appears in data fields
            assert "None" not in html_cleaned, f"Found 'None' in HTML: {[line for line in html_cleaned.split('\\n') if 'None' in line]}"

    def test_verify_remedio_dr_edit_masking(self, app, mock_dr_report_row_no_pii):
        """Test verify_remedio_dr/edit.html masks PII."""
        with app.app_context():
            user = Mock(id=1, is_authenticated=True)
            user.has_role.return_value = False

            with app.test_request_context():
                # Mock current_user_has template function
                def mock_has_role(role):
                    return False

                html = render_template(
                    'verify_remedio_dr/edit.html',
                    row=mock_dr_report_row_no_pii,
                    current_user=user,
                    current_user_has=mock_has_role,
                    back_url="#"
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
                    back_url="#",
                    prev_url=None,
                    next_url=None
                )
            assert "Anonymous" in html

    def test_verify_remedio_glaucoma_edit_masking(self, app, mock_glaucoma_report_row_no_pii):
        """Test verify_remedio_glaucoma/edit.html masks PII."""
        with app.app_context():
            user = Mock(id=1, is_authenticated=True)
            user.has_role.return_value = False

            with app.test_request_context():
                # Mock current_user_has template function
                def mock_has_role(role):
                    return False

                html = render_template(
                    'verify_remedio_glaucoma/edit.html',
                    row=mock_glaucoma_report_row_no_pii,
                    current_user=user,
                    current_user_has=mock_has_role,
                    back_url="#"
                )
            assert "Anonymous" in html
