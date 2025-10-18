# CORS (Cross-Origin Resource Sharing) Configuration

## Overview

This document details the Cross-Origin Resource Sharing (CORS) configuration in the Fundus Image Manager application. CORS is a security mechanism that allows or restricts cross-origin requests from web browsers.

## Current Configuration

The application uses Flask-CORS v6.0.1 to handle cross-origin requests for API endpoints. The configuration is set up in `app.py` with the following settings:

### Configuration Code

```python
# Initialize CORS for API endpoints
# Allow credentials from same origin (localhost/127.0.0.1) to handle session cookies
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
        "supports_credentials": True
    }
}, supports_credentials=True)
```

### Configuration Details

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `resources` | `r"/api/*": {...}` | Restricts CORS to API endpoints only |
| `origins` | `["http://localhost:5000", "http://127.0.0.1:5000"]` | Allows requests from localhost development servers |
| `supports_credentials` | `True` | Enables cookies and authentication headers |
| `global supports_credentials` | `True` | Global setting for credential support |

## Security Considerations

### Current Security Posture

1. **Restricted Origins**: Only allows requests from localhost development servers
2. **API-Only Configuration**: CORS is restricted to `/api/*` endpoints
3. **Credential Support**: Enables session cookies for authenticated requests
4. **Same-Source Policy**: Maintains security by limiting origins

### Production Requirements

For production deployment, the origins list should be updated to include the production domain:

```python
# Production configuration example
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://yourdomain.com", "https://www.yourdomain.com"],
        "supports_credentials": True
    }
}, supports_credentials=True)
```

## Request Handling

### Preflight Requests

The application automatically handles CORS preflight requests (`OPTIONS` method) for:

- Complex requests with custom headers
- Requests with methods other than GET/HEAD/POST
- Requests with non-simple content types

### Response Headers

Flask-CORS automatically adds the following headers to responses:

```http
Access-Control-Allow-Origin: http://localhost:5000
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-CSRFToken
```

## Integration with Frontend

### Fetch API Example

```javascript
// CORS-enabled API request with credentials
fetch('/api/hospitals', {
    method: 'GET',
    credentials: 'include',  // Include cookies for authentication
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCSRFToken()  // CSRF protection
    }
})
.then(response => response.json())
.then(data => console.log(data));
```

### Session Management

The CORS configuration enables proper session cookie handling:

1. **Authentication**: Session cookies are sent with API requests
2. **CSRF Protection**: Cross-site request forgery tokens work with CORS
3. **Security**: Only configured origins can access authenticated endpoints

## Troubleshooting

### Common CORS Issues

1. **"CORS policy: No 'Access-Control-Allow-Origin' header"**
   - Check if the request is to an `/api/*` endpoint
   - Verify the origin is in the allowed origins list

2. **"Credentials is not true for preflight"**
   - Ensure `supports_credentials` is set to `True`
   - Check that the frontend request includes `credentials: 'include'`

3. **"Cannot use wildcard in Access-Control-Allow-Origin when credentials flag is true"**
   - Don't use `*` as origin when credentials are enabled
   - Specify exact origins instead

### Debugging CORS

Enable CORS debugging in development:

```python
# Add to app.py for debugging
app.config['CORS_SEND_WILDCARD'] = False
app.config['CORS_EXPOSE_HEADERS'] = ['Content-Type', 'X-CSRFToken']
```

## Adding More Allowed Origins

### Static Configuration

To add more allowed origins, you can simply extend the origins list in the CORS configuration:

```python
# Current configuration with additional origins
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "https://yourdomain.com",
            "https://www.yourdomain.com",
            "https://admin.yourdomain.com",
            "https://staging.yourdomain.com"
        ],
        "supports_credentials": True
    }
}, supports_credentials=True)
```

### Environment-Based Configuration

For better maintainability across different environments, use environment variables:

```python
import os
from flask import Flask
from flask_cors import CORS

def create_app():
    app = Flask(__name__)
    
    # Get origins from environment variable or use defaults
    allowed_origins = os.getenv("CORS_ORIGINS",
        "http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")
    
    # Apply CORS configuration
    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "supports_credentials": True,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-CSRFToken"]
        }
    })
    
    return app
```

#### Environment Variable Setup

Add to your `.env` file:

```bash
# Development
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

# Production (example)
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com,https://admin.yourdomain.com

# Staging
CORS_ORIGINS=https://staging.yourdomain.com,https://test.yourdomain.com
```

### Configuration File Approach

For more complex scenarios, use a configuration file:

```python
# config.py
class Config:
    CORS_ORIGINS = [
        "http://localhost:5000",
        "http://127.0.0.1:5000"
    ]

class DevelopmentConfig(Config):
    CORS_ORIGINS = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:3000"  # React development server
    ]

class ProductionConfig(Config):
    CORS_ORIGINS = [
        "https://yourdomain.com",
        "https://www.yourdomain.com",
        "https://admin.yourdomain.com"
    ]

class StagingConfig(Config):
    CORS_ORIGINS = [
        "https://staging.yourdomain.com",
        "https://test.yourdomain.com"
    ]

# app.py
from config import DevelopmentConfig, ProductionConfig, StagingConfig

def create_app(config_name='development'):
    app = Flask(__name__)
    
    # Load configuration
    config_class = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'staging': StagingConfig
    }.get(config_name, DevelopmentConfig)
    
    app.config.from_object(config_class)
    
    # Apply CORS configuration
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config['CORS_ORIGINS'],
            "supports_credentials": True
        }
    })
    
    return app
```

### Dynamic Origin Configuration

For dynamic origin validation based on database or custom logic:

```python
from flask import request
from flask_cors import CORS

def is_allowed_origin(origin):
    """Custom function to validate origins"""
    allowed_domains = [
        "yourdomain.com",
        "trusted-partner.com"
    ]
    
    # Check if origin matches allowed domains
    for domain in allowed_domains:
        if origin and (origin.endswith(domain) or origin == f"http://localhost:5000"):
            return True
    return False

# Dynamic CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": is_allowed_origin,  # Function instead of list
        "supports_credentials": True
    }
}, supports_credentials=True)
```

### Multi-Environment Configuration with JSON

For complex multi-environment setups, use JSON configuration:

```python
import json
import os

def load_cors_origins():
    """Load CORS origins from JSON configuration file"""
    config_file = os.getenv("CORS_CONFIG_FILE", "cors_config.json")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        environment = os.getenv("FLASK_ENV", "development")
        return config.get(environment, config.get("default", []))
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to default origins
        return ["http://localhost:5000", "http://127.0.0.1:5000"]

# In app.py
CORS(app, resources={
    r"/api/*": {
        "origins": load_cors_origins(),
        "supports_credentials": True
    }
})
```

#### Example JSON Configuration (cors_config.json)

```json
{
    "default": [
        "http://localhost:5000",
        "http://127.0.0.1:5000"
    ],
    "development": [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:3000",
        "http://localhost:8080"
    ],
    "staging": [
        "https://staging.yourdomain.com",
        "https://test.yourdomain.com",
        "https://partner-staging.com"
    ],
    "production": [
        "https://yourdomain.com",
        "https://www.yourdomain.com",
        "https://admin.yourdomain.com",
        "https://partner.yourdomain.com"
    ]
}
```

### Per-Endpoint CORS Configuration

For different origins for different API endpoints:

```python
from flask_cors import cross_origin

# Global CORS configuration
CORS(app, resources={
    r"/api/public/*": {
        "origins": "*",  # Public endpoints
        "supports_credentials": False
    },
    r"/api/auth/*": {
        "origins": ["https://yourdomain.com", "https://www.yourdomain.com"],
        "supports_credentials": True
    }
})

# Per-endpoint override
@app.route('/api/special-endpoint')
@cross_origin(origins=["https://special.yourdomain.com"], supports_credentials=True)
def special_endpoint():
    return jsonify({"message": "Special endpoint with custom CORS"})
```

### Validation and Testing

After adding new origins, validate the configuration:

```python
def test_cors_origins():
    """Test CORS configuration with different origins"""
    with app.test_client() as client:
        # Test allowed origin
        response = client.get('/api/hospitals', headers={
            'Origin': 'https://yourdomain.com'
        })
        assert response.headers.get('Access-Control-Allow-Origin') == 'https://yourdomain.com'
        
        # Test disallowed origin
        response = client.get('/api/hospitals', headers={
            'Origin': 'https://malicious.com'
        })
        assert 'Access-Control-Allow-Origin' not in response.headers
```

## Best Practices

### Security Recommendations

1. **Specific Origins**: Always specify exact origins, avoid wildcards
2. **API-Only Configuration**: Restrict CORS to specific endpoint patterns
3. **Environment-Based Configuration**: Use different origins for development/production
4. **Regular Review**: Periodically review allowed origins list
5. **Principle of Least Privilege**: Only add origins that absolutely need access
6. **HTTPS in Production**: Always use HTTPS URLs for production origins

### Implementation Patterns

```python
# Environment-based CORS configuration
import os
from flask import Flask
from flask_cors import CORS

def create_app():
    app = Flask(__name__)
    
    # Environment-specific origins
    if app.debug:
        allowed_origins = ["http://localhost:5000", "http://127.0.0.1:5000"]
    else:
        allowed_origins = [os.getenv("FRONTEND_URL", "https://yourdomain.com")]
    
    # Apply CORS configuration
    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "supports_credentials": True,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-CSRFToken"]
        }
    })
    
    return app
```

## Testing CORS

### Local Testing

1. Start the Flask application on localhost:5000
2. Test API endpoints from a frontend on localhost:5000
3. Verify preflight requests are handled correctly

### Cross-Origin Testing

For testing cross-origin requests:

```javascript
// Test from different origin (e.g., different port)
fetch('http://localhost:5000/api/hospitals', {
    method: 'GET',
    credentials: 'include'
})
.then(response => {
    if (response.ok) {
        console.log('CORS working correctly');
    } else {
        console.error('CORS error:', response.statusText);
    }
});
```

## Package Information

- **Package**: Flask-CORS v6.0.1
- **Dependencies**: flask, werkzeug
- **Documentation**: https://flask-cors.readthedocs.io/
- **Security Notes**: Regularly update to latest version for security patches

## Integration with Other Security Features

CORS works alongside other security measures:

1. **CSRF Protection**: CSRF tokens are validated even with CORS enabled
2. **Session Security**: Server-side sessions remain secure with CORS
3. **Rate Limiting**: CORS requests are subject to the same rate limits
4. **Authentication**: User authentication works seamlessly with CORS

## Monitoring and Logging

CORS-related events are logged through the standard Flask logging system:

```python
# CORS-related debug logging
app.logger.debug("CORS request from origin: %s", request.headers.get('Origin'))
app.logger.info("CORS preflight request for path: %s", request.path)
```

## Future Enhancements

Potential improvements to CORS configuration:

1. **Dynamic Origins**: Load origins from database or configuration file
2. **Per-Endpoint Configuration**: Different CORS settings for different endpoints
3. **Origin Validation**: Implement additional origin validation logic
4. **CORS Analytics**: Track cross-origin request patterns