# Rate Limiter Test Suite Documentation

## Overview

This document describes the comprehensive test suite for the Flask-Limiter 4.0 implementation in the Fundus Image Manager application. The test suite includes unit tests, integration tests, and end-to-end tests to verify that rate limiting works correctly across different storage backends and configurations.

## Test Files

### 1. Unit Tests (`test_rate_limiter_unit.py`)
- **Purpose**: Test individual rate limiter utilities in isolation
- **Count**: 39 test cases
- **Coverage**:
  - Rate limit decorators (`@rate_limit`, `@auth_rate_limit`, etc.)
  - Key generation functions
  - Error handling (including RuntimeLimit objects)
  - Configuration parsing
  - Role-based rate limits
  - Rate limit management functions
  - Flash message handling
  - Rate limit initialization

### 2. Integration Tests (`test_rate_limiter_integration.py`)
- **Purpose**: Test rate limiting within Flask application context
- **Count**: 22 test cases
- **Coverage**:
  - Rate limit behavior with different backends
  - Rate limit headers
  - Authentication integration
  - Request context handling
  - Rate limit exemption
  - Concurrent request handling
  - Performance impact testing

### 3. End-to-End Tests (`test_rate_limiter_e2e.py`)
- **Purpose**: Test rate limiting against a running server
- **Count**: 10 test cases
- **Coverage**:
  - Actual HTTP requests to multiple endpoints
  - Rate limit enforcement
  - Response headers
  - Different endpoint types (homepage, API, style guide, etc.)
  - Concurrent requests
  - Rate limit recovery after time window
  - Rate limit management integration

### 4. Test Runner (`test_rate_limiter_runner.py`)
- **Purpose**: Execute different test suites with proper configuration
- **Features**:
  - Supports running individual test suites or all tests
  - Checks if Flask app is running before E2E tests
  - Provides test result summaries
  - Includes rate limit management command examples
- **Usage**:
  ```bash
  # Run all tests
  uv run python tests/test_rate_limiter_runner.py all
  
  # Run specific test suite
  uv run python tests/test_rate_limiter_runner.py unit
  uv run python tests/test_rate_limiter_runner.py integration
  uv run python tests/test_rate_limiter_runner.py e2e
  
  # Run E2E tests with app check
  uv run python tests/test_rate_limiter_runner.py e2e --check-app
  ```

## Configuration

The tests use the configuration from the `.env` file:

```bash
# Base URL for E2E tests
BASE_URL=http://127.0.0.1:5001
FLASK_PORT=5001

# Rate limiting configuration
RATELIMIT_ENABLED=true
RATELIMIT_STORAGE_URI=redis://localhost:6379/10
REDIS_URL=redis://localhost:6379/10
RATELIMIT_DEFAULT=500 per hour, 50 per minute
RATELIMIT_APPLICATION=1000 per hour, 100 per minute
RATELIMIT_HEADERS_ENABLED=true
RATELIMIT_STRATEGY=fixed-window
RATELIMIT_SWALLOW_ERRORS=true
RATELIMIT_KEY_PREFIX=
```

## Test Endpoints

The E2E tests verify rate limiting on the following endpoints:

| Endpoint | Expected Limit | Description |
|----------|----------------|-------------|
| `/` | 20 per minute | Homepage |
| `/style_guide` | 10 per minute | Style guide page |
| `/test-rate-limit` | 5 per minute | Dedicated test endpoint |
| `/favicon.ico` | 100 per minute | Static resource |
| `/healthz` | 100 per minute | Health check endpoint |
| `/api/hospitals` | 100 per minute | API endpoint (may require auth) |

## Running Tests

### Prerequisites

1. Ensure Redis is running (if using Redis backend):
   ```bash
   redis-server
   ```

2. Install dependencies:
   ```bash
   uv pip install
   ```

3. Start the application (for E2E tests):
   ```bash
   uv run app.py
   ```

### Running Individual Test Suites

1. **Unit Tests** (Fast, no server required):
   ```bash
   uv run python tests/test_rate_limiter_unit.py
   ```

2. **Integration Tests** (Medium speed, uses Flask app context):
   ```bash
   uv run python tests/test_rate_limiter_integration.py
   ```

3. **End-to-End Tests** (Slow, requires running server):
   ```bash
   uv run python tests/test_rate_limiter_e2e.py
   ```

### Running All Tests

```bash
uv run python tests/test_rate_limiter_runner.py
```

## Test Coverage

### Rate Limit Decorators

- `@rate_limit`: General purpose rate limiting
- `@auth_rate_limit`: Authentication endpoints (5 per minute)
- `@upload_rate_limit`: File upload endpoints (200 per minute)
- `@api_rate_limit`: API endpoints (100 per minute)
- `@admin_rate_limit`: Admin endpoints (100 per minute)
- `@rate_limit_with_feedback`: Rate limiting with user feedback

### Storage Backends

- **Memory Storage**: For development and testing
- **Redis Storage**: For production (recommended)
- **Memcached Storage**: Alternative production backend

### Key Features Tested

1. **Key Generation**: IP-based and user-based rate limit keys
2. **Rate Limit Enforcement**: Verifying limits are applied correctly
3. **Headers**: Rate limit headers in responses
4. **Error Handling**: Custom error messages and responses
5. **Role-based Limits**: Different limits for different user roles
6. **Exemptions**: Conditional rate limit exemptions
7. **Shared Limits**: Resource-specific shared limits
8. **Dynamic Limits**: Configuration-based rate limits

## Test Structure

### Test Classes Organization

#### Unit Tests (`test_rate_limiter_unit.py`)
- `TestRateLimitKeyGeneration`: Tests key generation for authenticated/anonymous users
- `TestRateLimitDecorators`: Tests all decorator functions with various parameters
- `TestRateLimitErrorHandling`: Tests error handling for different request types
- `TestRateLimitLogging`: Tests logging functionality
- `TestUserRateLimits`: Tests role-based rate limit retrieval
- `TestDynamicRateLimits`: Tests configuration-based rate limits
- `TestSharedResourceLimits`: Tests shared resource limit functionality
- `TestConditionalExemption`: Tests conditional exemption logic
- `TestRateLimitManagement`: Tests clearing and status functions
- `TestRateLimitInitialization`: Tests rate limiter initialization

#### Integration Tests (`test_rate_limiter_integration.py`)
- `TestRateLimiterIntegration`: Basic integration tests
- `TestRateLimitKeyGenerationIntegration`: Key generation with Flask context
- `TestRateLimitDecoratorIntegration`: Decorator tests with Flask app
- `TestRateLimitHeadersIntegration`: Response header tests
- `TestRateLimitStorageBackends`: Tests with different storage backends
- `TestRateLimitManagementIntegration`: Management functions in context
- `TestRateLimitWithAuthentication`: Authenticated user rate limiting
- `TestRateLimitErrorHandlingIntegration`: Error response formats
- `TestRateLimitPerformanceIntegration`: Performance impact tests

#### E2E Tests (`test_rate_limiter_e2e.py`)
- `TestRateLimiterE2E`: Complete end-to-end testing against running server
  - Homepage rate limiting
  - Style guide rate limiting
  - API rate limiting
  - Test endpoint rate limiting
  - Static resource rate limiting
  - Health check rate limiting
  - Different endpoints with different limits
  - Rate limit recovery after time window
  - Concurrent request handling
  - Rate limit management integration

## Troubleshooting

### Common Issues

1. **Redis Connection Error**:
   - Ensure Redis is running: `redis-server`
   - Check Redis configuration in `.env`
   - Test with: `uv run python scripts/test_redis_connection.py`
   - Verify Redis is accessible on the configured port (default: 6379)

2. **E2E Test Failures**:
   - Ensure the application is running on the correct port
   - Check `BASE_URL` and `FLASK_PORT` in `.env`
   - Verify rate limiting is enabled (`RATELIMIT_ENABLED=true`)
   - Use `--check-app` flag to verify app is running: `uv run python tests/test_rate_limiter_runner.py e2e --check-app`

3. **Test Timeouts**:
   - Rate limit tests use time-based assertions
   - Adjust timing if running on slow systems
   - Check system clock synchronization
   - E2E tests may need longer timeouts on slow networks

4. **Import Errors**:
   - Ensure all dependencies are installed: `uv pip install`
   - Check that the project root is in the Python path
   - Verify `.env` file exists and is properly configured

5. **Authentication Issues**:
   - API endpoints may require authentication
   - Test users should be properly set up in the database
   - Check session management for authenticated tests

### Debug Mode

Enable debug logging for rate limiting:

```python
import logging
logging.getLogger("flask-limiter").setLevel(logging.DEBUG)
logging.getLogger("rate_limit").setLevel(logging.DEBUG)
```

### Test Isolation Issues

If tests are interfering with each other:
1. Check that rate limits are properly cleared between tests
2. Verify test fixtures are creating clean state
3. Consider increasing time delays between rate limit checks
4. Use unique test keys when possible

## Best Practices

1. **Test Isolation**: Each test runs in isolation with clean state
2. **Mocking**: Unit tests use mocks to avoid external dependencies
3. **Fixtures**: Integration tests use pytest fixtures for setup
4. **Timing**: Tests account for rate limit timing windows
5. **Cleanup**: Tests clean up after themselves to avoid interference

## Performance Considerations

- Unit tests run in milliseconds (typically < 1 second total)
- Integration tests run in seconds (typically 5-15 seconds)
- E2E tests run in tens of seconds (typically 60-120 seconds)
- Total test suite completes in under 3 minutes depending on system performance

### Performance Tests Included

1. **Request Performance Impact**:
   - Measures time for multiple rate-limited requests
   - Verifies rate limiting doesn't significantly impact response times

2. **Concurrent Request Testing**:
   - Tests rate limiting behavior with multiple simultaneous requests
   - Verifies thread safety and consistency

## Rate Limit Management

The test suite includes integration with rate limit management scripts:

```bash
# List all rate limit blocks
uv run scripts/manage_rate_limits.py list

# Get status for specific key
uv run scripts/manage_rate_limits.py status --key <key>

# Clear rate limit for specific key
uv run scripts/manage_rate_limits.py clear --key <key>

# Clear all rate limits
uv run scripts/manage_rate_limits.py clear-all
```

## Future Enhancements

1. **Load Testing**: Add more comprehensive concurrent request testing
2. **Performance Benchmarks**: Measure rate limiter performance under different loads
3. **Chaos Testing**: Test behavior under failure conditions (Redis disconnect, etc.)
4. **Monitoring Integration**: Test with monitoring systems and metrics collection
5. **Automated CI/CD**: Integrate with continuous integration pipelines
6. **Storage Backend Tests**: Add more comprehensive tests for Memcached and other backends
7. **Distributed Rate Limiting**: Test rate limiting across multiple application instances

## References

- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/)
- [Redis Documentation](https://redis.io/documentation)
- [Rate Limiting Best Practices](docs/01-SETUP/rate_limiting.md)
- [Rate Limit Fixes Summary](docs/01-SETUP/RATE_LIMIT_FIXES_SUMMARY.md)