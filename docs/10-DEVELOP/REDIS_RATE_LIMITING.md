# Redis Rate Limiting Configuration

This document explains how Flask-Limiter is configured to use Redis for rate limiting in the Fundus Image Manager application.

## Overview

The application uses Flask-Limiter with Redis as the storage backend for distributed rate limiting. This ensures rate limits are enforced consistently across multiple application instances.

## Configuration

### Environment Variables

The following environment variables can be used to configure Redis for rate limiting:

#### Basic Configuration
- `REDIS_URL` or `RATELIMIT_REDIS_URL`: Full Redis connection URL (e.g., `redis://localhost:6379/0`)
- `RATELIMIT_REDIS_HOST`: Redis server host (default: `localhost`)
- `RATELIMIT_REDIS_PORT`: Redis server port (default: `6379`)
- `RATELIMIT_REDIS_DB`: Redis database number (default: `0`)

#### Authentication
- `RATELIMIT_REDIS_USERNAME`: Redis username (optional)
- `RATELIMIT_REDIS_PASSWORD`: Redis password (optional)

#### SSL/TLS Configuration
- `RATELIMIT_REDIS_SSL`: Enable SSL/TLS (default: `false`)
- `RATELIMIT_REDIS_SSL_CERT_REQS`: SSL certificate requirements (default: `required`)

#### Connection Pool Settings
- `RATELIMIT_REDIS_SOCKET_TIMEOUT`: Socket timeout in seconds (default: `5`)
- `RATELIMIT_REDIS_SOCKET_CONNECT_TIMEOUT`: Connection timeout in seconds (default: `5`)
- `RATELIMIT_REDIS_RETRY_ON_TIMEOUT`: Retry on timeout (default: `false`)
- `RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL`: Health check interval in seconds (default: `0`)
- `RATELIMIT_REDIS_CLIENT_NAME`: Client name for Redis (default: `flask-limiter`)
- `RATELIMIT_REDIS_CONNECTION_POOL_KWARGS`: Additional connection pool options as JSON string

### Example Configuration

```bash
# Basic Redis configuration
REDIS_URL=redis://localhost:6379/0

# Or using individual components
RATELIMIT_REDIS_HOST=localhost
RATELIMIT_REDIS_PORT=6379
RATELIMIT_REDIS_DB=0

# With authentication
RATELIMIT_REDIS_USERNAME=myuser
RATELIMIT_REDIS_PASSWORD=mypassword

# With SSL
RATELIMIT_REDIS_SSL=true
RATELIMIT_REDIS_SSL_CERT_REQS=required

# Custom connection settings
RATELIMIT_REDIS_SOCKET_TIMEOUT=10
RATELIMIT_REDIS_RETRY_ON_TIMEOUT=true
RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL=30
```

## Implementation Details

### Storage Backend

The application uses `RedisStorage` from Flask-Limiter, which provides:
- Distributed rate limiting across multiple application instances
- Persistent storage of rate limit counters
- Automatic expiration of rate limit entries
- Support for Redis clustering (when configured)

### Connection Management

The Redis connection is configured with:
- Connection pooling for efficient resource usage
- Configurable timeouts and retry logic
- Health checks for connection monitoring
- SSL/TLS support for secure connections

### Rate Limit Strategy

The application uses a fixed-window strategy by default, which:
- Resets rate limits at fixed intervals (e.g., every minute)
- Provides predictable behavior
- Works well with Redis's atomic operations

## Monitoring and Debugging

### Log Files

Rate limit violations are logged to:
- `logs/flask_limiter.log` - Flask-Limiter specific logs
- `logs/rate_limit.log` - Application rate limit logs

### Status Check

To check the current rate limiter status:

```bash
uv run scripts/manage_rate_limits.py status
```

### Testing

To test rate limiting functionality:

```bash
uv run scripts/test_rate_limiter_standalone.py
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

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check if Redis server is running and accessible
2. **Authentication Failed**: Verify Redis credentials
3. **SSL Errors**: Ensure SSL configuration is correct on both client and server
4. **Timeout Issues**: Increase timeout values or check network connectivity

### Debug Commands

```bash
# Check Redis connection
uv run python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=0); print('Redis connection:', r.ping())"

# Check rate limiter storage type
uv run scripts/manage_rate_limits.py status

# View rate limit logs
tail -f logs/flask_limiter.log
tail -f logs/rate_limit.log