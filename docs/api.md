# Fundus Image Manager API Documentation

This document provides comprehensive documentation for the RESTful API endpoints available in the Fundus Image Manager application.

## Authentication

Most API endpoints require authentication. Users must be logged in to access the API. Some endpoints have additional role-based access controls.

### Authentication Headers

All API requests should include proper authentication cookies from the Flask session.

### Role-Based Access

Different endpoints require different user roles:
- `admin`: Full access to all endpoints
- `data_manager`: Access to most data management endpoints
- `ophthalmologist`: Access to disease-related and grading endpoints
- `resident`: Limited access to specific endpoints

## Base URL

All API endpoints are prefixed with `/api`. For example: `https://your-domain.com/api/diseases`

✦ Based on my analysis of the codebase, I can see that there are several API endpoints that are used in the frontend JavaScript files. Here's what I've
  found:

   1. In the JavaScript files, there are fetch calls to various endpoints:
      - /ping endpoint in idle-timeout.js for checking user activity
      - Form action URLs in dr_edit.js and glaucoma_edit.js for submitting form data
      - Save and restore URLs in edit_image.js for image editing functionality

   2. In the Python API files, I found several API endpoints:
      - Direct uploads API:
        - /api/users/<int:user_id>/lab-units (GET)
        - /api/lab-units/<int:lab_unit_id>/hospital (GET)
        - /api/upload-jobs/<int:job_id>/status (GET)

      - Grading eligibility API:
        - /api/grading-eligibility/users/<int:user_id> (GET)
        - /api/grading-eligibility/users/<int:user_id>/details (GET)

      - Gradings API:
        - /api/gradings (GET)

  Looking at the JavaScript code, I can see that most of these API endpoints are used for specific functionalities:

   1. Authentication/User Management: The /ping endpoint in idle-timeout.js is used to keep the user session alive.

   2. Medical Data Management: Various form submission endpoints in dr_edit.js and glaucoma_edit.js are used to update medical records.

   3. Image Editing: The save and restore endpoints in edit_image.js are used for managing edited medical images.

   4. Direct Uploads: API endpoints for managing lab units and upload job statuses.

   5. Grading: API endpoints for retrieving and managing medical image gradings.

  The frontend JavaScript code communicates with the backend API through fetch requests with proper headers for CSRF protection and JSON data exchange.
  Most of the API calls include error handling and update the UI dynamically without full page reloads.
  