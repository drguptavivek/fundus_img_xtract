# api/routes.py
# This file is kept for backward compatibility and to ensure the blueprint is properly initialized
# All API routes have been moved to modular files

# Import all route handlers from modular files
from . import disease_gradings, disease_specializations, direct_uploads, jobs, hospitals, users, diseases, lab_units, comprehensive, lab_unit_disease_specialists, gradings

# The blueprint is imported from the modular files