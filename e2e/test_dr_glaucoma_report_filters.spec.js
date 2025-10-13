// @ts-check
import { test, expect } from '@playwright/test';

test.describe('DR and Glaucoma Report Filters Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the login page first
    await page.goto('http://localhost:5001/auth/login');
    
    // Fill in the login credentials
    await page.locator('[name="username"]').fill('admin');
    await page.locator('[name="password"]').fill('Vivek@2026');
    
    // Click the login button
    await page.locator('button[type="submit"]').first().click();
    
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
  });

  test('should test DR Report filter with ZIP images', async ({ page }) => {
    console.log('Testing DR Report filter with ZIP images...');
    
    // First, filter to show only ZIP images
    await page.locator('#filter-source').selectOption('zip');
    
    // Click the "Apply Filters" button to see all ZIP images
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Count ZIP images before applying DR filter
    const initialTableExists = await page.locator('table').isVisible().catch(() => false);
    let initialZipCount = 0;
    if (initialTableExists) {
      initialZipCount = await page.locator('tbody tr').count();
      console.log(`Initial ZIP images count: ${initialZipCount}`);
    }
    
    // Now apply the DR Report filter - set to "Yes"
    await page.locator('#filter-has-dr').selectOption('true');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check results after applying DR filter
    const drFilteredTableExists = await page.locator('table').isVisible().catch(() => false);
    let drFilteredCount = 0;
    if (drFilteredTableExists) {
      drFilteredCount = await page.locator('tbody tr').count();
      console.log(`ZIP images with DR reports count: ${drFilteredCount}`);
      
      // If we have results, verify they all have DR reports
      if (drFilteredCount > 0) {
        const drReportCells = page.locator('tbody tr td:nth-child(13)'); // DR Report column
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await drReportCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const drReportText = await drReportCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", DR Report="${drReportText?.trim()}"`);
          
          // Verify source is "zip" (since we filtered for ZIP images)
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify DR Report shows "Yes"
          expect(drReportText?.trim()).toContain('Yes');
        }
      }
    }
    
    // Now test the "No" option for DR Report filter
    await page.locator('#filter-has-dr').selectOption('false');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check results after applying DR filter = No
    const drNoFilteredTableExists = await page.locator('table').isVisible().catch(() => false);
    let drNoFilteredCount = 0;
    if (drNoFilteredTableExists) {
      drNoFilteredCount = await page.locator('tbody tr').count();
      console.log(`ZIP images without DR reports count: ${drNoFilteredCount}`);
      
      // If we have results, verify they all don't have DR reports
      if (drNoFilteredCount > 0) {
        const drReportCells = page.locator('tbody tr td:nth-child(13)'); // DR Report column
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await drReportCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const drReportText = await drReportCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", DR Report="${drReportText?.trim()}"`);
          
          // Verify source is "zip" (since we filtered for ZIP images)
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify DR Report shows "No"
          expect(drReportText?.trim()).toContain('No');
        }
      }
    }
    
    console.log('DR Report filter test completed');
  });

  test('should test Glaucoma Report filter with ZIP images', async ({ page }) => {
    console.log('Testing Glaucoma Report filter with ZIP images...');
    
    // First, filter to show only ZIP images
    await page.locator('#filter-source').selectOption('zip');
    
    // Click the "Apply Filters" button to see all ZIP images
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Count ZIP images before applying Glaucoma filter
    const initialTableExists = await page.locator('table').isVisible().catch(() => false);
    let initialZipCount = 0;
    if (initialTableExists) {
      initialZipCount = await page.locator('tbody tr').count();
      console.log(`Initial ZIP images count: ${initialZipCount}`);
    }
    
    // Now apply the Glaucoma Report filter - set to "Yes"
    await page.locator('#filter-has-gl').selectOption('true');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check results after applying Glaucoma filter
    const glaucomaFilteredTableExists = await page.locator('table').isVisible().catch(() => false);
    let glaucomaFilteredCount = 0;
    if (glaucomaFilteredTableExists) {
      glaucomaFilteredCount = await page.locator('tbody tr').count();
      console.log(`ZIP images with Glaucoma reports count: ${glaucomaFilteredCount}`);
      
      // If we have results, verify they all have Glaucoma reports
      if (glaucomaFilteredCount > 0) {
        const glaucomaReportCells = page.locator('tbody tr td:nth-child(14)'); // Glaucoma Report column
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await glaucomaReportCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const glaucomaReportText = await glaucomaReportCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", Glaucoma Report="${glaucomaReportText?.trim()}"`);
          
          // Verify source is "zip" (since we filtered for ZIP images)
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify Glaucoma Report shows "Yes"
          expect(glaucomaReportText?.trim()).toContain('Yes');
        }
      }
    }
    
    // Now test the "No" option for Glaucoma Report filter
    await page.locator('#filter-has-gl').selectOption('false');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check results after applying Glaucoma filter = No
    const glaucomaNoFilteredTableExists = await page.locator('table').isVisible().catch(() => false);
    let glaucomaNoFilteredCount = 0;
    if (glaucomaNoFilteredTableExists) {
      glaucomaNoFilteredCount = await page.locator('tbody tr').count();
      console.log(`ZIP images without Glaucoma reports count: ${glaucomaNoFilteredCount}`);
      
      // If we have results, verify they all don't have Glaucoma reports
      if (glaucomaNoFilteredCount > 0) {
        const glaucomaReportCells = page.locator('tbody tr td:nth-child(14)'); // Glaucoma Report column
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await glaucomaReportCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const glaucomaReportText = await glaucomaReportCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", Glaucoma Report="${glaucomaReportText?.trim()}"`);
          
          // Verify source is "zip" (since we filtered for ZIP images)
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify Glaucoma Report shows "No"
          expect(glaucomaReportText?.trim()).toContain('No');
        }
      }
    }
    
    console.log('Glaucoma Report filter test completed');
  });

  test('should test combined DR and Glaucoma Report filters', async ({ page }) => {
    console.log('Testing combined DR and Glaucoma Report filters...');
    
    // First, filter to show only ZIP images
    await page.locator('#filter-source').selectOption('zip');
    
    // Apply both DR and Glaucoma Report filters - set to "Yes"
    await page.locator('#filter-has-dr').selectOption('true');
    await page.locator('#filter-has-gl').selectOption('true');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check results after applying both filters
    const combinedFilteredTableExists = await page.locator('table').isVisible().catch(() => false);
    let combinedFilteredCount = 0;
    if (combinedFilteredTableExists) {
      combinedFilteredCount = await page.locator('tbody tr').count();
      console.log(`ZIP images with both DR and Glaucoma reports count: ${combinedFilteredCount}`);
      
      // If we have results, verify they all have both reports
      if (combinedFilteredCount > 0) {
        const drReportCells = page.locator('tbody tr td:nth-child(13)'); // DR Report column
        const glaucomaReportCells = page.locator('tbody tr td:nth-child(14)'); // Glaucoma Report column
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await drReportCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const drReportText = await drReportCells.nth(i).textContent();
          const glaucomaReportText = await glaucomaReportCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", DR Report="${drReportText?.trim()}", Glaucoma Report="${glaucomaReportText?.trim()}"`);
          
          // Verify source is "zip"
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify both reports show "Yes"
          expect(drReportText?.trim()).toContain('Yes');
          expect(glaucomaReportText?.trim()).toContain('Yes');
        }
      }
    }
    
    console.log('Combined DR and Glaucoma Report filters test completed');
  });
});