"""
WSGI entry point for Gunicorn server.

This module provides the WSGI application interface that Gunicorn uses
to serve the Flask application in production.
"""

import os
from app import create_app

# Load environment variables from .env file
# This ensures all configuration is available before the app is created
from dotenv import load_dotenv
load_dotenv()

# Expand environment variables that reference other variables
# This handles cases like DATABASE_URL=${POSTGRES_APP_USER}:${POSTGRES_APP_PASSWORD}@...
for key, value in os.environ.items():
    if isinstance(value, str) and '${' in value:
        # Expand environment variable references
        try:
            expanded = os.path.expandvars(value)
            os.environ[key] = expanded
        except Exception as e:
            print(f"Warning: Could not expand {key}: {e}")

# Create the Flask application instance
# The app will use the environment variables loaded above
app = create_app()

# Expose the WSGI application
# Gunicorn will look for this 'application' variable by default
application = app

if __name__ == "__main__":
    # This block allows running the WSGI file directly for testing
    app.run(debug=True, host="127.0.0.1", port=5001)