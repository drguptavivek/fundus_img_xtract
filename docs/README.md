# Fundus Image Manager Documentation

This directory contains documentation for the Fundus Image Manager application.

## Documentation Files

1. **routes.md** - Complete list of all application routes with details
2. **routes_by_blueprint.md** - Routes organized by blueprint for easier navigation
3. **template_route_links_check.md** - Verification of template links to ensure no broken routes

## Overview

The Fundus Image Manager is a comprehensive system for managing retinal fundus images in an eye hospital setting. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD).

## Key Features

- Data ingestion from ZIP archives and standalone images
- Image processing and anonymization
- Automated and manual verification workflows
- Masked clinical grading for unbiased assessments
- Data quality assurance and auditing
- User management with role-based access control

## Technology Stack

- **Backend**: Python, Flask
- **Database**: SQLAlchemy (ORM)
- **Frontend**: Jinja2 Templates, Vanilla JavaScript, Bootstrap 5.3
- **Key Libraries**: Pytesseract (OCR), Pandas, Numpy, Maplotlib