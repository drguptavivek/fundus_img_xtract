from pathlib import Path
import markdown
from flask import render_template, current_app, abort
from . import bp
from utils.rate_limiter import rate_limit
from utils.log_sanitize import sanitize_log_value


HELP_INDEX = {
    "title": "User Guide",
    "filename": "README.md",
}

HELP_PAGES = [
    {"slug": "getting-started", "title": "Getting Started", "filename": "getting-started.md"},
    {"slug": "uploading-images", "title": "Uploading Images", "filename": "uploading-images.md"},
    {"slug": "direct-uploads", "title": "Direct Uploads", "filename": "direct-uploads.md"},
    {"slug": "zip-uploads", "title": "ZIP Uploads", "filename": "zip-uploads.md"},
    {"slug": "pre-graded-uploads", "title": "Pre-Graded Uploads", "filename": "pre-graded-uploads.md"},
    {
        "slug": "verification-dr-glaucoma-zips",
        "title": "Verification of DR/Glaucoma",
        "filename": "verification-dr-glaucoma-zips.md",
    },
    {
        "slug": "verification-nodr-zips",
        "title": "Verification of No-DR ZIPs",
        "filename": "verification-nodr-zips.md",
    },
    {
        "slug": "direct-image-anonymization",
        "title": "Image Editing",
        "filename": "direct-image-anonymization.md",
    },
    {"slug": "grading-images", "title": "Grading Images", "filename": "grading-images.md"},
    {"slug": "viewing-analytics", "title": "Viewing Analytics", "filename": "viewing-analytics.md"},
    {"slug": "discrepancy-review", "title": "Discrepancy Review", "filename": "discrepancy-review.md"},
    {"slug": "notifications", "title": "Notifications", "filename": "notifications.md"},
    {"slug": "troubleshooting", "title": "Troubleshooting", "filename": "troubleshooting.md"},
    {"slug": "dataset-creation", "title": "Dataset Creation", "filename": "dataset-creation.md"},
    {"slug": "dataset-sharing", "title": "Dataset Sharing", "filename": "dataset-sharing.md"},
    {"slug": "dataset-download", "title": "Dataset Download", "filename": "dataset-download.md"},
]


def _docs_file_path(filename: str) -> Path:
    return (Path(current_app.root_path) / "docs" / "user-guide" / filename).resolve()


def read_markdown_file(filename: str) -> tuple[str | None, str | None]:
    """Read a markdown file from the user guide directory."""
    try:
        file_path = _docs_file_path(filename)
        if not file_path.is_file():
            return None, "File not found"
            
        with file_path.open('r', encoding='utf-8') as f:
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
        current_app.logger.error(
            "Error reading markdown file %s: %s",
            sanitize_log_value(filename),
            sanitize_log_value(e),
        )
        return None, str(e)


@bp.route("", strict_slashes=False)
@bp.route("/", strict_slashes=False)
@rate_limit("120 per minute")
def index():
    """Main help page - shows the user guide README."""
    content, error = read_markdown_file(HELP_INDEX["filename"])
    
    if error:
        abort(404)
    
    return render_template("help/help_page.html",
                         title=HELP_INDEX["title"],
                         content=content,
                         help_pages=HELP_PAGES,
                         is_main_page=True)


@bp.route("/<path:doc_path>")
@rate_limit("120 per minute")
def view_document(doc_path):
    """View a specific documentation file."""
    page_map = {page["slug"]: page for page in HELP_PAGES}
    page = page_map.get(doc_path)
    if not page:
        abort(404)

    content, error = read_markdown_file(page["filename"])
    
    if error:
        abort(404)
    
    return render_template("help/help_page.html", 
                         title=page["title"],
                         content=content,
                         help_pages=HELP_PAGES,
                         current_path=doc_path,
                         is_main_page=False)
