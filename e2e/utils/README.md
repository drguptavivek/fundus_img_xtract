# E2E Test Utilities

This directory contains utility functions and configuration for E2E tests.

## Configuration

The `config.js` file provides centralized configuration for all E2E tests. It reads the base URL from environment variables, allowing tests to run against different environments without code changes.

### Environment Variables

- `BASE_URL`: The base URL of the application (default: `http://127.0.0.1:5001`) - used in test scripts only

### Usage

```javascript
import { getBaseUrl, getLoginUrl, getApiBaseUrl } from './utils/config.js';

// Get the base URL
const baseUrl = getBaseUrl();

// Get specific URLs
const loginUrl = getLoginUrl();
const apiUrl = getApiBaseUrl();
```

## Login Utilities

The `login.js` file provides utilities for handling authentication in E2E tests.

### Functions

- `login(page, credentials)`: Login with specified credentials
- `loginWithRole(page, role)`: Login with a specific role (admin, user, viewer)
- `isLoggedIn(page)`: Check if user is currently logged in
- `logout(page)`: Logout the current user

### Example Usage

```javascript
import { login } from './utils/login.js';

// Login with default credentials
await login(page);

// Login with custom credentials
await login(page, {
  username: 'testuser',
  password: 'testpass',
  loginUrl: getLoginUrl()
});
```

## Updating Tests

When updating E2E tests:

1. Import the necessary functions from `config.js`
2. Replace hardcoded URLs with calls to the config functions
3. Use the login utilities for authentication

### Example Migration

Before:
```javascript
await page.goto('http://localhost:5001/auth/login');
```

After:
```javascript
import { getLoginUrl } from './utils/config.js';
await page.goto(getLoginUrl());