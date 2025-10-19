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

# Rate limit storage backend
RATELIMIT_STORAGE_URL=memcached://

# Memcached server configuration
RATELIMIT_MEMCACHED_SERVERS=localhost:11211
# RATELIMIT_MEMCACHED_USERNAME=
# RATELIMIT_MEMCACHED_PASSWORD=

# Include rate limit headers in responses
RATELIMIT_HEADERS_ENABLED=true

# Swallow errors when storage backend is unavailable
RATELIMIT_SWALLOW_ERRORS=true
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

The application provides several decorators for applying rate limits:

### Basic Rate Limit
```python
from utils.rate_limiter import rate_limit

@app.route('/api/data')
@rate_limit("100 per hour")
def get_data():
    return jsonify(data)
```

### Authentication Endpoints
```python
from utils.rate_limiter import auth_rate_limit

@auth_bp.route('/login', methods=['POST'])
@auth_rate_limit("5 per minute")
def login():
    # Login logic
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

## User-Based Rate Limits

Rate limits can be customized based on user roles:

- **Admin**: 5000 per hour, 100 per minute (upload), 1000 per minute (API)
- **Data Manager/Ophthalmologist**: 2000 per hour, 50 per minute (upload), 500 per minute (API)
- **File Uploader/Optometrist**: 1000 per hour, 20 per minute (upload), 200 per minute (API)
- **Default**: 500 per hour, 10 per minute (upload), 100 per minute (API)

## Logging

Rate limit violations are logged to:
- `logs/rate_limit.log` - Dedicated rate limit log file
- `logs/runtime_error.log` - Security monitoring

Log entries include:
- Client IP address
- User information (if authenticated)
- Endpoint and path
- HTTP method
- Rate limit that was exceeded

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

3. Verify configuration in `.env` file

4. Check application logs for errors

5. Verify Flask-Limiter is using Memcached:
   ```bash
   uv run flask limiter config
   ```
   Look for "MemcachedStorage" in the output

### Rate Limit Not Working
If rate limiting appears not to work:

1. Verify `RATELIMIT_ENABLED=true` in `.env`
2. Check if the endpoint has a rate limit decorator
3. Verify the storage backend is properly configured
4. Check logs for any error messages

## Security Considerations

1. Rate limits are applied per IP address for anonymous users
2. Authenticated users have rate limits applied per user ID
3. Rate limit violations are logged for security monitoring
4. Consider implementing additional monitoring for repeated violations