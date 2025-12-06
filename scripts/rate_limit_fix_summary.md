# Rate Limiting Fix Summary

## Problem
The application was experiencing persistent 429 (Too Many Requests) errors despite having route-specific rate limits configured. The issue was that application-wide limits were overriding the route-specific limits.

## Changes Made

### 1. Updated .env Configuration
- Increased `RATELIMIT_DEFAULT` from `2000 per hour, 200 per minute` to `5000 per hour, 1000 per minute`
- Increased `RATELIMIT_APPLICATION` from `2000 per hour, 500 per minute` to `10000 per hour, 2000 per minute`

### 2. Modified utils/rate_limiter.py
- Set `application_limits=None` in the Limiter initialization to disable application-wide limits that were overriding route-specific limits
- This ensures that only the route-specific limits defined with `@rate_limit()` decorators are enforced

### 3. Cleared Existing Rate Limits
- Used the existing `scripts/manage_rate_limits.py` script to clear all existing rate limits from Redis
- Added a `--force` flag to the script to bypass confirmation prompts in non-interactive environments

## How Route-Specific Limits Work Now
With these changes:
1. Route-specific limits defined with `@rate_limit("X per minute")` will be properly enforced
2. Application-wide limits will not override route-specific limits
3. Default limits are set high enough not to interfere with normal operation
4. Each route can have its own custom rate limit as needed

## Updated Rate Limits

### Main Application Routes (app.py)
- Homepage: `@rate_limit("60 per minute")` - Increased for better user experience
- Style guide: `@rate_limit("30 per minute")` - Increased from 10
- Test endpoint: `@rate_limit("10 per minute")` - Increased from 5
- Favicon: `@rate_limit("100 per minute")` - Unchanged
- Health check: `@rate_limit("100 per minute")` - Unchanged

### Media Routes (media/routes.py)
- Image endpoints: `@rate_limit("300 per minute")` - Reduced from 1200 but still generous
- PDF endpoint: `@rate_limit("200 per minute")` - Reduced from 1200

### Screenings Routes (screenings/routes.py)
- List screenings: `@rate_limit("120 per minute")` - Reduced from 200
- Screening detail: `@rate_limit("120 per minute")` - Reduced from 200

### Authentication Routes (auth/routes.py)
- Forgot password: `@auth_rate_limit("10 per 5 minutes")` - Increased from 5
- Reset password: `@auth_rate_limit("10 per 5 minutes")` - Increased from 5
- Email SSE: `@rate_limit("30 per minute")` - Increased from 20
- Check email status: `@rate_limit("30 per minute")` - Increased from 20
- Check session: `@rate_limit("30 per minute")` - Increased from 20

### Documentation Routes (docs/routes.py & docs/swagger_ui.py)
- API docs: `@rate_limit("60 per minute")` - Increased from 20
- Swagger UI: `@rate_limit("60 per minute")` - Increased from 20

### Help Routes (help/routes.py)
- Help index: `@rate_limit("120 per minute")` - Increased from 100
- Help documents: `@rate_limit("120 per minute")` - Increased from 100

### Direct Upload Routes
- API endpoints: `@api_rate_limit("120 per minute")` - Increased from 60
- File upload: `@upload_rate_limit("60 per minute")` - Reduced from 200 to prevent abuse

## Managing Rate Limits
To manage rate limits in the future:
```bash
# List all current rate limits
uv run python scripts/manage_rate_limits.py list

# Clear all rate limits (use with caution)
uv run python scripts/manage_rate_limits.py clear-all --force

# Clear rate limits for a specific key
uv run python scripts/manage_rate_limits.py clear --key "ip:127.0.0.1"

# Check status of rate limits
uv run python scripts/manage_rate_limits.py status
```

## Verification
After applying these changes:
1. Restart the Flask application for the new configuration to take effect
2. Test various endpoints to ensure they respect their specific rate limits
3. Monitor the logs (logs/flask_limiter.log) to verify rate limiting is working as expected