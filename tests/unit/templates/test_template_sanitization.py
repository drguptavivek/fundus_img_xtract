
import pytest
from flask import Flask, render_template_string
from utils.log_sanitize import mask_text_emails

class TestTemplateSanitization:
    """Test suite for template PII protection."""

    @pytest.fixture
    def app(self):
        """Create a Flask app with the mask_text_emails filter registered."""
        app = Flask(__name__)
        app.jinja_env.filters["mask_text_emails"] = mask_text_emails
        return app

    def test_filter_masks_email_in_template(self, app):
        """Test that the filter works within a Jinja2 template context."""
        template_str = "{{ comment|mask_text_emails }}"
        comment = "Please contact support@hospital.com for help."
        
        with app.app_context():
            rendered = render_template_string(template_str, comment=comment)
            
        assert "support@hospital.com" not in rendered
        assert "su***@hospital.com" in rendered

    def test_filter_handles_none(self, app):
        """Test filter handles None gracefully."""
        template_str = "{{ comment|mask_text_emails }}"
        
        with app.app_context():
            rendered = render_template_string(template_str, comment=None)
            
        assert rendered == ""

    def test_filter_handles_safe_string(self, app):
        """Test filter leaves safe strings alone."""
        template_str = "{{ comment|mask_text_emails }}"
        comment = "This is a safe comment."
        
        with app.app_context():
            rendered = render_template_string(template_str, comment=comment)
            
        assert rendered == "This is a safe comment."
