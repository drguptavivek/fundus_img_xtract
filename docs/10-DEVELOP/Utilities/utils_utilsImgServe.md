# Image Serving Utilities Documentation

This document provides an overview of the utility functions available in the image serving utilities module. These utilities are designed to serve various types of images and reports by UUID.

## Module Overview

This module provides utility functions for serving various types of images and reports by UUID, including encounter images from ZIP uploads, direct image uploads, and associated reports like DR and glaucoma reports.

## Functions

### `encounterImageByUUID(uuid: str)`

Serve an encounter image from ZIP uploads by UUID.

**Parameters:**
- `uuid` (str): The UUID of the encounter image to serve

**Returns:**
- Flask response with the image file

**Implementation Details:**
- Queries the database for the encounter file using the provided UUID
- Joins with PatientEncounters and ZipFile tables to get complete information
- Builds the image path using the upload date and filename
- Sets appropriate mimetype based on file extension
- Adds cache control headers to prevent browser caching issues when images are updated
- Properly closes the database session after the query
- Flashes error messages if the image is not found

### `encounterDrReportByUUID(uuid: str)`

Serve a diabetic retinopathy report by UUID.

**Parameters:**
- `uuid` (str): The UUID of the DR report to serve

**Returns:**
- Flask response with the PDF file

**Implementation Details:**
- Queries the database for the DR report using the provided UUID
- Joins with PatientEncounters and ZipFile tables to get complete information
- Builds the PDF path using the upload date and report filename
- Sets mimetype as 'application/pdf'
- Properly closes the database session after the query
- Flashes error messages if the report is not found

### `encounterGlaucomaReportByUUID(uuid: str)`

Serve a glaucoma report by UUID.

**Parameters:**
- `uuid` (str): The UUID of the glaucoma report to serve

**Returns:**
- Flask response with the PDF file

**Implementation Details:**
- Queries the database for the glaucoma report using the provided UUID
- Joins with PatientEncounters and ZipFile tables to get complete information
- Builds the PDF path using the upload date and report filename
- Sets mimetype as 'application/pdf'
- Properly closes the database session after the query
- Flashes error messages if the report is not found

### `directImgOrigByUUID(uuid: str)`

Serve a direct image original file by UUID.

**Parameters:**
- `uuid` (str): The UUID of the direct image to serve

**Returns:**
- Flask response with the image file

**Implementation Details:**
- Queries the database for the direct image upload using the provided UUID
- Builds the image path using the folder relative path and original filename
- Sets appropriate mimetype based on file extension
- Adds cache control headers to prevent browser caching issues when images are updated
- Properly closes the database session after the query
- Flashes error messages if the image is not found

### `directImgEdByUUID(uuid: str)`

Serve a direct image edited file by UUID.

**Parameters:**
- `uuid` (str): The UUID of the direct image to serve

**Returns:**
- Flask response with the edited image file

**Implementation Details:**
- Queries the database for the direct image upload using the provided UUID
- Builds the image path using the folder relative path, 'edited' subfolder, and edited filename
- Sets appropriate mimetype based on file extension
- Adds cache control headers to prevent browser caching issues when images are updated
- Properly closes the database session after the query
- Flashes error messages if no edited image exists or if the file is not found

### `directImgFinalByUUID(uuid: str)`

Serve a direct image final version by UUID, preferring the edited version if available.

**Parameters:**
- `uuid` (str): The UUID of the direct image to serve

**Returns:**
- Flask response with the image file (edited version if available, otherwise original)

**Implementation Details:**
- Queries the database for the direct image upload using the provided UUID
- Prefers the edited version if available, otherwise uses the original
- Builds the appropriate image path based on which version is available
- Sets appropriate mimetype based on file extension
- Adds cache control headers to prevent browser caching issues when images are updated
- Properly closes the database session after the query
- Flashes error messages if the image is not found

### `imgForGradingByUUID(uuid: str)`

Serve an image for grading purposes by UUID.

First tries to find an encounter image (from ZIP uploads), then tries to find a direct upload image (preferring edited versions). Shows appropriate error messages using flash if issues occur. Only one match is returned - encounter images have priority.

**Parameters:**
- `uuid` (str): The UUID of the image to serve

**Returns:**
- Flask response with the appropriate image file

**Implementation Details:**
- Checks if both encounter and direct upload images exist with the same UUID
- If both exist, flashes an integrity error message and aborts
- If only encounter image exists, serves it using encounterImageByUUID
- If only direct image exists, serves it using directImgFinalByUUID
- If neither exists, flashes an error message and aborts
- Properly closes the database session after the query