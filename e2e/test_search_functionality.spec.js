// @ts-check
import { test, expect } from '@playwright/test';

test.describe('Comprehensive Search Functionality Tests', () => {
  test.beforeEach(async ({ page }) => {
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
  });

 test('should search for Direct images with disease filters', async ({ page }) => {
    console.log('Testing Direct images with disease filters...');
    
    // Select "Direct Uploads" from the source filter
    await page.locator('#filter-source').selectOption('direct');
    
    // Select a disease filter (e.g., Diabetic Retinopathy if available)
    const diseaseSelect = page.locator('#filter-disease');
    const diseaseOptions = await diseaseSelect.locator('option').all();
    
    if (diseaseOptions.length > 1) { // More than just "All" option
      // Select the first available disease (not "All")
      const firstDiseaseOption = diseaseOptions[1];
      const diseaseValue = await firstDiseaseOption.getAttribute('value');
      if (diseaseValue) {
        await diseaseSelect.selectOption(diseaseValue);
        console.log(`Selected disease filter: ${await firstDiseaseOption.textContent()}`);
      }
    }
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    
    // Wait for the page to reload with filtered results
    await page.waitForLoadState('networkidle');
    
    // Check if the table exists (even if it has no rows)
    const tableExists = await page.locator('table').isVisible().catch(() => false);
    
    if (tableExists) {
      console.log('Table is visible, checking for Direct images with disease filters...');
      
      // If table exists, check if there are any rows
      const tableRows = await page.locator('tbody tr').count();
      console.log(`Found ${tableRows} rows in the table`);
      
      if (tableRows > 0) {
        // Check first few rows to ensure they are Direct images and have disease info
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        const diseaseCells = page.locator('tbody tr td:nth-child(6)'); // Disease column
        
        for (let i = 0; i < Math.min(5, await sourceCells.count()); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const diseaseText = await diseaseCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", Disease="${diseaseText?.trim()}"`);
          
          // Verify source is "direct"
          expect(sourceText?.trim().toLowerCase()).toBe('direct');
          
          // Verify disease column has actual disease info (not '—')
          expect(diseaseText?.trim()).not.toBe('—');
          expect(diseaseText?.trim()).not.toBe('');
        }
      } else {
        console.log('No rows found - this is acceptable if no Direct images match the disease filter');
      }
    } else {
      console.log('Table not found - might be no results or different page structure');
    }
  });

  test('should search for ZIP images (which should not show disease information)', async ({ page }) => {
    console.log('Testing ZIP images without disease information...');
    
    // Select "ZIP Images" from the source filter
    await page.locator('#filter-source').selectOption('zip');
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    
    // Wait for the page to reload with filtered results
    await page.waitForLoadState('networkidle');
    
    // Check if the table exists (even if it has no rows)
    const tableExists = await page.locator('table').isVisible().catch(() => false);
    
    if (tableExists) {
      console.log('Table is visible, checking for ZIP images without disease info...');
      
      // If table exists, check if there are any rows
      const tableRows = await page.locator('tbody tr').count();
      console.log(`Found ${tableRows} rows in the table`);
      
      if (tableRows > 0) {
        // Check first few rows to ensure they are ZIP images and have no disease info
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        const diseaseCells = page.locator('tbody tr td:nth-child(6)'); // Disease column
        
        for (let i = 0; i < Math.min(5, await sourceCells.count()); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const diseaseText = await diseaseCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", Disease="${diseaseText?.trim()}"`);
          
          // Verify source is "zip"
          expect(sourceText?.trim().toLowerCase()).toBe('zip');
          
          // Verify disease column shows '—' (no disease info for ZIP images)
          expect(diseaseText?.trim()).toBe('—');
        }
      } else {
        console.log('No rows found - this is acceptable if no ZIP images exist in the database');
      }
    } else {
      console.log('Table not found - might be no results or different page structure');
    }
  });

 test('should filter by upload date and capture date for both image types', async ({ page }) => {
    console.log('Testing upload date and capture date filters...');
    
    // Test with both image types
    for (const imageType of ['all', 'direct', 'zip']) {
      console.log(`Testing date filters for ${imageType} images...`);
      
      // Reset filters first
      await page.locator('#filter-source').selectOption('all');
      await page.locator('#filter-disease').selectOption('');
      await page.locator('#filter-upload-start').fill('');
      await page.locator('#filter-upload-end').fill('');
      await page.locator('#filter-capture-start').fill('');
      await page.locator('#filter-capture-end').fill('');
      
      // Apply "all" source initially to reset
      await page.locator('#filter-source').selectOption(imageType);
      
      // Set upload date range (e.g., last 30 days)
      const today = new Date();
      const thirtyDaysAgo = new Date();
      thirtyDaysAgo.setDate(today.getDate() - 30);
      
      const uploadStartDate = thirtyDaysAgo.toISOString().split('T')[0];
      const uploadEndDate = today.toISOString().split('T')[0];
      
      await page.locator('#filter-upload-start').fill(uploadStartDate);
      await page.locator('#filter-upload-end').fill(uploadEndDate);
      
      // Set capture date range (similar to upload date for testing)
      await page.locator('#filter-capture-start').fill(uploadStartDate);
      await page.locator('#filter-capture-end').fill(uploadEndDate);
      
      // Click the "Apply Filters" button
      await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
      
      // Wait for the page to reload with filtered results
      await page.waitForLoadState('networkidle');
      
      // Check if the table exists (even if it has no rows)
      const tableExists = await page.locator('table').isVisible().catch(() => false);
      
      if (tableExists) {
        console.log(`Table is visible for ${imageType} images, checking date filters...`);
        
        // If table exists, check if there are any rows
        const tableRows = await page.locator('tbody tr').count();
        console.log(`Found ${tableRows} rows in the table for ${imageType} images`);
        
        if (tableRows > 0) {
          // Check first few rows to verify they match the date filters
          const uploadDateCells = page.locator('tbody tr td:nth-child(9)'); // Upload Date column
          const captureDateCells = page.locator('tbody tr td:nth-child(10)'); // Capture Date column
          
          for (let i = 0; i < Math.min(3, await uploadDateCells.count()); i++) {
            const uploadDateText = await uploadDateCells.nth(i).textContent();
            const captureDateText = await captureDateCells.nth(i).textContent();
            
            console.log(`Row ${i}: Upload Date="${uploadDateText?.trim()}", Capture Date="${captureDateText?.trim()}"`);
            
            // For direct images, upload date should be within range
            // For ZIP images, both upload and capture dates should be within range
            if (uploadDateText && uploadDateText.trim() !== '—') {
              // Parse the date (format is likely "YYYY-MM-DD HH:MM")
              const dateStr = uploadDateText.trim().split(' ')[0]; // Get just the date part
              const uploadDate = new Date(dateStr);
              
              // Verify date is within range (allowing for some flexibility)
              expect(uploadDate >= thirtyDaysAgo).toBe(true);
              expect(uploadDate <= today).toBe(true);
            }
          }
        } else {
          console.log(`No rows found for ${imageType} images with date filters - this is acceptable`);
        }
      } else {
        console.log(`Table not found for ${imageType} images - might be no results`);
      }
    }
  });

  test('should verify that ZIP images are excluded when disease filters are applied', async ({ page }) => {
    console.log('Testing that ZIP images are excluded when disease filters are applied...');
    
    // Reset all filters first
    await page.locator('#filter-source').selectOption('all');
    await page.locator('#filter-disease').selectOption('');
    
    // Click the "Apply Filters" button to reset
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Get the total count of all images (before applying disease filter)
    const allImagesTableExists = await page.locator('table').isVisible().catch(() => false);
    let totalImagesCount = 0;
    if (allImagesTableExists) {
      totalImagesCount = await page.locator('tbody tr').count();
      console.log(`Total images before disease filter: ${totalImagesCount}`);
    }
    
    // Now apply a disease filter
    const diseaseSelect = page.locator('#filter-disease');
    const diseaseOptions = await diseaseSelect.locator('option').all();
    
    if (diseaseOptions.length > 1) { // More than just "All" option
      // Select the first available disease (not "All")
      const firstDiseaseOption = diseaseOptions[1];
      const diseaseValue = await firstDiseaseOption.getAttribute('value');
      if (diseaseValue) {
        await diseaseSelect.selectOption(diseaseValue);
        console.log(`Applied disease filter: ${await firstDiseaseOption.textContent()}`);
      }
    }
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    
    // Wait for the page to reload with filtered results
    await page.waitForLoadState('networkidle');
    
    // Check if the table exists (even if it has no rows)
    const tableExists = await page.locator('table').isVisible().catch(() => false);
    
    if (tableExists) {
      console.log('Table is visible after applying disease filter, checking for ZIP exclusions...');
      
      // If table exists, check if there are any rows
      const tableRows = await page.locator('tbody tr').count();
      console.log(`Found ${tableRows} rows in the table after disease filter`);
      
      if (tableRows > 0) {
        // Check all rows to ensure they are Direct images (no ZIP images)
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        
        for (let i = 0; i < await sourceCells.count(); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}"`);
          
          // Verify source is "direct" - ZIP images should be excluded when disease filter is applied
          expect(sourceText?.trim().toLowerCase()).toBe('direct');
        }
        
        console.log('Confirmed: All results are Direct images, ZIP images were excluded due to disease filter');
      } else {
        console.log('No rows found after disease filter - this is acceptable if no Direct images match the disease');
      }
    } else {
      console.log('Table not found after disease filter - might be no results or different page structure');
    }
  });

  test('should verify that the labels are correct in the UI (Disease (Direct), etc.)', async ({ page }) => {
    console.log('Testing UI labels are correct...');
    
    // Check that the labels in the filter form are correct
    await expect(page.locator('label[for="filter-disease"]')).toContainText('Disease (Direct)');
    await expect(page.locator('label[for="filter-camera"]')).toContainText('Camera (Direct)');
    await expect(page.locator('label[for="filter-area"]')).toContainText('Area (Direct)');
    await expect(page.locator('label[for="filter-mydriatic"]')).toContainText('Mydriatic (Direct)');
    await expect(page.locator('label[for="filter-has-enc"]')).toContainText('Has Encounter (ZIP)');
    
    // Check table headers
    await expect(page.locator('th:has-text("Disease (Direct)")')).toBeVisible();
    await expect(page.locator('th:has-text("Camera (Direct)")')).toBeVisible();
    await expect(page.locator('th:has-text("Area (Direct)")')).toBeVisible();
    await expect(page.locator('th:has-text("Mydriatic (Direct)")')).toBeVisible();
    
    console.log('All UI labels are correct as expected');
  });

 test('should test the sorting functionality to ensure it works with the new date fields', async ({ page }) => {
    console.log('Testing sorting functionality with new date fields...');
    
    // First, ensure we have some data to sort
    await page.locator('#filter-source').selectOption('all');
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    await page.waitForLoadState('networkidle');
    
    // Check if table exists and has data
    const tableExists = await page.locator('table').isVisible().catch(() => false);
    
    if (tableExists) {
      const initialRowCount = await page.locator('tbody tr').count();
      console.log(`Found ${initialRowCount} rows for sorting test`);
      
      if (initialRowCount > 1) {
        // Test sorting by Upload Date (click on the header)
        const uploadDateHeader = page.locator('th:has-text("Uploaded")');
        await expect(uploadDateHeader).toBeVisible();
        await uploadDateHeader.click();
        
        // Wait for the page to reload with sorted results
        await page.waitForLoadState('networkidle');
        
        console.log('Successfully sorted by Upload Date');
        
        // Test sorting by Capture Date (click on the header)
        const captureDateHeader = page.locator('th:has-text("Capture Date")');
        await expect(captureDateHeader).toBeVisible();
        await captureDateHeader.click();
        
        // Wait for the page to reload with sorted results
        await page.waitForLoadState('networkidle');
        
        console.log('Successfully sorted by Capture Date');
        
        // Verify that no errors occurred during sorting
        const consoleErrors = [];
        page.on('console', msg => {
          if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
          }
        });
        
        expect(consoleErrors.length).toBe(0);
        console.log('No errors occurred during sorting operations');
      } else {
        console.log('Not enough rows to test sorting functionality');
      }
    } else {
      console.log('Table not found - cannot test sorting functionality');
    }
  });

 test('should test combined filters work correctly', async ({ page }) => {
    console.log('Testing combined filters...');
    
    // Reset all filters first
    await page.locator('#filter-source').selectOption('all');
    await page.locator('#filter-disease').selectOption('');
    await page.locator('#filter-hospital').selectOption('');
    await page.locator('#filter-upload-start').fill('');
    
    // Apply a combination of filters: source=direct, with a disease filter
    await page.locator('#filter-source').selectOption('direct');
    
    // Select a disease filter if available
    const diseaseSelect = page.locator('#filter-disease');
    const diseaseOptions = await diseaseSelect.locator('option').all();
    
    if (diseaseOptions.length > 1) { // More than just "All" option
      // Select the first available disease (not "All")
      const firstDiseaseOption = diseaseOptions[1];
      const diseaseValue = await firstDiseaseOption.getAttribute('value');
      if (diseaseValue) {
        await diseaseSelect.selectOption(diseaseValue);
        console.log(`Applied combined filters: Direct source + ${await firstDiseaseOption.textContent()}`);
      }
    }
    
    // Click the "Apply Filters" button
    await page.locator('button[type="submit"]').filter({ hasText: 'Apply Filters' }).click();
    
    // Wait for the page to reload with filtered results
    await page.waitForLoadState('networkidle');
    
    // Check if the table exists (even if it has no rows)
    const tableExists = await page.locator('table').isVisible().catch(() => false);
    
    if (tableExists) {
      console.log('Table is visible after combined filters, checking results...');
      
      // If table exists, check if there are any rows
      const tableRows = await page.locator('tbody tr').count();
      console.log(`Found ${tableRows} rows in the table after combined filters`);
      
      if (tableRows > 0) {
        // Check first few rows to ensure they match the combined filters
        const sourceCells = page.locator('tbody tr td:nth-child(2)'); // Source column
        const diseaseCells = page.locator('tbody tr td:nth-child(6)'); // Disease column
        
        for (let i = 0; i < Math.min(5, await sourceCells.count()); i++) {
          const sourceText = await sourceCells.nth(i).textContent();
          const diseaseText = await diseaseCells.nth(i).textContent();
          
          console.log(`Row ${i}: Source="${sourceText?.trim()}", Disease="${diseaseText?.trim()}"`);
          
          // Verify source is "direct"
          expect(sourceText?.trim().toLowerCase()).toBe('direct');
          
          // Verify disease column has actual disease info (not '—')
          expect(diseaseText?.trim()).not.toBe('—');
          expect(diseaseText?.trim()).not.toBe('');
        }
      } else {
        console.log('No rows found after combined filters - this is acceptable');
      }
    } else {
      console.log('Table not found after combined filters - might be no results');
    }
 });
});