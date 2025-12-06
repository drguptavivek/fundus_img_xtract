# Security Protection for Large and Malformed Payloads

This document describes the security measures implemented to protect the Flask application from large or malformed payload attacks, especially on non-logged-in routes.

## Overview

The application now includes multiple layers of protection against payload-based attacks:

1. **Request Size Limiting Middleware** - Validates and limits request payload sizes
2. **Payload Validation Middleware** - Validates structure and content of payloads
3. **CSRF Protection for Non-Authenticated Routes** - Prevents cross-site request forgery
4. **Enhanced Rate Limiting** - Limits request frequency to prevent abuse

## Implementation Details

### 1. Request Size Limiting Middleware (`utils/security_middleware.py`)

The `PayloadSizeValidator` class provides automatic protection against oversized requests:

- **Stricter limits for non-authenticated routes**: Login forms limited to 1KB, other non-authenticated endpoints to 10KB
- **File upload routes excluded**: Routes like `/direct/upload`, `/direct/pregraded`, `/direct/pregraded/grades`, and `/remedio_zip_uploads/upload` have a 100MB limit (they have their own validation)
- **Automatic validation**: Validates content-length before processing requests
- **Custom error handling**: Returns appropriate error responses for API and web requests
- **Logging**: Logs violations for security monitoring

#### Key Features:
```python
# Automatic initialization in app.py
payload_validator = PayloadSizeValidator(app)

# Decorator for custom limits
@validate_payload_size(max_size=1024)  # 1KB limit
def sensitive_route():
    pass
```

### 2. Payload Validation Middleware (`utils/security_middleware.py`)

Multiple decorators for validating different types of payloads:

#### Form Submission Protection:
```python
@protect_form_submission(max_fields=100, max_field_length=1024)
def form_handler():
    pass
```

#### JSON Structure Validation:
```python
@validate_json_structure(required_fields=['username', 'password'])
def api_handler():
    pass
```

### 3. CSRF Protection for Non-Authenticated Routes (`utils/csrf_protection.py`)

Custom CSRF protection for routes that don't use Flask-WTF forms:

#### Token Management:
- Time-based tokens with configurable expiry (default: 1 hour)
- IP address binding for additional security
- HMAC-based validation using the app's secret key

#### Route Protection:
```python
@csrf_protect_for_anonymous(max_age=3600)
def non_auth_route():
    pass
```

#### Origin Validation:
```python
@validate_origin_for_api()
def api_endpoint():
    pass
```

### 4. Enhanced Rate Limiting

Stricter rate limits have been applied to vulnerable endpoints:

- **Homepage**: Reduced from 100 to 20 requests per minute
- **Style Guide**: Limited to 10 requests per minute
- **Authentication endpoints**: Already had strict limits (5 per minute for login)
- **Password reset**: 3 attempts per 5 minutes for forgot password, 5 per 10 minutes for reset

## Protected Routes

### Non-Authenticated Routes with Protection:

1. **`/login`**
   - Payload size: 1KB limit
   - Form validation: Max 10 fields, 100 chars each
   - CSRF protection: Required
   - Rate limiting: 5 per minute

2. **`/forgot-password`**
   - Payload size: 1KB limit
   - Form validation: Max 5 fields, 200 chars each
   - CSRF protection: Required
   - Rate limiting: 3 per 5 minutes

3. **`/reset-password`**
   - Payload size: 2KB limit
   - Form validation: Max 5 fields, 200 chars each
   - CSRF protection: Required
   - Rate limiting: 5 per 10 minutes

4. **`/check-email-status`**
   - CSRF protection: Required
   - Rate limiting: 20 per minute

5. **`/email-sse`**
   - CSRF protection: Required
   - Rate limiting: 20 per minute

## Testing

A test script (`test_security_middleware.py`) is provided to verify the implementation:

```bash
# Run with the app running on localhost:5001
python test_security_middleware.py
```

The test script verifies:
- Large payload protection
- Malformed JSON handling
- CSRF protection
- Rate limiting

## Configuration

The security middleware can be configured through environment variables:

```bash
# Maximum content length for the entire app (existing)
MAX_CONTENT_LENGTH=524288000  # 500MB

# Rate limiting configuration (existing)
RATELIMIT_DEFAULT="500 per hour, 50 per minute"
RATELIMIT_ENABLED=true
```

## Logging

All security violations are logged to dedicated log files:

- `security.log`: General security events
- `rate_limit.log`: Rate limit violations
- `auth.log`: Authentication-related events

## Best Practices

1. **Monitor Logs**: Regularly check security logs for potential attacks
2. **Adjust Limits**: Tune rate limits based on legitimate usage patterns
3. **Update Tokens**: Consider rotating the secret key periodically
4. **Test Regularly**: Run the test script after making changes

## Deployment Considerations

1. **Production Mode**: Ensure Flask is running in production mode (not debug)
2. **Reverse Proxy**: If using a reverse proxy (nginx, Apache), configure it to:
   - Limit request sizes
   - Rate limit requests
   - Block suspicious patterns
3. **Load Balancer**: Configure load balancers to provide additional protection

## Future Enhancements

Potential improvements to consider:

1. **IP-Based Blocking**: Automatic temporary blocking of abusive IPs
2. **CAPTCHA Integration**: Add CAPTCHA for repeated failed attempts
3. **Machine Learning**: Anomaly detection for request patterns
4. **Honeypots**: Dummy endpoints to catch automated attacks

## Troubleshooting

### Common Issues:

1. **Legitimate Requests Blocked**:
   - Check if payload size exceeds limits
   - Verify CSRF token is included
   - Check rate limits

2. **CSRF Token Errors**:
   - Ensure token is included in forms and AJAX requests
   - Check token expiry
   - Verify secret key is configured

3. **Rate Limiting Issues**:
   - Adjust limits in environment configuration
   - Check if multiple users share the same IP
   - Verify rate limiter storage is working