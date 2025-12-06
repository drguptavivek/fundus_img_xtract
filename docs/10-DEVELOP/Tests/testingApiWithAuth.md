# Testing API with Authentication Helpers

## Overview

The authentication helper module provides functions to authenticate test users and retrieve session cookies for making authenticated requests to the application endpoints.

## Files

- [`tests/test_auth_helpers.py`](../../../tests/test_auth_helpers.py) - Main authentication helper module
- [`tests/example_auth_usage.py`](../../../tests/example_auth_usage.py) - Basic usage example
- [`tests/test_api_with_auth.py`](../../../tests/test_api_with_auth.py) - API testing example

## Key Functions

### `login_as_test_admin()`
Logs in as test_admin user and returns session cookies.

### `login_as_test_manager()`
Logs in as test_manager user and returns session cookies.

### `make_authenticated_request(url, cookies, method='GET', data=None, json_data=None)`
Makes authenticated requests using provided cookies.

## Usage Example

```python
from tests.test_auth_helpers import login_as_test_admin, make_authenticated_request

# Login and get cookies
admin_cookies = login_as_test_admin()

# Make authenticated request
response = make_authenticated_request("http://127.0.0.1:5001/dashboard", admin_cookies)
```

## Running Tests

```bash
# Run basic example
uv run tests/example_auth_usage.py

# Run API testing example
uv run tests/test_api_with_auth.py
```

## Environment

The helpers read credentials from `.env.testing` and base URL from `.env`.