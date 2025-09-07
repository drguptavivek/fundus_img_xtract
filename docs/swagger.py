# docs/swagger.py
import os
from flask import render_template_string, send_from_directory, abort, url_for
from . import docs_bp

# Get the base directory of the application
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Simple HTML template for rendering markdown as HTML
MARKDOWN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            padding: 20px;
        }
        .markdown-content {
            max-width: 900px;
            margin: 0 auto;
        }
        pre {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }
        code {
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="markdown-content">
        {{ content|safe }}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

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
    </style>
</head>
<body>
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
                layout: "StandaloneLayout"
            });
            window.ui = ui;
        };
    </script>
</body>
</html>
"""

@docs_bp.route('/api.html')
def api_docs_html():
    """Serve the API documentation as HTML."""
    docs_dir = os.path.join(BASE_DIR, 'docs')
    try:
        with open(os.path.join(docs_dir, 'api.md'), 'r', encoding='utf-8') as f:
            import markdown
            content = markdown.markdown(f.read(), extensions=['fenced_code', 'tables'])
        
        return render_template_string(MARKDOWN_TEMPLATE, 
                                    title="API Documentation", 
                                    content=content)
    except FileNotFoundError:
        abort(404)
    except Exception:
        # Fallback to plain text if markdown processing fails
        try:
            with open(os.path.join(docs_dir, 'api.md'), 'r', encoding='utf-8') as f:
                content = f.read().replace('\n', '<br>')
            return render_template_string(MARKDOWN_TEMPLATE, 
                                        title="API Documentation", 
                                        content=content)
        except FileNotFoundError:
            abort(404)

@docs_bp.route('/swagger')
def swagger_ui():
    """Serve Swagger UI for API testing and discovery."""
    spec_url = url_for('docs.openapi_spec')
    return render_template_string(SWAGGER_TEMPLATE, spec_url=spec_url)

@docs_bp.route('/swagger.json')
def swagger_json():
    """Serve the OpenAPI specification as JSON (converted from YAML)."""
    try:
        import yaml
        import json
        docs_dir = os.path.join(BASE_DIR, 'docs')
        with open(os.path.join(docs_dir, 'openapi.yaml'), 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        return json.dumps(yaml_content), 200, {'Content-Type': 'application/json'}
    except FileNotFoundError:
        abort(404)
    except Exception as e:
        abort(500)