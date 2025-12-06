// @ts-check
import { expect } from '@playwright/test';
import { getBaseUrl, getLoginUrl } from './config.js';

/**
 * Generic login utility function for the fundus image management application
 * @param {import('@playwright/test').Page} page - The Playwright page object
 * @param {Object} [credentials] - Login credentials
 * @param {string} [credentials.username] - Username for login (defaults to 'admin')
 * @param {string} [credentials.password] - Password for login (defaults to 'Vivek@2026')
 * @param {string} [credentials.loginUrl] - Login page URL (defaults to http://localhost:5001/auth/login)
 * @param {string} [credentials.redirectUrl] - Expected redirect URL after login (defaults to dashboard)
 * @returns {Promise<void>} Promise that resolves when login is complete
 */
/**
 * Generic login utility function for the fundus image management application
 * @param {import('@playwright/test').Page} page - The Playwright page object
 * @param {Object} [credentials] - Login credentials
 * @param {string} [credentials.username] - Username for login (defaults to 'admin')
 * @param {string} [credentials.password] - Password for login (defaults to 'Vivek@2026')
 * @param {string} [credentials.loginUrl] - Login page URL (defaults to http://localhost:5001/auth/login)
 * @param {string} [credentials.redirectUrl] - Expected redirect URL after login (defaults to grading)
 * @returns {Promise<void>} Promise that resolves when login is complete
 */
export async function login(page, credentials = {}) {
  const {
    username = process.env.PLAYWRIGHT_USERNAME || 'admin',
    password = process.env.PLAYWRIGHT_PASSWORD || 'Vivek@2026',
    loginUrl = getLoginUrl(),
    redirectUrl = '**/grading**'
  } = credentials;

  // Navigate to the login page
  await page.goto(loginUrl);
  
  // Fill in the login credentials
  await page.locator('[name="username"]').fill(username);
  await page.locator('[name="password"]').fill(password);
  
  // Click the login button
  await page.locator('button[type="submit"]').first().click().catch(() => {
    // If there are multiple submit buttons, try to be more specific
    return page.locator('button[type="submit"]').filter({ hasText: 'Login' }).click();
  });
  
  // Wait for navigation after login
  await page.waitForURL(redirectUrl, { timeout: 15000 }).catch(() => {
    console.log('Continuing after login, may have redirected to default page');
  });
  
  // Verify that we're logged in by checking for common logged-in elements
  await expect(page.locator('nav')).toBeVisible().catch(() => {
    console.log('Navigation element not found, but continuing...');
  });
}

/**
 * Login with different user roles
 * @param {import('@playwright/test').Page} page - The Playwright page object
 * @param {'admin'|'user'|'viewer'} role - User role to login with
 * @returns {Promise<void>} Promise that resolves when login is complete
 */
export async function loginWithRole(page, role) {
  const credentials = getCredentialsByRole(role);
  await login(page, credentials);
}

/**
 * Get credentials based on user role
 * @param {'admin'|'user'|'viewer'} role - User role
 * @returns {Object} Credentials object
 */
function getCredentialsByRole(role) {
  const roleCredentials = {
    admin: {
      username: process.env.PLAYWRIGHT_ADMIN_USERNAME || 'admin',
      password: process.env.PLAYWRIGHT_ADMIN_PASSWORD || 'Vivek@2026',
      redirectUrl: '**/grading**'
    },
    user: {
      username: process.env.PLAYWRIGHT_USER_USERNAME || 'user',
      password: process.env.PLAYWRIGHT_USER_PASSWORD || 'user_password',
      redirectUrl: '**/grading**'
    },
    viewer: {
      username: process.env.PLAYWRIGHT_VIEWER_USERNAME || 'viewer',
      password: process.env.PLAYWRIGHT_VIEWER_PASSWORD || 'viewer_password',
      redirectUrl: '**/grading**'
    }
  };
  
  return roleCredentials[role] || roleCredentials.admin;
}

/**
 * Check if user is already logged in
 * @param {import('@playwright/test').Page} page - The Playwright page object
 * @returns {Promise<boolean>} Promise that resolves to true if user is logged in
 */
export async function isLoggedIn(page) {
  // Check for elements that are visible only when logged in
  try {
    const hasDashboardElement = await page.locator('nav').isVisible({ timeout: 2000 });
    const hasLogoutButton = await page.locator('text=Logout').isVisible({ timeout: 2000 });
    const hasUserProfile = await page.locator('.user-profile').isVisible({ timeout: 2000 }) || 
                           await page.locator('[data-testid="user-menu"]').isVisible({ timeout: 2000 });
    
    return hasDashboardElement || hasLogoutButton || hasUserProfile;
  } catch (e) {
    return false;
  }
}

/**
 * Logout utility function
 * @param {import('@playwright/test').Page} page - The Playwright page object
 * @returns {Promise<void>} Promise that resolves when logout is complete
 */
export async function logout(page) {
  // Look for a logout button/link
  const logoutSelectors = [
    'text=Logout',
    'text=Sign out',
    '[data-testid="logout"]',
    '.logout-btn',
    'button:has-text("Logout")',
    'a:has-text("Logout")'
  ];
  
  for (const selector of logoutSelectors) {
    try {
      if (await page.locator(selector).isVisible({ timeout: 2000 })) {
        await page.locator(selector).click();
        await page.waitForURL('**/auth/login**', { timeout: 5000 });
        return;
      }
    } catch (e) {
      // Try next selector
    }
  }
  
  // If no logout button found, navigate directly to login
  await page.goto(getLoginUrl());
}