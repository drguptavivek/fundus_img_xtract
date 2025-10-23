# Flask-Limiter 4.0 Test Suite

This document describes the comprehensive test suite for the Flask-Limiter 4.0 implementation in the Fundus Image Manager application.

## Test Files Overview

### 1. Unit Tests (`test_rate_limiter_unit.py`)
Comprehensive unit tests for all rate limiter utilities and functions.

**Test Categories:**
- **Rate Limit Key Generation**: Tests key generation for authenticated and anonymous users
- **Rate Limit Decorators**: Tests all decorator functions (`rate_limit`, `auth_rate_limit`, `upload_rate_limit`, `api_rate_limit`, `admin_rate_limit`)
- **Error Handling**: Tests rate limit error handling for different request types
- **Logging**: Tests rate limit violation logging functionality
- **User Rate Limits**: Tests role-based rate limit assignment
- **Dynamic Rate Limits**: Tests dynamic configuration loading
- **Shared Resource Limits**: Tests shared resource protection
- **Conditional Exemption**: Tests conditional rate limit exemption
- **Rate Limit Management**: Tests clearing and status checking functions
- **Initialization**: Tests rate limiter initialization with different backends

### 2. Integration Tests (`test_rate_limiter_integration.py`)
Integration tests that work with Flask app context.

**Test Categories:**
- **Request Limit Handling**: Tests rate limit error handling in app context
- **Key Generation Integration**: Tests key generation with Flask context
- **Rate Limit Decorators**: Tests decorators with real Flask routes
- **Rate Limit Headers**: Tests rate limit headers in responses
- **Storage Backends**: Tests different storage backends (memory, Redis)
- **Rate Limit Management**: Tests management functions in app context
- **Authentication**: Tests rate limiting with authenticated users
- **Error Handling**: Tests error response formats
- **Performance**: Tests performance impact of rate limiting

### 3. End-to-End Tests (`test_rate_limiter_e2e.py`)
End-to-end tests against a running Flask application.

**Test Categories:**
- **Homepage Rate Limiting**: Tests rate limiting on the homepage endpoint
- **Style Guide Rate Limiting**: Tests rate limiting on style guide endpoint
- **API Rate Limiting**: Tests rate limiting on API endpoints
- **Test Rate Limit Endpoint**: Tests the dedicated test endpoint
- **Favicon Rate Limiting**: Tests rate limiting on favicon endpoint
- **Health Check Rate Limiting**: Tests rate limiting on health check endpoint
- **Different Endpoints Different Limits**: Tests varying limits across endpoints
- **Rate Limit Recovery**: Tests rate limit recovery after time window
- **Concurrent Requests**: Tests rate limiting with concurrent requests

### 4. Test Runner (`test_rate_limiter_runner.py`)
A test runner script to execute different test suites.

**Usage:**
```bash
# Run unit tests
uv run python tests/test_rate_limiter_runner.py unit

# Run integration tests
uv run python tests/test_rate_limiter_runner.py integration

# Run end-to-end tests (requires running app)
uv run python tests/test_rate_limiter_runner.py e2e

# Run all tests
uv run python tests/test_rate_limiter_runner.py all

# Run E2E tests with app check
uv run python tests/test_rate_limiter_runner.py e2e --check-app
```

## Configuration

The tests use the following configuration from `.env`:

- **BASE_URL**: Base URL for the application (default: `http://127.0.0.1`)
- **FLASK_PORT**: Port for the Flask application (default: `5000`)
- **RATELIMIT_***: All rate limiting configuration variables

## Test Coverage

### Features Tested

1. **Rate Limit Decorators**
   - Basic rate limiting
   - Authentication-specific rate limiting
   - Upload rate limiting
   - API rate limiting
   - Admin rate limiting
   - Rate limiting with feedback

2. **Key Generation**
   - User-based keys for authenticated users
   - IP-based keys for anonymous users
   - Fallback handling

3. **Error Handling**
   - API error responses (JSON)
   - Web error responses (HTML)
   - Login page redirects
   - Custom error messages

4. **Storage Backends**
   - Memory storage (development)
   - Redis storage (production)
   - Memcached storage (alternative)

5. **Rate Limit Management**
   - Clearing specific rate limits
   - Clearing all rate limits
   - Getting rate limit status
   - Rate limit recovery

6. **Headers**
   - Rate limit headers in responses
   - Custom header configuration
   - Header absence handling

7. **Performance**
   - Performance impact measurement
   - Concurrent request handling
   - Rate limit overhead

## Running Tests

### Prerequisites

1. **Unit/Integration Tests**: No prerequisites beyond the development environment
2. **E2E Tests**: Flask application must be running

### Running Individual Test Files

```bash
# Unit tests
uv run python -m pytest tests/test_rate_limiter_unit.py -v

# Integration tests
uv run python -m pytest tests/test_rate_limiter_integration.py -v

# E2E tests (requires running app)
uv run python tests/test_rate_limiter_e2e.py
```

### Running with Test Runner

```bash
# Run all unit tests
uv run python tests/test_rate_limiter_runner.py unit

# Run all integration tests
uv run python tests/test_rate_limiter_runner.py integration

# Run all E2E tests (requires running app)
uv run python tests/test_rate_limiter_runner.py e2e

# Run all test suites
uv run python tests/test_rate_limiter_runner.py all
```

## Test Environment Variables

The tests respect the following environment variables:

- `TESTING`: Set to `true` for test environment
- `RATELIMIT_ENABLED`: Can be set to `false` to disable rate limiting for tests
- `RATELIMIT_STORAGE_URI`: Can be set to `memory://` for faster tests
- `BASE_URL`: Base URL for E2E tests
- `FLASK_PORT`: Port for E2E tests

## Known Issues and Limitations

### Unit Tests
- Some tests may fail due to Flask context requirements
- Mocking of Flask-Login current_user requires careful setup

### Integration Tests
- Authentication middleware may interfere with some tests
- Rate limiting behavior may vary with different storage backends

### E2E Tests
- Requires running Flask application
- Tests may be affected by network latency
- Rate limit windows may cause test flakiness

## Troubleshooting

### Unit Test Failures

1. **Context Issues**: Ensure proper Flask context mocking
2. **Import Issues**: Verify all required modules are imported
3. **Mock Issues**: Check mock configuration and return values

### Integration Test Failures

1. **Authentication Issues**: Some endpoints may require authentication
2. **Rate Limit Not Applied**: Verify rate limiter initialization
3. **Storage Issues**: Check storage backend configuration

### E2E Test Failures

1. **App Not Running**: Start the Flask application first
2. **Connection Issues**: Verify BASE_URL and FLASK_PORT configuration
3. **Rate Limit Exhaustion**: Wait for rate limit windows to reset

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Cleanup**: Clean up rate limits after each test
3. **Mocking**: Use appropriate mocking for external dependencies
4. **Assertions**: Provide clear and descriptive assertions
5. **Documentation**: Document test purpose and expected behavior

## Future Improvements

1. **Test Coverage**: Add tests for edge cases and error conditions
2. **Performance Testing**: Add more comprehensive performance tests
3. **Load Testing**: Add load testing scenarios
4. **Mocking**: Improve mocking strategies for better isolation
5. **CI/CD**: Integrate tests into CI/CD pipeline

## Dependencies

- `pytest`: Test framework
- `requests`: HTTP client for E2E tests
- `python-dotenv`: Environment variable loading
- `unittest.mock`: Mocking framework
- `flask`: Flask framework (for integration tests)