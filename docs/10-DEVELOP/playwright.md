# Playwright Testing Guide

## Overview

This project uses Playwright for end-to-end (E2E) testing of the Fundus Image Manager web application. Playwright enables reliable testing of web applications across multiple browsers (Chromium, Firefox, and WebKit) with features like auto-waits, network interception, and powerful debugging tools.

## Setup and Installation

### Prerequisites

- Node.js (v14 or higher)
- Python environment with the Flask application running
- Access to the application (typically on `http://localhost:5001`)

### Installation

1. **Install Node.js dependencies**:
   ```bash
   npm install
   ```

2. **Install Playwright browsers**:
   ```bash
   npx playwright install
   ```

3. **Verify installation**:
   ```bash
   npx playwright --version
   ```

## Configuration

### Playwright Configuration File

The Playwright configuration is defined in `playwright.config.js`:

```javascript
export default defineConfig({
  testDir: './e2e',                    // Test files directory
  fullyParallel: true,                  // Run tests in parallel
  forbidOnly: !!process.env.CI,         // Fail on test.only in CI
  retries: process.env.CI ? 2 : 0,      // Retry on CI
  workers: process.env.CI ? 1 : undefined, // Workers for parallel execution
  reporter: 'html',                     // HTML reporter
  use: {
    trace: 'on-first-retry',           // Collect trace on retry
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
```

### Environment Variables

Create a `.env` file for test credentials:

```bash
# Test user credentials
PLAYWRIGHT_USERNAME=admin
PLAYWRIGHT_PASSWORD=your_password

# Role-specific credentials (optional)
PLAYWRIGHT_ADMIN_USERNAME=admin
PLAYWRIGHT_ADMIN_PASSWORD=admin_password
PLAYWRIGHT_USER_USERNAME=test_user
PLAYWRIGHT_USER_PASSWORD=user_password
PLAYWRIGHT_VIEWER_USERNAME=viewer
PLAYWRIGHT_VIEWER_PASSWORD=viewer_password
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
npx playwright test

# Run tests in headed mode (shows browser)
npx playwright test --headed

# Run specific test file
npx playwright test e2e/test_search_functionality.spec.js

# Run tests matching a pattern
npx playwright test --grep "search"
```

### Debugging Tests

```bash
# Run with debugging (pauses on failure)
npx playwright test --debug

# Run with browser UI (shows each step)
npx playwright test --ui

# Run with trace viewer
npx playwright test --trace on
npx playwright show-trace trace.zip
```

### Running Tests on Different Browsers

```bash
# Run on Chrome only
npx playwright test --project chromium

# Run on Firefox only
npx playwright test --project firefox

# Run on Safari only
npx playwright test --project webkit
```

## Test Structure

### Test File Organization

```
e2e/
├── utils/
│   ├── login.js          # Login utilities
│   └── README.md         # Utility documentation
├── example_login_test.spec.js
├── test_search_functionality.spec.js
├── test_api_hospitals_labunits.spec.js
└── test_dr_glaucoma_report_filters.spec.js
```

### Test File Template

```javascript
import { test, expect } from '@playwright/test';
import { login } from './utils/login.js';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await login(page);
  });

  test('should perform basic functionality', async ({ page }) => {
    // Test implementation
    await page.goto('/dashboard');
    await expect(page.locator('h1')).toContainText('Dashboard');
  });

  test('should handle edge cases', async ({ page }) => {
    // Edge case testing
  });
});
```

## Login Utilities

The project includes comprehensive login utilities in `e2e/utils/login.js`:

### Basic Login

```javascript
import { login } from '../utils/login.js';

test('example test', async ({ page }) => {
  await login(page);
  // Continue with authenticated actions
});
```

### Custom Login Credentials

```javascript
await login(page, {
  username: 'custom_user',
  password: 'custom_password',
  loginUrl: 'http://localhost:5001/auth/login',
  redirectUrl: '**/dashboard'
});
```

### Role-Based Login

```javascript
import { loginWithRole } from '../utils/login.js';

// Login with specific role
await loginWithRole(page, 'admin');
await loginWithRole(page, 'user');
await loginWithRole(page, 'viewer');
```

### Login Status Checking

```javascript
import { isLoggedIn, logout } from '../utils/login.js';

// Check if already logged in
if (await isLoggedIn(page)) {
  await logout(page);
}
```

## Writing Tests

### Best Practices

1. **Use descriptive test names** that explain what is being tested
2. **Group related tests** using `test.describe()`
3. **Use data-testid attributes** for reliable element selection
4. **Wait for elements** using Playwright's auto-wait features
5. **Avoid hard-coded waits** - use `waitForSelector()` instead
6. **Clean up test data** in `afterEach` hooks
7. **Use page objects** for complex page interactions

### Selecting Elements

```javascript
// Prefer data-testid attributes
await page.locator('[data-testid="submit-button"]').click();

// Use text selectors when appropriate
await page.locator('text=Submit').click();

// Use CSS selectors for complex queries
await page.locator('.form-group > input[type="email"]').fill('test@example.com');

// Use XPath when necessary
await page.locator('//button[contains(text(), "Submit")]').click();
```

### Handling Forms

```javascript
test('should submit form', async ({ page }) => {
  await page.goto('/form');
  
  // Fill form fields
  await page.locator('[name="username"]').fill('testuser');
  await page.locator('[name="email"]').fill('test@example.com');
  await page.locator('[name="password"]').fill('password123');
  
  // Select dropdown
  await page.selectOption('[name="role"]', 'admin');
  
  // Check checkbox
  await page.check('[name="agree"]');
  
  // Submit form
  await page.locator('button[type="submit"]').click();
  
  // Verify result
  await expect(page.locator('.success-message')).toBeVisible();
});
```

### Handling Navigation

```javascript
test('should navigate between pages', async ({ page }) => {
  await page.goto('/');
  
  // Click navigation link
  await page.locator('a[href="/dashboard"]').click();
  
  // Wait for navigation
  await page.waitForURL('**/dashboard');
  
  // Verify URL and content
  expect(page.url()).toContain('/dashboard');
  await expect(page.locator('h1')).toContainText('Dashboard');
});
```

### Handling Tables and Lists

```javascript
test('should interact with table', async ({ page }) => {
  await page.goto('/users');
  
  // Wait for table to load
  await page.waitForSelector('[data-testid="users-table"]');
  
  // Get all rows
  const rows = await page.locator('[data-testid="users-table"] tbody tr').count();
  expect(rows).toBeGreaterThan(0);
  
  // Click specific row
  await page.locator('[data-testid="users-table"] tbody tr').first().click();
  
  // Verify navigation to detail page
  await expect(page.locator('h1')).toContainText('User Details');
});
```

### Handling Modals and Dialogs

```javascript
test('should handle modal dialog', async ({ page }) => {
  await page.goto('/dashboard');
  
  // Open modal
  await page.locator('[data-testid="open-modal"]').click();
  
  // Wait for modal to appear
  await expect(page.locator('[data-testid="modal"]')).toBeVisible();
  
  // Interact with modal content
  await page.locator('[data-testid="modal-input"]').fill('test data');
  await page.locator('[data-testid="modal-submit"]').click();
  
  // Wait for modal to close
  await expect(page.locator('[data-testid="modal"]')).not.toBeVisible();
});
```

### Network Requests

```javascript
test('should handle API calls', async ({ page }) => {
  // Listen for network requests
  await page.route('**/api/users', route => {
    // Mock API response
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 1, name: 'Test User' }])
    });
  });
  
  await page.goto('/users');
  
  // Verify API was called
  const response = await page.waitForResponse('**/api/users');
  expect(response.status()).toBe(200);
});
```

## Debugging

### Using Playwright Inspector

```bash
# Run test with debugger
npx playwright test --debug

# Or add debugger in test
test('debug example', async ({ page }) => {
  await page.goto('/');
  await page.pause(); // Pauses execution and opens inspector
  // Continue with test steps
});
```

### Generating Test Code

```bash
# Record user actions to generate test code
npx playwright codegen http://localhost:5001
```

### Taking Screenshots

```javascript
test('should take screenshot on failure', async ({ page }) => {
  await page.goto('/');
  
  try {
    // Test steps that might fail
    await expect(page.locator('.non-existent')).toBeVisible();
  } catch (error) {
    // Take screenshot on failure
    await page.screenshot({ path: 'failure-screenshot.png', fullPage: true });
    throw error;
  }
});
```

### Console Logging

```javascript
test('should log browser console', async ({ page }) => {
  // Listen for console messages
  page.on('console', msg => {
    console.log('Browser console:', msg.text());
  });
  
  // Listen for page errors
  page.on('pageerror', error => {
    console.error('Page error:', error.message);
  });
  
  await page.goto('/');
});
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Playwright Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - run: npm install
      - run: npx playwright install
      - run: npx playwright test
      - uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
```

### Running Tests in CI

```bash
# Run tests in CI mode
npx playwright test --reporter=html --reporter=junit

# Run with specific browser in CI
npx playwright test --project chromium --reporter=list
```

## Common Test Scenarios

### Authentication Flow

```javascript
test.describe('Authentication', () => {
  test('should login successfully', async ({ page }) => {
    await page.goto('/auth/login');
    
    await page.locator('[name="username"]').fill('admin');
    await page.locator('[name="password"]').fill('password');
    await page.locator('button[type="submit"]').click();
    
    await expect(page.locator('.user-menu')).toBeVisible();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.goto('/auth/login');
    
    await page.locator('[name="username"]').fill('invalid');
    await page.locator('[name="password"]').fill('invalid');
    await page.locator('button[type="submit"]').click();
    
    await expect(page.locator('.error-message')).toContainText('Invalid credentials');
  });
});
```

### Search and Filtering

```javascript
test.describe('Search Functionality', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto('/search');
  });

  test('should search by patient name', async ({ page }) => {
    await page.locator('[data-testid="search-input"]').fill('John Doe');
    await page.locator('[data-testid="search-button"]').click();
    
    await expect(page.locator('[data-testid="search-results"]')).toBeVisible();
    await expect(page.locator('[data-testid="search-results"] tbody tr')).toHaveCount(1);
  });

  test('should filter by date range', async ({ page }) => {
    await page.locator('[data-testid="date-from"]').fill('2024-01-01');
    await page.locator('[data-testid="date-to"]').fill('2024-12-31');
    await page.locator('[data-testid="filter-button"]').click();
    
    await expect(page.locator('[data-testid="search-results"]')).toBeVisible();
  });
});
```

### File Upload

```javascript
test.describe('File Upload', () => {
  test('should upload image file', async ({ page }) => {
    await login(page);
    await page.goto('/upload');
    
    // Select file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('test-assets/sample-image.jpg');
    
    // Fill metadata
    await page.locator('[name="patient-name"]').fill('Test Patient');
    await page.locator('[name="description"]').fill('Test upload');
    
    // Submit form
    await page.locator('[data-testid="upload-button"]').click();
    
    // Verify upload success
    await expect(page.locator('.success-message')).toBeVisible();
  });
});
```

## Troubleshooting

### Common Issues

1. **Tests fail to find elements**
   - Ensure the application is running on the expected port
   - Check if elements are inside iframes
   - Use `waitForSelector()` for dynamic content

2. **Tests timeout**
   - Increase timeout values in `playwright.config.js`
   - Check for network requests that might be hanging
   - Use `waitForLoadState()` for complex pages

3. **Flaky tests**
   - Add explicit waits for dynamic content
   - Use retry mechanisms for network-dependent tests
   - Ensure tests clean up after themselves

4. **Authentication issues**
   - Verify test credentials are correct
   - Check if login redirects are working
   - Ensure CSRF tokens are handled properly

### Debug Commands

```bash
# Run specific test with debugging
npx playwright test --debug --project chromium e2e/test_file.spec.js

# Run tests with verbose output
npx playwright test --reporter=list

# Generate HTML report
npx playwright test --reporter=html
npx playwright show-report
```

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Test Configuration](https://playwright.dev/docs/test-configuration)
- [Playwright Test Best Practices](https://playwright.dev/docs/best-practices)
- [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer)
- [Playwright VS Code Extension](https://playwright.dev/docs/getting-started-vscode)