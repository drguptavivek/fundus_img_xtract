// @ts-check
import { test, expect } from '@playwright/test';
import { login } from './utils/login.js';

test('should load search images page after login', async ({ page }) => {
  // Login first as the search images page requires authentication
  await login(page);
  
  // Navigate to the search images page
  await page.goto('http://localhost:5001/search/images');
  
  // Wait for the page to load
  await expect(page).toHaveTitle(/Search Images/);
  
  console.log('Page loaded successfully after login');
});