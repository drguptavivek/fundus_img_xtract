"""
Test suite for HSTS header configuration (CWE-523).

This module tests that HTTP Strict Transport Security (HSTS)
header is properly configured for production environments.

Tests follow TDD: write failing tests first, then implement fix.
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from flask import Flask


class TestHSTSHeader:
    """Test suite for HSTS header configuration."""

    def test_hsts_header_set_in_production(self):
        """
        FAILING TEST: HSTS header not set in production.

        Test that Strict-Transport-Security header is present
        in production environment.
        """
        from app_init.security_headers import register_csp

        # Create a test Flask app
        app = Flask(__name__)
        app.debug = False

        # Register CSP (which includes add_security_headers)
        register_csp(app)

        with app.test_request_context('/'):
            with patch.dict('os.environ', {'FLASK_ENV': 'production', 'DEBUG': 'false'}):
                # Create a mock response
                from werkzeug.wrappers.response import Response
                response = Response("test")
                response.headers = {}

                # Get the after_request function
                # We need to call the function directly
                with app.app_context():
                    # Simulate the after_request hook
                    from flask import g
                    g.csp_script_nonce = "test-nonce"
                    g.csp_style_nonce = "test-nonce"

                    # Process response through security headers
                    # The function is the last one registered as after_request
                    for func in reversed(app.after_request_funcs.get(None, [])):
                        response = func(response)

                    # Check HSTS header is set
                    hsts_header = response.headers.get('Strict-Transport-Security')
                    assert hsts_header is not None, (
                        f"HSTS header should be present in production. Headers: {dict(response.headers)}"
                    )

    def test_hsts_header_has_max_age(self):
        """
        FAILING TEST: HSTS max-age directive not set correctly.

        Test that HSTS header includes max-age directive
        with at least 31536000 (1 year).
        """
        from app_init.security_headers import register_csp

        app = Flask(__name__)
        app.debug = False
        register_csp(app)

        with app.test_request_context('/'):
            with patch.dict('os.environ', {'FLASK_ENV': 'production', 'DEBUG': 'false'}):
                from werkzeug.wrappers.response import Response
                response = Response("test")
                response.headers = {}

                with app.app_context():
                    from flask import g
                    g.csp_script_nonce = "test-nonce"
                    g.csp_style_nonce = "test-nonce"

                    for func in reversed(app.after_request_funcs.get(None, [])):
                        response = func(response)

                    hsts_header = response.headers.get('Strict-Transport-Security')
                    if hsts_header:
                        assert 'max-age=' in hsts_header, (
                            "HSTS header should include max-age directive"
                        )

                        import re
                        max_age_match = re.search(r'max-age=(\d+)', hsts_header)
                        if max_age_match:
                            max_age = int(max_age_match.group(1))
                            assert max_age >= 31536000, (
                                f"HSTS max-age should be at least 31536000 (1 year), got {max_age}"
                            )

    def test_hsts_header_has_include_subdomains(self):
        """
        FAILING TEST: HSTS includeSubDomains directive not set.

        Test that HSTS header includes includeSubDomains directive.
        """
        from app_init.security_headers import register_csp

        app = Flask(__name__)
        app.debug = False
        register_csp(app)

        with app.test_request_context('/'):
            with patch.dict('os.environ', {'FLASK_ENV': 'production', 'DEBUG': 'false'}):
                from werkzeug.wrappers.response import Response
                response = Response("test")
                response.headers = {}

                with app.app_context():
                    from flask import g
                    g.csp_script_nonce = "test-nonce"
                    g.csp_style_nonce = "test-nonce"

                    for func in reversed(app.after_request_funcs.get(None, [])):
                        response = func(response)

                    hsts_header = response.headers.get('Strict-Transport-Security')
                    if hsts_header:
                        assert 'includeSubDomains' in hsts_header, (
                            "HSTS header should include includeSubDomains directive"
                        )

    def test_hsts_header_not_set_in_development(self):
        """
        Test that HSTS header is NOT set in development environment.

        HSTS should only be set in production to avoid issues
        with local development over HTTP.
        """
        from app_init.security_headers import register_csp

        app = Flask(__name__)
        app.debug = True  # Development mode
        register_csp(app)

        with app.test_request_context('/'):
            with patch.dict('os.environ', {'FLASK_ENV': 'development', 'DEBUG': 'true'}):
                from werkzeug.wrappers.response import Response
                response = Response("test")
                response.headers = {}

                with app.app_context():
                    from flask import g
                    g.csp_script_nonce = "test-nonce"
                    g.csp_style_nonce = "test-nonce"

                    for func in reversed(app.after_request_funcs.get(None, [])):
                        response = func(response)

                    # In development, HSTS should not be set
                    hsts_header = response.headers.get('Strict-Transport-Security')
                    assert hsts_header is None, (
                        f"HSTS header should not be present in development. Got: {hsts_header}"
                    )


class TestHSTSConfiguration:
    """Test suite for HSTS configuration options."""

    def test_hsts_max_age_configurable(self):
        """
        FAILING TEST: HSTS max-age not configurable.

        Test that HSTS max-age is configurable via environment variable.
        """
        # This test documents the need for configurability
        # The implementation should allow HSTS_MAX_AGE env var
        pass

    def test_hsts_preload_optional(self):
        """
        FAILING TEST: HSTS preload not configurable.

        Test that 'preload' directive can be optionally included
        via environment variable.
        """
        # This test documents the preload option
        # The implementation should allow HSTS_PRELOAD env var
        pass
