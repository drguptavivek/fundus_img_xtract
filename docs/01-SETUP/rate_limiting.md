# Rate Limiting Configuration

This document explains how rate limiting is configured in the Fundus Image Manager application using Flask-Limiter with Redis backend.

## Overview

The application uses Flask-Limiter 4.0+ with Redis as the storage backend to implement distributed rate limiting for API endpoints and web routes. Rate limiting helps prevent abuse and ensures fair usage of resources across multiple application instances.

## Configuration

Rate limiting is configured through environment variables in the `.env` file:

### Core Flask-Limiter 4.0 Settings

```bash
# Enable/disable rate limiting globally
RATELIMIT_ENABLED=true

# Default rate limit applied to all routes (format: "count per period")
RATELIMIT_DEFAULT=500 per hour, 50 per minute

# Application-wide limits that apply to all routes
RATELIMIT_APPLICATION=1000 per hour, 100 per minute

# Rate limiting strategy (fixed-window, moving-window, sliding-window-counter)
RATELIMIT_STRATEGY=fixed-window

# Include rate limit headers in responses
RATELIMIT_HEADERS_ENABLED=true

# Configure individual header names
RATELIMIT_HEADER_LIMIT=X-RateLimit-Limit
RATELIMIT_HEADER_REMAINING=X-RateLimit-Remaining
RATELIMIT_HEADER_RESET=X-RateLimit-Reset

# Swallow errors when storage backend is unavailable (useful for development)
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

# Routes exempt from rate limiting (comma-separated patterns)
RATELIMIT_DEFAULTS_EXEMPT=
```

### Redis Storage Configuration

```bash
# Storage Backend Configuration
# -------------------------------------------------------------------
# Primary storage backend for rate limiting
# Options: memory:// (development), redis:// (production), memcached:// (alternative)
RATELIMIT_STORAGE_URI=redis://localhost:6379/10

# Redis Configuration (Preferred for Production)
# -------------------------------------------------------------------
# Redis connection URL (takes precedence over individual settings)
REDIS_URL=redis://localhost:6379/10

# Redis storage options (JSON format for connection pool parameters)
# RATELIMIT_STORAGE_OPTIONS={"socket_connect_timeout": 5, "socket_timeout": 5, "client_name": "flask-limiter"}

# Redis Connection Pool Settings
# RATELIMIT_STORAGE_OPTIONS={"socket_connect_timeout": 5, "socket_timeout": 5, "retry_on_timeout": false, "health_check_interval": 0, "client_name": "flask-limiter"}

# Redis SSL/TLS Configuration (for secure connections)
# RATELIMIT_STORAGE_OPTIONS={"socket_connect_timeout": 5, "socket_timeout": 5, "ssl": true, "ssl_cert_reqs": "required"}

# Redis Cluster Configuration
# REDIS_STORAGE_URI=redis+cluster://localhost:7000,localhost:7001,localhost:7002
```

### Advanced Redis Configuration

For production environments, you can configure additional Redis options:

```bash
# Redis Connection Options (JSON format)
RATELIMIT_STORAGE_OPTIONS={
  "socket_connect_timeout": 5,
  "socket_timeout": 5,
  "retry_on_timeout": false,
  "health_check_interval": 0,
  "client_name": "flask-limiter",
  "max_connections": 50,
  "connection_pool_kwargs": {
    "socket_keepalive": true,
    "socket_keepalive_options": {}
  }
}

# Redis Authentication
REDIS_URL=redis://username:password@localhost:6379/10

# Redis with SSL
REDIS_URL=rediss://localhost:6379/10
RATELIMIT_STORAGE_OPTIONS={"ssl_cert_reqs": "required"}
```

## Storage Backends

### Memory Storage (Development)
```bash
RATELIMIT_STORAGE_URI=memory://
```
- Suitable for development and single-instance deployments
- Rate limit data is lost on application restart
- No external dependencies

### Redis (Production - Recommended)
```bash
RATELIMIT_STORAGE_URI=redis://localhost:6379/10
REDIS_URL=redis://localhost:6379/10
```
- Recommended for production environments
- Shared across multiple application instances
- Persistent storage with automatic expiration
- Requires Redis server to be installed and running
- Supports clustering for high availability

### Memcached (Production Alternative)
```bash
RATELIMIT_STORAGE_URI=memcached://localhost:11211
```
- Alternative to Redis for production
- Shared across multiple application instances
- Requires memcached server to be installed and running

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

## Logging

Rate limit violations are logged to:
- `logs/flask_limiter.log` - Dedicated Flask-Limiter log file (primary)
- `logs/rate_limit.log` - Application rate limit log file
- `logs/runtime_error.log` - Security monitoring  

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
   tail -f logs/flask_limiter.log
   ```

2. Monitor Redis usage:
   ```bash
   redis-cli info memory
   redis-cli info stats
   ```

3. View Flask-Limiter configuration:
   ```bash
   uv run python -c "from utils.rate_limiter import limiter; print(limiter.limiter.config)"
   ```

4. Check Redis connection:
   ```bash
   uv run python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=10); print('Redis connection:', r.ping())"
   ```

## Requirements

The following Python packages are required:
- `flask-limiter>=4.0.0`
- `redis>=7.0.0`

These are included in `requirements.txt`.

## Production Considerations

1. **Redis Server**: Ensure Redis server is properly configured for production use
2. **Persistence**: Configure Redis persistence to maintain rate limits across restarts if needed
3. **Memory Management**: Monitor Redis memory usage as rate limit data accumulates
4. **High Availability**: Consider Redis Sentinel or Cluster for high-availability setups
5. **Security**: Use Redis authentication and SSL/TLS in production environments
6. **Connection Pooling**: Configure appropriate connection pool sizes for your load
7. **Monitoring**: Set up monitoring for Redis performance and rate limit violations

## Troubleshooting

### Redis Connection Issues
If Redis is not being used:

1. Verify Redis is running:
   ```bash
   redis-cli ping
   ```

2. Check Redis connectivity:
   ```bash
   redis-cli -h localhost -p 6379 -n 10 ping
   ```

3. Verify configuration in `.env` file:
   ```bash
   # Required for Redis
   RATELIMIT_STORAGE_URI=redis://localhost:6379/10
   REDIS_URL=redis://localhost:6379/10
   ```

4. Check application logs for errors:
   ```bash
   tail -f logs/rate_limit.log
   tail -f logs/flask_limiter.log
   ```

5. Verify Flask-Limiter is using Redis:
   ```bash
   uv run python -c "from utils.rate_limiter import limiter; print('Storage type:', type(limiter.limiter.storage))"
   ```
   Look for "RedisStorage" in the output

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
   uv run python -c "from utils.rate_limiter import limiter; print(limiter.limiter.limits)"
   ```

3. Verify the limiter initialization order:
   - Rate limiting must be initialized before blueprints are registered
   - Check `app.py` to ensure `init_rate_limiting(app)` is called before blueprint registration

### Testing Rate Limits
To test if rate limits are working correctly:

1. Use a script to make multiple requests quickly:
   ```python
   import requests
   
   for i in range(10):
       response = requests.post('http://localhost:5001/login', data={'username': 'test', 'password': 'wrong'})
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
7. Application limits provide additional protection against sophisticated attacks

## Best Practices

1. **Always use specific decorators for sensitive endpoints**:
   - Authentication endpoints should use `@auth_rate_limit`
   - Upload endpoints should use `@upload_rate_limit`
   - API endpoints should use `@api_rate_limit`

2. **Test your rate limits**:
   - Verify custom limits override defaults
   - Test with both authenticated and anonymous requests
   - Check that Redis is being used in production

3. **Monitor rate limit violations**:
   - Set up alerts for repeated violations from the same IP
   - Review logs regularly for attack patterns
   - Consider auto-blocking IPs with excessive violations

4. **Configure appropriate limits**:
   - Authentication: 5-10 attempts per minute
   - Password reset: 3-5 attempts per 5-10 minutes
   - File uploads: 10-20 per minute
   - General API: 100-1000 per minute depending on usage

5. **Use Redis in production**:
   - Ensures rate limits persist across app restarts
   - Shared across multiple application instances
   - Better performance than memory storage
   - Supports distributed deployments

## Migration from Previous Versions

If you're migrating from an older version of Flask-Limiter or from Memcached:

1. **Update Dependencies**: Ensure you have Flask-Limiter 4.0+ and Redis 7.0+
2. **Update Configuration**: Replace deprecated variables:
   - `RATELIMIT_STORAGE_URL` → `RATELIMIT_STORAGE_URI`
   - `RATELIMIT_META_LIMITS` → `RATELIMIT_APPLICATION`
3. **Update Environment**: Use the new configuration format shown above
4. **Test Thoroughly**: Verify all rate limits work as expected after migration

For detailed migration instructions, see the migration guide in `docs/FLASK_LIMITER_MIGRATION_SUMMARY.md`.