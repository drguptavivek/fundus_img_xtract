# Fundus Image Manager Documentation

This folder contains documentation for the Fundus Image Manager application.

## Available Documentation

- [API Documentation](api.html) - Comprehensive documentation for all RESTful API endpoints
- [OpenAPI Specification](openapi.yaml) - Machine-readable OpenAPI 3.0 specification for the API
- [Application Overview](details.html) - General information about the application
- [Main Processing Pipeline](main.html) - Documentation for the main data processing pipeline
- [Models](models.html) - Database schema documentation
- [App Factory](app.html) - Documentation for the application factory

## API Documentation

The [API documentation](api.html) provides detailed information about all available RESTful API endpoints, including:

- Endpoint URLs and HTTP methods
- Required authentication and authorization
- Request parameters
- Response formats
- Error codes

## OpenAPI Specification

The [OpenAPI specification](openapi.yaml) provides a machine-readable description of the API that can be used with tools like:

- Swagger UI for interactive API documentation
- Code generation tools to create client SDKs
- API testing tools
- Documentation generators

This specification follows the OpenAPI 3.0 standard and includes comprehensive schema definitions for all request and response objects.

## Other Documentation

Additional documentation files provide information about the application architecture, data processing pipeline, and database schema.

- [Audit Documentation](audit.html)
- [Build Themes Documentation](BUILD_THEMES.html)
- [Changelog](CHANGELOG.html)
- [Direct Uploads Documentation](direct_uploads.html)
- [Grading Documentation](Grading.html)
- [Logging Documentation](Logging.html)
- [OCR Extraction Documentation](ocr_extraction.html)
- [Process PDFs Documentation](process_pdfs.html)
- [Routes Documentation](routes.html)
- [Security Documentation](Security.html)
- [Template Route Links Check](template_route_links_check.html)
- [ZIP Uploads Documentation](zip_uploads.html)

## Application Workflow Flowchart

```mermaid
flowchart TD
    subgraph Ingestion & Initial Processing
        A[ZIP Upload] --> B[Extract Files - Images & PDFs];
        B --> C[Validate & MD5 Hash];
        C --> D1[Assign UUIDs to Images];
        C --> D2[Assign UUIDs to PDFs];

        E[Direct Image Upload] --> F[Assign UUID & Metadata];
    end

    subgraph Processing & Anonymization
        D1 --> G[Image Anonymization];
        F --> G;

        D2 --> H[Process PDFs - OCR & Data Extraction];
        H --> I[Store OCR Data in DB & Assign UUIDs to Reports];
    end

    subgraph Verification
        I --> J[Manual Data Verification - OCR Data & Laterality Tagging];
        G --> K[Direct Image Anonymization Verification];
    end

    subgraph Clinical Grading
        J --> L[Image Ready for Grading];
        K --> L;

        L --> M[Grading Dashboard];
        M --> N[Start Grading - Random Ungraded Image];
        N --> O[Advanced Image Viewer & Impression Selection];
        O --> P[Save Grade - Upsert Logic];
    end

    P --> Q[Image Ready for AI Model Training/Validation];

    style A fill:#f9f,stroke:#333,stroke-width:2px;
    style E fill:#f9f,stroke:#333,stroke-width:2px;
    style Q fill:#bbf,stroke:#333,stroke-width:2px;

```

## Usage

Developers can use this documentation to:
- Integrate with the Fundus Image Manager API
- Extend the application's functionality
- Troubleshoot issues
- Understand the system architecture