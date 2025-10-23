# Redis Rate Limiting Configuration

> **⚠️ Documentation Moved**
> 
> This documentation has been consolidated and updated. Please refer to the main rate limiting documentation:
> 
> **📖 [Rate Limiting Configuration](../01-SETUP/rate_limiting.md)**

## Overview

This document previously explained how Flask-Limiter is configured to use Redis for rate limiting in the Fundus Image Manager application.

## Current Status

All Redis rate limiting configuration has been integrated into the main rate limiting documentation and updated for Flask-Limiter 4.0+ compatibility.

## Updated Documentation Location

The complete and current Redis rate limiting configuration is now available in:

- **[Rate Limiting Configuration](../01-SETUP/rate_limiting.md)** - Complete setup guide
- **[Redis Storage Configuration](../01-SETUP/rate_limiting.md#redis-storage-configuration)** - Redis-specific settings
- **[Advanced Redis Configuration](../01-SETUP/rate_limiting.md#advanced-redis-configuration)** - Production-ready settings
- **[Production Considerations](../01-SETUP/rate_limiting.md#production-considerations)** - Deployment guidelines

## Key Features Now Documented

### Flask-Limiter 4.0+ Configuration
- Updated configuration variables (`RATELIMIT_STORAGE_URI`, `RATELIMIT_APPLICATION`)
- Removed deprecated variables (`RATELIMIT_STORAGE_URL`, `RATELIMIT_META_LIMITS`)
- Enhanced Redis connection pooling and SSL support

### Redis Configuration Examples
```bash
# Basic Redis configuration
RATELIMIT_STORAGE_URI=redis://localhost:6379/10
REDIS_URL=redis://localhost:6379/10

# Advanced configuration with connection pooling
RATELIMIT_STORAGE_OPTIONS={
  "socket_connect_timeout": 5,
  "socket_timeout": 5,
  "retry_on_timeout": false,
  "health_check_interval": 0,
  "client_name": "flask-limiter"
}

# Redis with SSL/TLS
REDIS_URL=rediss://localhost:6379/10
RATELIMIT_STORAGE_OPTIONS={"ssl_cert_reqs": "required"}
```

### Production Deployment
- Redis server configuration
- Connection pooling optimization
- High availability with Redis Cluster/Sentinel
- Security with authentication and SSL/TLS
- Memory management and monitoring

### Monitoring and Troubleshooting
- Redis connection testing
- Performance monitoring
- Log analysis
- Common issues and solutions

## Quick Reference

### Basic Setup
```bash
# .env configuration
RATELIMIT_ENABLED=true
RATELIMIT_STORAGE_URI=redis://localhost:6379/10
REDIS_URL=redis://localhost:6379/10
```

### Verification Commands
```bash
# Test Redis connection
uv run python -c "import redis; r = redis.Redis(host='localhost', port=6379, db=10); print('Redis connection:', r.ping())"

# Check Flask-Limiter configuration
uv run python -c "from utils.rate_limiter import limiter; print('Storage type:', type(limiter.limiter.storage))"

# Monitor Redis usage
redis-cli info memory
redis-cli info stats
```

### Requirements
- `flask-limiter>=4.0.0`
- `redis>=7.0.0`

## Migration Information

If you're migrating from older versions or different backends:

1. **Update Dependencies**: Ensure Flask-Limiter 4.0+ and Redis 7.0+
2. **Update Configuration**: Use new variable names
3. **Test Thoroughly**: Verify functionality after migration

See the main documentation for detailed migration instructions.

---

**Last Updated**: This document is preserved for historical reference. All current Redis rate limiting information is maintained in the main rate limiting documentation with Flask-Limiter 4.0+ compatibility.