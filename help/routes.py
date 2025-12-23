import os
import markdown
from flask import render_template, request, current_app, abort
from flask_login import login_required
from . import bp
from utils.rate_limiter import rate_limit


def read_markdown_file(relative_path):
    """Read a markdown file from the docs directory."""
    try:
        # Get the absolute path to the docs directory
        docs_dir = os.path.join(current_app.root_path, 'docs')
        file_path = os.path.join(docs_dir, relative_path)
        
        if not os.path.exists(file_path):
            return None, "File not found"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Convert markdown to HTML
        html_content = markdown.markdown(
            content,
            extensions=[
                'markdown.extensions.extra',
                'markdown.extensions.codehilite',
                'markdown.extensions.toc',
                'markdown.extensions.tables'
            ]
        )
        
        return html_content, None
    except Exception as e:
        current_app.logger.error(f"Error reading markdown file {relative_path}: {str(e)}")
        return None, str(e)


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@rate_limit("120 per minute")
def index():
    """Main help page - shows the user guide README."""
    print("Help index route called!")
    content, error = read_markdown_file("user-guide/README.md")
    
    if error:
        print(f"Error reading markdown: {error}")
        abort(404)
    
    return render_template("help/help_page.html",
                         title="User Guide",
                         content=content,
                         is_main_page=True)


@bp.route("/<path:doc_path>")
@rate_limit("120 per minute")
def view_document(doc_path):
    """View a specific documentation file."""
    # Security check - only allow paths within user-guide directory
    if ".." in doc_path or doc_path.startswith("/"):
        abort(400)
    
    # Construct the full path
    full_path = f"user-guide/{doc_path}"
    
    # If no extension provided, try .md
    if not os.path.splitext(full_path)[1]:
        full_path += ".md"
    
    content, error = read_markdown_file(full_path)
    
    if error:
        abort(404)
    
    # Extract title from first heading or use filename
    title = doc_path.replace("-", " ").replace("_", " ").title()
    if content:
        # Try to extract title from first # heading
        lines = content.split('\n')
        for line in lines:
            if line.strip().startswith('<h1'):
                # Extract text from h1 tag
                import re
                match = re.search(r'<h1[^>]*>(.*?)</h1>', line)
                if match:
                    title = match.group(1).strip()
                    break
    
    return render_template("help/help_page.html", 
                         title=title,
                         content=content,
                         current_path=doc_path,
                         is_main_page=False)
