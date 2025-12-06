# Authentication Routes Tests

This document provides an overview of the authentication routes tests in the fundus image management application.

## Test Coverage

| Test Class | Test Method | Description | Status |
|------------|-------------|-------------|--------|
| TestLoginRoute | test_login_get_request | Tests that GET request to login returns the login template | ✅ Pass |
| TestLoginRoute | test_login_already_authenticated | Tests that authenticated users are redirected to appropriate pages | ✅ Pass |
| TestLoginRoute | test_login_valid_credentials | Tests successful login with valid credentials | ✅ Pass |
| TestLoginRoute | test_login_invalid_credentials | Tests login with invalid credentials | ✅ Pass |
| TestLoginRoute | test_login_inactive_user | Tests login with inactive user account | ✅ Pass |
| TestLoginRoute | test_login_user_lockout | Tests that user gets locked after too many failed attempts | ✅ Pass |
| TestLoginRoute | test_login_ip_lockout | Tests that IP gets locked after too many failed attempts | ✅ Pass |
| TestLogoutRoute | test_logout_authenticated_user | Tests that authenticated users can logout successfully | ✅ Pass |
| TestLogoutRoute | test_logout_unauthenticated_user | Tests that unauthenticated users are redirected when trying to logout | ✅ Pass |
| TestForgotPasswordRoute | test_forgot_password_get_request | Tests that GET request to forgot-password returns the template | ✅ Pass |
| TestForgotPasswordRoute | test_forgot_password_valid_email | Tests forgot password with valid email | ✅ Pass |
| TestForgotPasswordRoute | test_forgot_password_invalid_email | Tests forgot password with invalid email format | ✅ Pass |
| TestForgotPasswordRoute | test_forgot_password_nonexistent_email | Tests forgot password with non-existent email (should not reveal this) | ✅ Pass |
| TestForgotPasswordRoute | test_forgot_password_rate_limiting | Tests that forgot password is rate limited | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_get_request | Tests that GET request to reset-password returns the template | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_with_valid_otp | Tests password reset with valid OTP | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_with_invalid_otp | Tests password reset with invalid OTP | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_with_expired_otp | Tests password reset with expired OTP | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_mismatched_passwords | Tests password reset with mismatched passwords | ✅ Pass |
| TestResetPasswordRoute | test_reset_password_short_password | Tests password reset with too short password | ✅ Pass |
| TestAuthHelperRoutes | test_ping_route_authenticated | Tests /ping route for authenticated users | ✅ Pass |
| TestAuthHelperRoutes | test_ping_route_unauthenticated | Tests /ping route for unauthenticated users | ✅ Pass |
| TestAuthHelperRoutes | test_check_session_authenticated | Tests /check-session route for authenticated users | ✅ Pass |
| TestAuthHelperRoutes | test_check_session_unauthenticated | Tests /check-session route for unauthenticated users | ✅ Pass |
| TestAuthHelperRoutes | test_check_email_status | Tests /check-email-status route | ✅ Pass |
| TestAuthSecurityFeatures | test_csrf_protection | Tests that CSRF protection is working | ✅ Pass |
| TestAuthSecurityFeatures | test_payload_size_validation | Tests that payload size validation is working | ✅ Pass |
| TestAuthSecurityFeatures | test_form_field_validation | Tests that form field validation is working | ✅ Pass |

## Test File Location

The authentication routes tests are located in [`tests/test_auth_routes.py`](../../../tests/test_auth_routes.py).

## Running the Tests

To run the authentication routes tests:

```bash
uv run pytest tests/test_auth_routes.py -v
```

## Test Dependencies

The authentication routes tests depend on:

1. **Flask Test Client**: For simulating HTTP requests
2. **Pytest Fixtures**: For setting up test environment and test data
3. **Test Database**: For testing database operations without affecting production data
4. **Mock Objects**: For mocking external dependencies like email sending

## Key Test Features

1. **Authentication Flow Testing**: Tests complete login and logout flows
2. **Security Testing**: Tests security features like rate limiting, CSRF protection, and account lockout
3. **Password Reset Testing**: Tests the complete password reset flow with OTP
4. **Role-based Redirect Testing**: Tests that users are redirected to appropriate pages based on their roles
5. **Error Handling Testing**: Tests various error conditions and edge cases

## Test Users

The tests use the following test users:

| Username | Role | Password | Description |
|----------|------|----------|-------------|
| test_admin | admin | Test@2026 | Administrator user with full system access |
| test_resident2 | ophthalmologist | Test@2026 | Resident2 user with grading permissions |
| test_resident | ophthalmologist | TestPassword123! | Resident user with grading permissions |
| testResident2 | ophthalmologist | TestPassword123! | Resident2 user with specific role slots |
| testResident | ophthalmologist | TestPassword123! | Resident user with specific role slots |
| testArbitrator | ophthalmologist | TestPassword123! | Arbitrator user with specific role slots |
| test_uploader | fileUploader | TestPassword123! | File uploader user (created during tests) |

## Security Features Tested

1. **Rate Limiting**: Tests that API endpoints are rate limited to prevent abuse
2. **CSRF Protection**: Tests that CSRF tokens are validated for form submissions
3. **Account Lockout**: Tests that accounts are locked after too many failed login attempts
4. **IP Lockout**: Tests that IP addresses are locked after too many failed attempts
5. **Password Validation**: Tests that passwords meet minimum requirements
6. **Session Management**: Tests that sessions are properly managed and invalidated

## Best Practices Demonstrated

1. **Test Isolation**: Each test is independent and doesn't rely on other tests
2. **Cleanup**: Tests properly clean up any created resources
3. **Mocking**: External dependencies are mocked to ensure reliable tests
4. **Fixture Usage**: Pytest fixtures are used for common setup and teardown
5. **Comprehensive Coverage**: Tests cover both success and failure scenarios