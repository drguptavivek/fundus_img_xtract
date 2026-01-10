# Test Suite Documentation

## Overview

This test suite is organized into clear categories to make it easy to find, run, and maintain tests. The structure follows industry best practices for test organization and enables efficient testing strategies.

## Directory Structure

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── auth/               # Authentication & authorization unit tests
│   ├── utils/              # Utility function tests
│   ├── models/             # Database model tests
│   └── services/           # Service layer tests
│
├── integration/             # Integration tests (multi-component)
│   ├── auth/               # Auth workflow integration tests
│   ├── api/                # API endpoint tests
│   ├── uploads/            # Upload workflow tests
│   ├── analytics/          # Analytics integration tests
│   ├── grading/            # Grading workflow tests
│   ├── thumbnails/         # Thumbnail processing tests
│   └── rate_limiting/      # Rate limiter integration tests
│
├── e2e/                     # End-to-end tests (full workflows)
│   ├── pytest/             # Python E2E tests
│   ├── playwright/         # Playwright browser tests
│   └── fixtures/           # Test data and sample files
│
├── regression/              # Regression tests (bug prevention)
│   └── bugs/               # Bug-specific regression tests
│
├── performance/             # Performance & load tests
├── security/                # Security-focused tests
│
└── helpers/                 # Shared test utilities
    ├── auth_helpers.py     # Authentication helpers
    ├── factories.py        # Test data factories
    ├── assertions.py       # Custom assertions
    └── mocks.py            # Common mocks
```

## Test Categories

### Unit Tests (`tests/unit/`)
- **Purpose**: Test individual functions/methods in isolation
- **Speed**: Fast (< 100ms per test)
- **Dependencies**: Heavily mocked, no external dependencies
- **Database**: Mocked
- **When to use**: Testing business logic, utility functions, model methods

### Integration Tests (`tests/integration/`)
- **Purpose**: Test interaction between multiple components
- **Speed**: Medium (100ms - 1s per test)
- **Dependencies**: Test database, minimal external services
- **Database**: Real test database with transactions
- **When to use**: Testing routes, API endpoints, workflows

### E2E Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows end-to-end
- **Speed**: Slow (> 1s per test)
- **Dependencies**: Full application stack
- **Database**: Real test database
- **When to use**: Testing critical user journeys, browser interactions

### Regression Tests (`tests/regression/`)
- **Purpose**: Prevent bugs from reoccurring
- **Speed**: Varies
- **Naming**: `test_bug_YYYY_MM_issue_NNN.py`
- **When to use**: After fixing a bug, create a regression test

### Performance Tests (`tests/performance/`)
- **Purpose**: Benchmark and load testing
- **Speed**: Slow
- **When to use**: Testing scalability, response times, resource usage

### Security Tests (`tests/security/`)
- **Purpose**: Security-focused testing
- **Speed**: Medium
- **When to use**: Testing CSRF, XSS, authentication, authorization

## Running Tests

See tests/README.md for complete documentation on running and writing tests.
