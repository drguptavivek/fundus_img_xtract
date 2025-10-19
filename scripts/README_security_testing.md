# Security Testing Scripts

This directory contains scripts for testing the security middleware implementation and managing test users.

## Scripts Overview

### 1. create_test_admin.py
Creates a test admin user with predefined credentials:
- Username: `Test`
- Password: `test@123`
- Role: `admin`

Usage:
```bash
uv run scripts/create_test_admin.py
```

### 2. cleanup_test_admin.py
Removes the test admin user and all related data.
Use the `--force` flag to delete the user even if they have related data.

Usage:
```bash
# Safe mode (won't delete if user has related data)
uv run scripts/cleanup_test_admin.py

# Force mode (deletes user and all related data)
uv run scripts/cleanup_test_admin.py --force
```

### 3. login_admin.py
Logs in as an admin user and saves session cookies to a JSON file for testing authenticated routes.

Usage:
```bash
# Use default credentials
uv run scripts/login_admin.py

# Specify custom credentials
uv run scripts/login_admin.py --username MyAdmin --password MyPassword

# Specify custom base URL and output file
uv run scripts/login_admin.py --base-url http://localhost:8080 --output my_cookies.json
```

### 4. test_upload_routes.py
Comprehensive test script that verifies:
- Non-authenticated routes have strict payload limits
- File upload routes allow larger payloads
- CSRF protection is working
- Admin user creation and cleanup

Usage:
```bash
uv run test_upload_routes.py
```

## Security Features Tested

1. **Payload Size Limits**:
   - Login routes: 1KB limit
   - Other non-authenticated routes: 10KB limit
   - File upload routes: 100MB limit (with their own validation)

2. **CSRF Protection**:
   - Login forms are protected against CSRF attacks
   - Rate limiting prevents brute force attempts

3. **File Upload Security**:
   - Direct image uploads (`/direct/upload`)
   - Pre-graded uploads (`/direct/pregraded`)
   - Excel grade uploads (`/direct/pregraded/grades`)
   - ZIP file uploads (`/remedio_zip_uploads/upload`)

## Testing Workflow

1. Run the main test script:
   ```bash
   uv run test_upload_routes.py
   ```

2. The script will:
   - Create a test admin user
   - Test all security features
   - Clean up the test user automatically

3. For manual testing:
   - Create a test admin user
   - Use the login script to get cookies
   - Use the cookies in your own test requests
   - Clean up when done

## Notes

- All scripts handle errors gracefully
- The test script automatically cleans up after itself
- CSRF protection blocking login attempts is expected behavior
- File upload routes are excluded from strict payload limits to allow legitimate uploads