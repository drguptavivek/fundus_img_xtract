# Help System

This module provides a comprehensive help system for the Fundus Image Manager application. It allows users to browse documentation written in Markdown format that is rendered as HTML in the frontend.

## Features

- **Markdown Documentation**: All help content is written in simple Markdown files for easy maintenance
- **HTML Rendering**: Markdown files are automatically converted to HTML when displayed
- **Navigation**: Sidebar navigation with automatic highlighting of the current page
- **Search**: Full-text search across all help documents
- **Responsive Design**: Mobile-friendly layout that works on all devices
- **Theme Support**: Automatically adapts to the application's light/dark theme

## Structure

```
help/
├── __init__.py          # Blueprint initialization
├── routes.py            # Route handlers for help pages
├── templates/
│   └── help/
│       ├── help_page.html    # Template for displaying help content
│       └── search.html       # Template for search results
└── README.md            # This file
```

Documentation files are stored in:
```
docs/user-guide/
├── README.md            # Main user guide (shown on help home)
├── getting-started.md   # Getting started guide
├── uploading-images.md  # Image upload instructions
├── grading-images.md    # Image grading instructions
├── viewing-analytics.md # Analytics guide
├── notifications.md     # Notifications guide
└── troubleshooting.md   # Troubleshooting guide
```

## Routes

- `/help/` - Help index page showing the main user guide
- `/help/<doc_path>` - View a specific help document
- `/help/search` - Search help documentation

## Adding New Documentation

1. Create a new Markdown file in the `docs/user-guide/` directory
2. Add a navigation link to the sidebar in `help/templates/help/help_page.html`
3. The document will be automatically available at `/help/<filename>`

## Styling

The help system uses the custom CSS file `static/css/help.css` which extends the application's existing Bootstrap theme. The styles are designed to be consistent with the rest of the application while providing optimal readability for documentation.

## Security

- All file paths are sanitized to prevent directory traversal attacks
- Only files within the `docs/user-guide/` directory can be accessed
- All routes require user authentication