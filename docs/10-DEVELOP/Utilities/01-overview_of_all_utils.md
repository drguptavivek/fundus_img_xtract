# Overview of All Utils

This document provides a comprehensive overview of all utility modules in the Fundus Image Manager application. The utils directory contains various helper modules that provide core functionality across the application.


## Core Categories

### 1. Dual Grading System Utils
These modules handle the dual grading workflow for medical image assessment:

- **dualGradingConsensusUtils.py**: Manages consensus creation and status checking
- **dualGradingEligibility.py**: Checks user eligibility for grading roles
- **dualGradingFetchDetailUtils.py**: Retrieves detailed grading information
- **dualGradingGetNextTasks.py**: Assigns next eligible tasks to graders
- **dualGradingKPIs.py**: Calculates key performance indicators
- **dualGradingRevisionUtils.py**: Manages grade revision eligibility
- **dualGradingStuckTaskCleanup.py**: Cleans up abandoned tasks

### 2. File and Image Management Utils
These modules handle file operations, image serving, and path management:

- **fileUtils.py**: Core file handling operations
- **imageSearchUtil.py**: Advanced image search with filters
- **paths.py**: Path resolution and security
- **utilsImgServe.py**: Image serving for different contexts

### 3. System Utilities
These provide general system functionality:

- **captcha.py**: CAPTCHA generation and validation with audio support using PiperTTS
- **emails.py**: Email sending and notification system
- **notifications.py**: In-app notification management
- **rate_limiter.py**: Rate limiting for security and abuse prevention
- **stack_trace_handler.py**: Error tracking and debugging
- **datetime_filters.py**: Timezone-aware datetime formatting
- **timezone_choices.py**: Timezone selection helpers

### 4. Data Management Utils
These handle data retrieval and management:

- **masterUtils.py**: Core entity retrieval (diseases, hospitals, etc.)
- **taskUtils.py**: Task management and querying
- **jobUtils.py**: Job status and processing utilities
- **upload_eligibility.py**: User upload permission checks

### 5. General Utilities
These contain miscellaneous helper functions:

- **utils.py**: Basic utility functions and session management
- **utils2.py**: Additional helper functions for file operations
