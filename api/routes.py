# api/routes.py
# This file is kept for backward compatibility and to ensure the blueprint is properly initialized
# All API routes have been moved to modular files

# Import all route handlers from modular files
from . import direct_uploads, gradings, grading_eligibility
# The blueprint is imported from the modular files
