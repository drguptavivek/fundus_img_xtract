# api/routes.py
# This file is kept for backward compatibility and to ensure the blueprint is properly initialized
# All API routes have been moved to modular files

# Import all route handlers from modular files
from . import disease_gradings, direct_uploads, jobs, hospitals, users, diseases, lab_units, comprehensive, lab_unit_disease_specialists, gradings, image_metadata, image_data, pdf_data, grading_eligibility

# The blueprint is imported from the modular files
