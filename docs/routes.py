# docs/routes.py
import os
import markdown
from markdown_mermaid import makeExtension
from flask import send_from_directory, abort, render_template_string, current_app
from . import docs_bp
from utils.rate_limiter import rate_limit

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
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>
    <script>
        console.log("Mermaid.js script loaded.");
        mermaid.initialize({ startOnLoad: true });
        console.log("Mermaid.js initialized with startOnLoad: true.");
    </script>
</body>
</html>
"""

@docs_bp.route('/api.md')
@rate_limit("60 per minute")
def api_docs():
    """Serve the API documentation markdown file."""
    docs_dir = os.path.join(BASE_DIR, 'docs')
    try:
        return send_from_directory(docs_dir, 'api.md', mimetype='text/markdown')
    except FileNotFoundError:
        abort(404)

@docs_bp.route('/api.html')
@rate_limit("60 per minute")
def api_docs_html():
    """Serve the API documentation as HTML."""
    docs_dir = os.path.join(BASE_DIR, 'docs')
    try:
        with open(os.path.join(docs_dir, 'api.md'), 'r', encoding='utf-8') as f:
            content = markdown.markdown(f.read(), extensions=['fenced_code', 'tables', makeExtension()])
        
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

@docs_bp.route('/openapi.yaml')
@rate_limit("60 per minute")
def openapi_spec():
    """Serve the OpenAPI specification YAML file."""
    docs_dir = os.path.join(BASE_DIR, 'docs')
    try:
        return send_from_directory(docs_dir, 'openapi.yaml', mimetype='text/yaml')
    except FileNotFoundError:
        abort(404)

@docs_bp.route('/')
@rate_limit("60 per minute")
def docs_index():
    """Serve the documentation index."""
    docs_dir = os.path.join(BASE_DIR, 'docs')
    try:
        with open(os.path.join(docs_dir, 'README.md'), 'r', encoding='utf-8') as f:
            content = markdown.markdown(f.read(), extensions=['fenced_code', 'tables', makeExtension()])
        current_app.logger.info("--- DEBUG: Markdown Content ---")
        current_app.logger.info(content)
        current_app.logger.info("--- END DEBUG ---")
        
        return render_template_string(MARKDOWN_TEMPLATE, 
                                    title="Documentation", 
                                    content=content)
    except FileNotFoundError:
        abort(404)
    except Exception:
        # Fallback to plain text if markdown processing fails
        try:
            with open(os.path.join(docs_dir, 'README.md'), 'r', encoding='utf-8') as f:
                content = f.read().replace('\n', '<br>')
            return render_template_string(MARKDOWN_TEMPLATE, 
                                        title="Documentation", 
                                        content=content)
        except FileNotFoundError:
            abort(404)