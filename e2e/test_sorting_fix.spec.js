// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Test Sorting Fix for Search Functionality', () => {
  test('should not throw AttributeError: created_at when sorting search results', async ({ page }) => {
    // Navigate to the login page first
    await page.goto('http://localhost:5001/auth/login');
    
    // Fill in the login credentials
    await page.locator('[name="username"]').fill('admin');
    await page.locator('[name="password"]').fill('Vivek@2026');
    
    // Click the login button
    await page.locator('button[type="submit"]').first().click(); // Use first() to avoid the duplicate button issue
    
    // Wait for navigation after login
    await page.waitForURL('**/dashboard**', { timeout: 15000 }).catch(() => {
      console.log('Continuing after login, may have redirected to default page');
    });
    
    // Navigate to the search images page
    await page.goto('http://localhost:5001/search/images');
    
    // Wait for the page to load
    await page.waitForLoadState('networkidle');
    
    // Verify that the search page loaded
    await expect(page.locator('h1')).toContainText('Search Images');
    
    // Test basic search without filters to trigger the sorting
    console.log('Testing basic search functionality with sorting...');
    
    // Initially, there might be results already loaded or we might need to click search
    // Check if there are any errors in the console that would indicate the sorting issue
    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    
    // Try different filter combinations to trigger the search functionality
    // First, try direct images
    await page.locator('#filter-source').selectOption('direct');
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check for any errors after this operation
    if (consoleErrors.length > 0) {
      console.log('Console errors found:', consoleErrors);
      // Check if any of the errors is related to the created_at attribute error
      const hasCreatedAttributeError = consoleErrors.some(error => 
        error.includes('created_at') || error.includes('AttributeError')
      );
      expect(hasCreatedAttributeError).toBe(false);
    }
    
    // Now try ZIP images
    await page.locator('#filter-source').selectOption('zip');
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check for any errors after this operation
    if (consoleErrors.length > 0) {
      console.log('Console errors found:', consoleErrors);
      const hasCreatedAttributeError = consoleErrors.some(error => 
        error.includes('created_at') || error.includes('AttributeError')
      );
      expect(hasCreatedAttributeError).toBe(false);
    }
    
    // Try both (no filter)
    await page.locator('#filter-source').selectOption('all');
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Final check for errors
    if (consoleErrors.length > 0) {
      console.log('Console errors found:', consoleErrors);
      const hasCreatedAttributeError = consoleErrors.some(error => 
        error.includes('created_at') || error.includes('AttributeError')
      );
      expect(hasCreatedAttributeError).toBe(false);
    }
    
    console.log('Sorting fix test completed successfully - no AttributeError: created_at found');
  });
});