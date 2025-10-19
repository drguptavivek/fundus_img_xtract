# Rate Limiting Configuration

This document explains how rate limiting is configured in the Fundus Image Manager application.

## Overview

The application uses Flask-Limiter to implement rate limiting for API endpoints and web routes. Rate limiting helps prevent abuse and ensures fair usage of resources.

## Configuration

Rate limiting is configured through environment variables in the `.env` file:

```bash
# Enable/disable rate limiting
RATELIMIT_ENABLED=true

# Default rate limit applied to all routes
RATELIMIT_DEFAULT=500 per hour, 50 per minute

# Meta limits for overall protection (applies to all limits)
RATELIMIT_META_LIMITS=1000 per hour, 100 per minute

# Rate limit storage backend
RATELIMIT_STORAGE_URL=memcached://

# Memcached server configuration
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
RATELIMIT_MEMCACHED_CONNECT_TIMEOUT=2
RATELIMIT_MEMCACHED_TIMEOUT=1
RATELIMIT_MEMCACHED_MAX_POOL_SIZE=10
# RATELIMIT_MEMCACHED_USERNAME=
# RATELIMIT_MEMCACHED_PASSWORD=

# Rate limiting strategy (fixed-window, moving-window, sliding-window-counter)
RATELIMIT_STRATEGY=fixed-window

# Include rate limit headers in responses
RATELIMIT_HEADERS_ENABLED=true

# Swallow errors when storage backend is unavailable
RATELIMIT_SWALLOW_ERRORS=true

# Fail immediately on first breach
RATELIMIT_FAIL_ON_FIRST_BREACH=false

# Deduplicate identical requests
RATELIMIT_DEDUPLICATE=false

# Apply limits per HTTP method
RATELIMIT_DEFAULTS_PER_METHOD=false

# Default cost per request
RATELIMIT_DEFAULTS_COST=1

# Key prefix for rate limits
RATELIMIT_KEY_PREFIX=

# Shared resource limits
RATELIMIT_SHARED_DEFAULT=100 per hour
```

## Storage Backends

### Memory Storage (Development)
```bash
RATELIMIT_STORAGE_URL=memory://
```
- Suitable for development and single-instance deployments
- Rate limit data is lost on application restart

### Memcached (Production)
```bash
RATELIMIT_STORAGE_URL=memcached://
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
```
- Recommended for production environments
- Shared across multiple application instances
- Requires memcached server to be installed and running
- Currently configured and active in this application

### Redis (Production Alternative)
```bash
RATELIMIT_STORAGE_URL=redis://localhost:6379/0
REDIS_URL=redis://localhost:6379/0
```
- Alternative to Memcached for production
- Shared across multiple application instances
- Requires Redis server to be installed and running

## Rate Limit Decorators

The application provides several decorators for applying rate limits. These decorators properly override the default limits when applied to routes.

### Basic Rate Limit
```python
from utils.rate_limiter import rate_limit

@app.route('/api/data')
@rate_limit("100 per hour")
def get_data():
    return jsonify(data)
```

### Authentication Endpoints
Authentication endpoints use stricter rate limits for security:

```python
from utils.rate_limiter import auth_rate_limit

@auth_bp.route('/login', methods=['POST'])
@auth_rate_limit("5 per minute")
def login():
    # Login logic - limited to 5 attempts per minute

@auth_bp.route('/forgot-password', methods=['POST'])
@auth_rate_limit("3 per 5 minutes")
def forgot_password():
    # Password reset - limited to 3 attempts per 5 minutes

@auth_bp.route('/reset-password', methods=['POST'])
@auth_rate_limit("5 per 10 minutes")
def reset_password():
    # Password reset - limited to 5 attempts per 10 minutes
```

### Upload Endpoints
```python
from utils.rate_limiter import upload_rate_limit

@upload_bp.route('/upload', methods=['POST'])
@upload_rate_limit("10 per minute")
def upload_file():
    # Upload logic
```

### API Endpoints
```python
from utils.rate_limiter import api_rate_limit

@api_bp.route('/endpoint')
@api_rate_limit("100 per minute")
def api_endpoint():
    # API logic
```

### Admin Endpoints
```python
from utils.rate_limiter import admin_rate_limit

@admin_bp.route('/admin/action')
@admin_rate_limit("50 per minute")
def admin_action():
    # Admin logic
```

### Rate Limit with Feedback
For endpoints that need user feedback when approaching limits:

```python
from utils.rate_limiter import rate_limit_with_feedback

@app.route('/sensitive-action')
@rate_limit_with_feedback("5 per minute", showWarning=True)
def sensitive_action():
    # Will show warning to users when approaching the limit
    # And flash message when limit is exceeded
```

## User-Based Rate Limits

Rate limits can be customized based on user roles:

- **Admin**: 5000 per hour, 100 per minute (upload), 1000 per minute (API)
- **Data Manager/Ophthalmologist**: 2000 per hour, 50 per minute (upload), 500 per minute (API)
- **File Uploader/Optometrist**: 1000 per hour, 20 per minute (upload), 200 per minute (API)
- **Default**: 500 per hour, 10 per minute (upload), 100 per minute (API)

## Advanced Features

### Dynamic Rate Limits
Rate limits can be loaded dynamically from configuration:

```python
from utils.rate_limiter import dynamic_rate_limit_from_config

@app.route("/api/dynamic")
@rate_limit(dynamic_rate_limit_from_config)
def dynamic_endpoint():
    # Limit is loaded from RATELIMIT_API_DYNAMIC_LIMIT config
    return jsonify({"data": []})
```

### Shared Resource Limits
Protect shared resources across multiple endpoints:

```python
from utils.rate_limiter import shared_resource_limit

# Apply to database-intensive endpoints
@shared_resource_limit("database", "50 per minute")
@app.route("/api/query1")
def query1():
    pass

@shared_resource_limit("database", "50 per minute")
@app.route("/api/query2")
def query2():
    pass
```

### Conditional Exemptions
Exempt routes based on conditions:

```python
from utils.rate_limiter import conditional_exempt
from flask_login import current_user

@conditional_exempt(lambda: current_user.is_admin)
@app.route("/admin/bypass")
def admin_endpoint():
    # No rate limiting for admin users
    pass
```

### Meta Limits
Meta limits provide an additional layer of protection by limiting the total number of times any rate limit can be breached within a given period. This is configured globally via `RATELIMIT_META_LIMITS`.

## Logging

Rate limit violations are logged to:
- `logs/flask_limiter.log` - Dedicated Flask-Limiter log file (primary)
- `logs/rate_limit.log` - Application rate limit log file
- `logs/runtime_error.log` - Security monitoring (for backward compatibility)

Log entries include:
- Client IP address
- User information (if authenticated)
- Endpoint and path
- HTTP method
- Rate limit that was exceeded
- Rate limit key that was breached

### Flask-Limiter Logger Configuration

The Flask-Limiter logger is automatically configured in `app.py` and writes to `logs/flask_limiter.log`. This is the primary logger for rate limit violations as per Flask-Limiter documentation.

You can further configure the Flask-Limiter logger:

```python
import logging
limiter_logger = logging.getLogger("flask-limiter")

# Force DEBUG logging
limiter_logger.setLevel(logging.DEBUG)

# Restrict to only error level
limiter_logger.setLevel(logging.ERROR)

# Add a custom filter
limiter_logger.addFilter(CustomFilter)
```

### Rate Limit Management

The application provides a web interface for managing rate limits:

1. **Access the Rate Limit Management page**:
   - Navigate to Admin → Rate Limits in the web interface
   - Or go directly to `/admin/rate-limits/`

2. **Features available**:
   - View rate limit statistics
   - Clear specific rate limits by key
   - Clear all rate limits (with confirmation)
   - Check rate limit status for specific keys
   - Get your current rate limit key

3. **Command-line management**:
   ```bash
   # Clear all rate limits
   uv run python scripts/manage_rate_limits.py clear-all
   
   # Clear a specific rate limit
   uv run python scripts/manage_rate_limits.py clear --key "user:123"
   
   # Check rate limit status
   uv run python scripts/manage_rate_limits.py status
   ```

## Monitoring

To monitor rate limiting:

1. Check the log files:
   ```bash
   tail -f logs/rate_limit.log
   ```

2. Monitor memcached usage:
   ```bash
   echo "stats" | nc localhost 11211
   ```

3. View Flask-Limiter configuration:
   ```bash
   uv run flask limiter config
   ```

4. List all configured rate limits:
   ```bash
   uv run flask limiter limits
   ```

5. Filter limits by endpoint:
   ```bash
   uv run flask limiter limits --endpoint=my_endpoint
   ```

6. Filter limits by path:
   ```bash
   uv run flask limiter limits --path=/api/myendpoint
   ```

7. Check rate limit status for specific key:
   ```bash
   uv run flask limiter limits --key=127.0.0.1
   ```

8. Clear rate limits for specific key:
   ```bash
   uv run flask limiter clear --key=127.0.0.1 -y
   ```

## Troubleshooting

### Memcached Connection Issues
If memcached is not being used:

1. Verify memcached is running:
   ```bash
   ps aux | grep memcached
   ```

2. Check memcached connectivity:
   ```bash
   telnet localhost 11211
   ```

3. Verify configuration in `.env` file:
   ```bash
   # Required for memcached
   RATELIMIT_STORAGE_URL=memcached://
   RATELIMIT_MEMCACHED_SERVERS=localhost:11211
   ```

4. Check application logs for errors:
   ```bash
   tail -f logs/rate_limit.log
   ```

5. Verify Flask-Limiter is using Memcached:
   ```bash
   uv run flask limiter config
   ```
   Look for "MemcachedStorage" in the output under "Rate Limiting Config"

### Rate Limit Not Working
If rate limiting appears not to work:

1. Verify `RATELIMIT_ENABLED=true` in `.env`
2. Check if the endpoint has a rate limit decorator
3. Verify the storage backend is properly configured
4. Check logs for any error messages

### Custom Limits Not Applied
If custom rate limits on routes are not being applied (default limits are used instead):

1. Verify the decorator is applied correctly:
   ```python
   @auth_bp.route('/login', methods=['POST'])
   @auth_rate_limit("5 per minute")  # Must be before the function
   def login():
       pass
   ```

2. Check the actual limits applied to routes:
   ```bash
   uv run flask limiter limits
   ```
   - Custom limits should appear without the default limits
   - If both appear, the decorator may not be overriding defaults

3. Verify the limiter initialization order:
   - Rate limiting must be initialized before blueprints are registered
   - Check `app.py` to ensure `init_rate_limiting(app)` is called before blueprint registration

### Testing Rate Limits
To test if rate limits are working correctly:

1. Use a script to make multiple requests quickly:
   ```python
   import requests
   
   for i in range(10):
       response = requests.post('http://localhost:5000/login', data={'username': 'test', 'password': 'wrong'})
       print(f"Request {i+1}: Status {response.status_code}")
       if response.status_code == 429:
           print(f"Rate limit hit after {i+1} requests")
           break
   ```

2. Check response headers for rate limit info:
   ```bash
   curl -I http://localhost:5000/api/endpoint
   # Look for X-RateLimit-Limit, X-RateLimit-Remaining headers
   ```

## Security Considerations

1. Rate limits are applied per IP address for anonymous users
2. Authenticated users have rate limits applied per user ID
3. Rate limit violations are logged for security monitoring
4. Consider implementing additional monitoring for repeated violations
5. Authentication endpoints have stricter limits to prevent brute force attacks
6. Rate limit keys include user ID when authenticated, preventing shared IP attacks
7. Meta limits provide additional protection against sophisticated attacks

## Best Practices

1. **Always use specific decorators for sensitive endpoints**:
   - Authentication endpoints should use `@auth_rate_limit`
   - Upload endpoints should use `@upload_rate_limit`
   - API endpoints should use `@api_rate_limit`

2. **Test your rate limits**:
   - Verify custom limits override defaults
   - Test with both authenticated and anonymous requests
   - Check that memcached is being used in production

3. **Monitor rate limit violations**:
   - Set up alerts for repeated violations from the same IP
   - Review logs regularly for attack patterns
   - Consider auto-blocking IPs with excessive violations

4. **Configure appropriate limits**:
   - Authentication: 5-10 attempts per minute
   - Password reset: 3-5 attempts per 5-10 minutes
   - File uploads: 10-20 per minute
   - General API: 100-1000 per minute depending on usage

5. **Use memcached in production**:
   - Ensures rate limits persist across app restarts
   - Shared across multiple application instances
   - Better performance than memory storage