// @ts-check
import { test, expect } from '@playwright/test';
import { login, loginWithRole, isLoggedIn, logout } from './utils/login.js';
import { getLoginUrl, getSearchImagesUrl, getDashboardUrl } from './utils/config.js';

test.describe('Login Utility Tests', () => {
 test('should login with default credentials', async ({ page }) => {
    // Test the basic login function with default credentials
    await login(page);
    
    // Verify login was successful by checking for common logged-in elements
    await expect(page.locator('nav')).toBeVisible();
    // The application redirects to grading page after login, not dashboard
    await expect(page).toHaveURL(/.*grading.*/);
  });

  test('should login with custom credentials', async ({ page }) => {
    // Test login with custom credentials
    await login(page, {
      username: 'admin',
      password: 'Vivek@2026',
      loginUrl: getLoginUrl()
    });
    
    // Verify login was successful
    await expect(page.locator('nav')).toBeVisible();
    await expect(page).toHaveURL(/.*grading.*/);
  });

  test('should login with admin role', async ({ page }) => {
    // Test login with role-based credentials
    await loginWithRole(page, 'admin');
    
    // Verify login was successful
    await expect(page.locator('nav')).toBeVisible();
    await expect(page).toHaveURL(/.*grading.*/);
  });

  test('should check if user is logged in', async ({ page }) => {
    // First login
    await login(page);
    
    // Check if user is logged in
    const loggedIn = await isLoggedIn(page);
    expect(loggedIn).toBe(true);
  });

  test('should handle logout', async ({ page }) => {
    // Login first
    await login(page);
    
    // Verify logged in
    expect(await isLoggedIn(page)).toBe(true);
    
    // Logout
    await logout(page);
    
    // Verify logged out by checking if we're back on login page
    await expect(page).toHaveURL(/.*auth\/login.*/);
  });

  test('should maintain session across multiple actions', async ({ page }) => {
    // Login
    await login(page);
    
    // Navigate to search images page (requires authentication)
    await page.goto(getSearchImagesUrl());
    
    // Verify we can access the page (not redirected to login)
    await expect(page).toHaveURL(/.*search\/images.*/);
    await expect(page.locator('h1')).toContainText('Search Images');
    
    // Try another authenticated page
    await page.goto(getDashboardUrl());
    await expect(page).toHaveURL(/.*dashboard.*/);
  });
});