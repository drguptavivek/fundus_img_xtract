# docs/swagger_ui.py
import os
import yaml
import json
from flask import render_template_string, abort, url_for
from . import docs_bp

# Get the base directory of the application
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Swagger UI template
SWAGGER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Fundus Image Manager API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui.css">
    <style>
        html {
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }
        *,
        *:before,
        *:after {
            box-sizing: inherit;
        }
        body {
            margin:0;
            background: #fafafa;
        }
        .auth-note {
            background-color: #fff3cd;
            border-color: #ffeaa7;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid transparent;
            border-radius: 0.375rem;
        }
        .instructions {
            background-color: #d1ecf1;
            border-color: #bee5eb;
            padding: 15px;
            margin: 10px 0;
            border: 1px solid transparent;
            border-radius: 0.375rem;
        }
    </style>
</head>
<body>
    <div class="auth-note">
        <strong>Authentication Required:</strong> This API requires authentication via session cookies.
    </div>
    <div class="instructions">
        <strong>Before Testing Endpoints:</strong>
        <ol>
            <li>Ensure you are logged into the application in this browser</li>
            <li>Some endpoints may require specific user roles (admin, data_manager, etc.)</li>
            <li>If you get 403 Forbidden errors, check that your user account has the required permissions</li>
        </ol>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@4.15.5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            const ui = SwaggerUIBundle({
                url: "{{ spec_url }}",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                requestInterceptor: function(request) {
                    // Ensure credentials are included for cross-origin requests
                    request.credentials = 'include';
                    return request;
                }
            });
            window.ui = ui;
        };
    </script>
</body>
</html>
"""

@docs_bp.route('/swagger')
def swagger_ui():
    """Serve Swagger UI for API testing and discovery."""
    spec_url = url_for('docs.openapi_spec')
    return render_template_string(SWAGGER_TEMPLATE, spec_url=spec_url)

@docs_bp.route('/swagger.json')
def swagger_json():
    """Serve the OpenAPI specification as JSON (converted from YAML)."""
    try:
        docs_dir = os.path.join(BASE_DIR, 'docs')
        with open(os.path.join(docs_dir, 'openapi.yaml'), 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        return json.dumps(yaml_content), 200, {'Content-Type': 'application/json'}
    except FileNotFoundError:
        abort(404)
    except Exception as e:
        abort(500)