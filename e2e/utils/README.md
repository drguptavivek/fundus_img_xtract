# Playwright Utilities

This directory contains reusable utility functions for Playwright end-to-end tests.

## Login Utility

The `login.js` file provides a set of functions to handle authentication in tests.

### Functions

#### `login(page, credentials)`
Generic login function that handles the authentication process.

**Parameters:**
- `page`: Playwright page object
- `credentials` (optional): Object containing:
  - `username`: Username for login (defaults to 'admin')
  - `password`: Password for login (defaults to 'Vivek@2026')
  - `loginUrl`: Login page URL (defaults to 'http://localhost:5001/auth/login')
  - `redirectUrl`: Expected redirect URL after login (defaults to '**/grading**')

**Example:**
```javascript
import { login } from './utils/login.js';

await login(page); // Uses default credentials
await login(page, {
  username: 'custom_user',
  password: 'custom_password'
});
```

#### `loginWithRole(page, role)`
Login with predefined role-based credentials.

**Parameters:**
- `page`: Playwright page object
- `role`: User role ('admin', 'user', or 'viewer')

#### `isLoggedIn(page)`
Check if user is already logged in.

**Parameters:**
- `page`: Playwright page object
**Returns:** Promise resolving to boolean

#### `logout(page)`
Logout the current user.

**Parameters:**
- `page`: Playwright page object

## Usage

Import the functions in your test files:

```javascript
import { login, loginWithRole, isLoggedIn, logout } from './utils/login.js';