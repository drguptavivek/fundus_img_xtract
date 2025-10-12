// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Search Images - Hospital Name for ZIP Images', () => {
 test('should show hospital name for ZIP image type', async ({ page }) => {
    // Navigate to the login page first
    await page.goto('http://localhost:5001/auth/login');
    
    // Fill in the login credentials
    await page.locator('[name="username"]').fill('admin');
    await page.locator('[name="password"]').fill('Vivek@2026');
    
    // Click the login button
    await page.locator('button[type="submit"]').click();
    
    // Wait for navigation to the dashboard or main page after login
    await page.waitForURL('**/dashboard**', { timeout: 3000 }).catch(() => {
      // If dashboard URL doesn't match, wait for any page change
      console.log('Continuing after login...');
    });
    
    // Navigate to the search images page
    await page.goto('http://localhost:5001/search/images');
    
    // Select "ZIP Images" from the source filter
    await page.locator('#filter-source').selectOption('zip');
    
    // Click the "Apply Filters" button specifically
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    
    // Wait for the page to load after filtering
    await page.waitForLoadState('networkidle');
    
    // Wait for the table to be visible
    await page.waitForSelector('table', { state: 'visible' });
    
    // Verify that the page has loaded results
    const tableRows = await page.locator('tbody tr').count();
    // Note: We may have 0 rows if there are no ZIP images, so just check that the page loaded without error
    // Check if the table is present and at least the header exists
    await expect(page.locator('table')).toBeVisible();
    
    // If there are rows, then check for hospital names
    if (tableRows > 0) {
      // Check that hospital names are visible in the table
      const hospitalCells = page.locator('tbody tr td:nth-child(3)'); // Hospital column is 3rd
      const hospitalCellCount = await hospitalCells.count();
      
      for (let i = 0; i < hospitalCellCount; i++) {
        const hospitalText = await hospitalCells.nth(i).textContent();
        // Hospital name should not be empty or just '—'
        if (hospitalText !== null) {
          expect(hospitalText.trim()).not.toBe('—');
          expect(hospitalText.trim()).not.toBe('');
          console.log(`Hospital name for row ${i}: "${hospitalText.trim()}"`);
        } else {
          console.log(`Hospital name for row ${i}: null`);
          expect(hospitalText).not.toBe(null);
        }
      }
      
      // Verify that the source column shows 'zip'
      const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column is 2nd
      for (let i = 0; i < Math.min(5, await sourceCells.count()); i++) { // Check first 5 rows
        const sourceText = await sourceCells.nth(i).textContent();
        if (sourceText !== null) {
          expect(sourceText.trim().toLowerCase()).toBe('zip');
        } else {
          expect(sourceText).not.toBe(null);
        }
      }
    } else {
      console.log('No rows found in the table, which is acceptable if there are no ZIP images in the database');
    }
    
    // Check that hospital names are visible in the table
    const hospitalCells = page.locator('tbody tr td:nth-child(3)'); // Hospital column is 3rd
    const hospitalCellCount = await hospitalCells.count();
    
    for (let i = 0; i < hospitalCellCount; i++) {
      const hospitalText = await hospitalCells.nth(i).textContent();
      // Hospital name should not be empty or just '—'
      if (hospitalText !== null) {
        expect(hospitalText.trim()).not.toBe('—');
        expect(hospitalText.trim()).not.toBe('');
        console.log(`Hospital name for row ${i}: "${hospitalText.trim()}"`);
      } else {
        console.log(`Hospital name for row ${i}: null`);
        expect(hospitalText).not.toBe(null);
      }
    }
    
    // Verify that the source column shows 'zip'
    const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column is 2nd
    for (let i = 0; i < Math.min(5, await sourceCells.count()); i++) { // Check first 5 rows
      const sourceText = await sourceCells.nth(i).textContent();
      if (sourceText !== null) {
        expect(sourceText.trim().toLowerCase()).toBe('zip');
      } else {
        expect(sourceText).not.toBe(null);
      }
    }
  });
});