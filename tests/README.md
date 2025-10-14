# Image Search Utility Tests

This directory contains comprehensive tests for the new `utils/imageSearchUtil.py` functionality.

## Test Files

1. **`test_imageSearchUtil.py`** - Unit tests with mocked dependencies
2. **`test_runner.py`** - Integration tests with real database
3. **`conftest.py`** - Pytest configuration and fixtures

## Running the Tests

### Unit Tests (Mocked)

Run the unit tests with pytest:

```bash
cd /path/to/fundus_img_xtract
python -m pytest tests/test_imageSearchUtil.py -v
```

### Integration Tests (Real Database)

Run the integration tests that connect to the actual database:

```bash
cd /path/to/fundus_img_xtract
uv run python tests/test_runner.py
```

The integration tests use the admin credentials:
- Username: `admin`
- Password: `Vivek@2026`

## Test Coverage

### Unit Tests Cover:
- Filter validation logic
- Pagination validation
- User scoping functionality
- Task information retrieval
- Image formatting (both direct and ZIP)
- Main search function scenarios
- Legacy function compatibility
- Error handling

### Integration Tests Cover:
- Basic search functionality
- Direct image filter searches
- ZIP image filter searches
- Filter conflict detection
- Task information inclusion
- UUID-based returns (no filename exposure)

## Key Features Tested

1. **Strict Filter Separation**
   - Direct filters exclude ZIP images
   - ZIP filters exclude Direct images
   - Global filters apply to both when no specific filters

2. **UUID-Based Returns**
   - No original filenames in response
   - Clean, standardized data structure

3. **Task Disease Information**
   - Each image includes list of diseases with active tasks
   - Efficient batch querying

4. **User Lab Unit Scoping**
   - Proper access control using `get_user_lab_unit_ids`
   - Admin users can see all images

5. **Error Handling**
   - Custom exceptions for invalid filters
   - Conflict detection
   - Validation errors

## Expected Results

When running the integration tests, you should see output similar to:

```
Starting Image Search Utility Tests
=====================================
Found admin user: admin (ID: 1)
User has admin role: True

=== Testing Basic Search ===
Test 1: Search with no filters
Found X total images, returned Y results
...

=== Testing Direct Image Filter Search ===
Test 1: Search with camera filter
Found X direct images with camera ID 1, returned Y results
All results are direct images: True
...

=== Testing ZIP Image Filter Search ===
...

==================================================
TEST SUMMARY
==================================================
Basic Search: PASSED
Direct Filter Search: PASSED
ZIP Filter Search: PASSED
Filter Conflict Detection: PASSED
Task Information: PASSED
UUID-Based Returns: PASSED

Total: 6/6 tests passed
🎉 All tests passed!
```

## Troubleshooting

### Common Issues

1. **Admin user not found**
   - Ensure the admin user exists in the database
   - Check the username is exactly 'admin'

2. **Database connection errors**
   - Verify the database is accessible
   - Check the DATABASE_URL configuration

3. **No test data**
   - The tests work with existing data in the database
   - Ensure there are some DirectImageUpload and EncounterFile records

4. **Permission errors**
   - Ensure the admin user has the necessary roles
   - Check lab unit assignments

### Debug Mode

For more detailed output, you can modify the test runner to include debug information or add print statements to trace execution.

## Adding New Tests

To add new tests:

1. For unit tests, add new test methods to `test_imageSearchUtil.py`
2. For integration tests, add new test functions to `test_runner.py`
3. Follow the existing naming conventions and structure
4. Include both positive and negative test cases
5. Test edge cases and error conditions

## Notes

- The unit tests use mocked dependencies and don't require a database
- The integration tests use the actual database and existing test data
- Tests are designed to be non-destructive and won't modify existing data
- The test runner creates its own database sessions and properly closes them