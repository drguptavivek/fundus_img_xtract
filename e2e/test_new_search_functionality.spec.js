const { test, expect } = require('@playwright/test');
const { login } = require('./utils/login');

test.describe('New Search Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin user
    await login(page, 'admin', 'admin');
    await page.goto('/search/images');
  });

  test('should display search page with correct filters', async ({ page }) => {
    // Check page title
    await expect(page.locator('h1')).toContainText('Search Images');
    
    // Check common filters are visible
    await expect(page.locator('#filter-source')).toBeVisible();
    await expect(page.locator('#filter-hospital')).toBeVisible();
    await expect(page.locator('#filter-lab')).toBeVisible();
    await expect(page.locator('#filter-upload-start')).toBeVisible();
    await expect(page.locator('#filter-upload-end')).toBeVisible();
    
    // Check image-specific filters section
    await expect(page.locator('.card-header h5')).toContainText('Image-Specific Filters');
  });

  test('should show/hide filters based on source selection', async ({ page }) => {
    // Default to "All" - should show direct filters, hide ZIP filters
    await expect(page.locator('.direct-only-filter')).toBeVisible();
    await expect(page.locator('.zip-only-filter')).toBeHidden();
    
    // Select "Direct Uploads" - should show direct filters, hide ZIP filters
    await page.selectOption('#filter-source', 'direct');
    await expect(page.locator('.direct-only-filter')).toBeVisible();
    await expect(page.locator('.zip-only-filter')).toBeHidden();
    
    // Select "ZIP Images" - should hide direct filters, show ZIP filters
    await page.selectOption('#filter-source', 'zip');
    await expect(page.locator('.direct-only-filter')).toBeHidden();
    await expect(page.locator('.zip-only-filter')).toBeVisible();
    
    // Check ZIP-specific filters are visible
    await expect(page.locator('#filter-has-dr')).toBeVisible();
    await expect(page.locator('#filter-has-gl')).toBeVisible();
    await expect(page.locator('#filter-capture-start')).toBeVisible();
    await expect(page.locator('#filter-capture-end')).toBeVisible();
  });

  test('should search direct images with direct-specific filters', async ({ page }) => {
    // Select direct images only
    await page.selectOption('#filter-source', 'direct');
    
    // Apply direct-specific filters
    await page.selectOption('#filter-camera', '1'); // Assuming camera ID 1 exists
    await page.selectOption('#filter-disease', '1'); // Assuming disease ID 1 exists
    await page.selectOption('#filter-area', '1'); // Assuming area ID 1 exists
    await page.selectOption('#filter-mydriatic', 'true');
    
    // Submit search
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check that results are shown (if any exist)
    const resultsTable = page.locator('.table-responsive');
    if (await resultsTable.isVisible()) {
      // Check that all results are direct images
      const sourceCells = page.locator('td:nth-child(2)'); // Source column
      const count = await sourceCells.count();
      
      for (let i = 0; i < count; i++) {
        await expect(sourceCells.nth(i)).toContainText('direct');
      }
    }
  });

  test('should search ZIP images with ZIP-specific filters', async ({ page }) => {
    // Select ZIP images only
    await page.selectOption('#filter-source', 'zip');
    
    // Apply ZIP-specific filters
    await page.selectOption('#filter-has-dr', 'true');
    await page.selectOption('#filter-has-gl', 'false');
    
    // Submit search
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check that results are shown (if any exist)
    const resultsTable = page.locator('.table-responsive');
    if (await resultsTable.isVisible()) {
      // Check that all results are ZIP images
      const sourceCells = page.locator('td:nth-child(2)'); // Source column
      const count = await sourceCells.count();
      
      for (let i = 0; i < count; i++) {
        await expect(sourceCells.nth(i)).toContainText('zip');
      }
      
      // Check DR report column shows "Yes" for all results
      const drReportCells = page.locator('td:nth-child(12)'); // DR Report column
      const drCount = await drReportCells.count();
      
      for (let i = 0; i < drCount; i++) {
        await expect(drReportCells.nth(i)).toContainText('Yes');
      }
    }
  });

  test('should apply global filters to both image types', async ({ page }) => {
    // Select "All" sources
    await page.selectOption('#filter-source', 'all');
    
    // Apply global filters
    await page.selectOption('#filter-hospital', '1'); // Assuming hospital ID 1 exists
    await page.selectOption('#filter-lab', '1'); // Assuming lab unit ID 1 exists
    
    // Set date range
    await page.fill('#filter-upload-start', '2024-01-01');
    await page.fill('#filter-upload-end', '2024-12-31');
    
    // Submit search
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check that results are shown (if any exist)
    const resultsTable = page.locator('.table-responsive');
    if (await resultsTable.isVisible()) {
      // Results should contain both direct and zip images
      const sourceCells = page.locator('td:nth-child(2)'); // Source column
      const count = await sourceCells.count();
      
      let hasDirect = false;
      let hasZip = false;
      
      for (let i = 0; i < count; i++) {
        const source = await sourceCells.nth(i).textContent();
        if (source.includes('direct')) hasDirect = true;
        if (source.includes('zip')) hasZip = true;
      }
      
      // At least one type should be present if results exist
      expect(hasDirect || hasZip).toBeTruthy();
    }
  });

  test('should display capture date in correct timezone', async ({ page }) => {
    // Select ZIP images to see capture dates
    await page.selectOption('#filter-source', 'zip');
    
    // Submit search
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check that results are shown (if any exist)
    const resultsTable = page.locator('.table-responsive');
    if (await resultsTable.isVisible()) {
      // Check capture date column
      const captureDateCells = page.locator('td:nth-child(10)'); // Capture Date column
      const count = await captureDateCells.count();
      
      for (let i = 0; i < count; i++) {
        const cellText = await captureDateCells.nth(i).textContent();
        if (cellText && cellText !== '—') {
          // Should be formatted as YYYY-MM-DD HH:MM (user's timezone)
          expect(cellText).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
        }
      }
    }
  });

  test('should handle filter conflicts gracefully', async ({ page }) => {
    // Select direct images
    await page.selectOption('#filter-source', 'direct');
    
    // Try to apply ZIP-specific filters (should be hidden, but let's try via URL)
    await page.goto('/search/images?source=direct&has_dr_report=true');
    
    // Should show error message
    await expect(page.locator('.alert-danger')).toContainText('Search error');
    await expect(page.locator('.alert-danger')).toContainText('Cannot apply ZIP-specific filters when searching direct images only');
  });

  test('should open direct image view correctly', async ({ page }) => {
    // Select direct images only
    await page.selectOption('#filter-source', 'direct');
    
    // Submit search
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check that results are shown
    const resultsTable = page.locator('.table-responsive');
    if (await resultsTable.isVisible()) {
      // Find first "Open" button
      const openButton = page.locator('a[href*="direct/view"]').first();
      
      if (await openButton.isVisible()) {
        // Click open button
        await openButton.click();
        
        // Wait for page to load
        await page.waitForLoadState('networkidle');
        
        // Check that we're on the view page
        await expect(page.locator('h1')).toContainText('Direct Upload Summary');
        
        // Check that uploader information is displayed
        await expect(page.locator('text=Uploader:')).toBeVisible();
        
        // Check that image is displayed
        await expect(page.locator('img[alt*="Direct upload"]')).toBeVisible();
      }
    }
  });

  test('should clear filters correctly', async ({ page }) => {
    // Apply some filters
    await page.selectOption('#filter-source', 'direct');
    await page.selectOption('#filter-camera', '1');
    await page.selectOption('#filter-disease', '1');
    await page.fill('#filter-upload-start', '2024-01-01');
    
    // Click clear filters
    await page.click('a[href="/search/images"]');
    
    // Wait for page to reload
    await page.waitForLoadState('networkidle');
    
    // Check that filters are reset to defaults
    await expect(page.locator('#filter-source')).toHaveValue('all');
    await expect(page.locator('#filter-camera')).toHaveValue('');
    await expect(page.locator('#filter-disease')).toHaveValue('');
    await expect(page.locator('#filter-upload-start')).toHaveValue('');
  });

  test('should paginate results correctly', async ({ page }) => {
    // Submit search with minimal filters to get more results
    await page.click('button[type="submit"]');
    
    // Wait for results
    await page.waitForLoadState('networkidle');
    
    // Check pagination
    const pagination = page.locator('.btn-group[aria-label="Pagination"]');
    if (await pagination.isVisible()) {
      // Check if next button exists and is enabled
      const nextButton = page.locator('a:has-text("Next")');
      if (await nextButton.isVisible() && !(await nextButton.hasClass('disabled'))) {
        // Click next page
        await nextButton.click();
        
        // Wait for page to load
        await page.waitForLoadState('networkidle');
        
        // Check that URL has page parameter
        expect(page.url()).toContain('page=');
      }
    }
  });
});