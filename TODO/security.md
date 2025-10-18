# OWASP Top 10 Security Implementation Guide

## Overview
This document outlines the OWASP Top 10 2021/2023 security vulnerabilities and provides specific implementation recommendations for the Fundus Image Management Flask application.

## 1. Broken Access Control (A01:2021)

### Current Implementation
- Role-Based Access Control (RBAC) implemented via [`auth/routes.py`](auth/routes.py:38)
- Flask-Login for authentication
- Server-side session management via [`server_side_session.py`](server_side_session.py:26)
- IP and username-based lockout mechanisms

### Recommended Protections

#### 1.1 Authorization Verification
```python
# Add this decorator to sensitive routes
@auth_bp.route("/sensitive-endpoint")
@login_required
@roles_required('admin', 'data_manager')
def sensitive_operation():
    # Your code here
    pass
```

#### 1.2 Resource-Based Access Control
```python
# Verify resource ownership before access
def verify_user_access(user_id, resource_id):
    with Session() as db:
        resource = db.get(ResourceModel, resource_id)
        if not resource or resource.user_id != user_id:
            abort(403)
```

#### 1.3 Secure Direct Object References
```python
# Add UUID-based resource access validation
@bp.route("/images/<string:uuid>")
@login_required
def get_image(uuid):
    image = db.query(DirectImageUpload).filter_by(uuid=uuid).first()
    if not image or not verify_user_lab_access(current_user.id, image.lab_unit_id):
        abort(404)  # Use 404 to prevent enumeration
```

## 2. Cryptographic Failures (A02:2021)

### Current Implementation
- Argon2id password hashing via [`auth/security.py`](auth/security.py:22)
- Optional pepper for password hashing
- TLS configuration for session cookies

### Recommended Protections

#### 2.1 Encryption at Rest
```python
# Add file encryption for sensitive uploads
from cryptography.fernet import Fernet

def encrypt_sensitive_file(file_path, key):
    f = Fernet(key)
    with open(file_path, 'rb') as file:
        file_data = file.read()
    encrypted_data = f.encrypt(file_data)
    with open(file_path, 'wb') as file:
        file.write(encrypted_data)
```

#### 2.2 Key Management
```python
# Store encryption keys securely
def get_encryption_key():
    key = os.getenv("FILE_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("Encryption key not configured")
    return key.encode()
```

#### 2.3 Secure Configuration
```python
# Add to .env
FILE_ENCRYPTION_KEY=your-32-byte-base64-key
SESSION_ENCRYPTION_KEY=your-session-encryption-key
```

## 3. Injection (A03:2021)

### Current Implementation
- SQLAlchemy ORM for database queries
- Parameterized queries in most places
- Input validation in [`auth/security.py`](auth/security.py:36)

### Recommended Protections

#### 3.1 SQL Injection Prevention
```python
# Always use parameterized queries
def get_user_grades(user_id, date_range):
    with Session() as db:
        return db.execute(
            select(ImageGrading)
            .where(ImageGrading.grader_user_id == user_id)
            .where(ImageGrading.created_at >= date_range.start)
            .where(ImageGrading.created_at <= date_range.end)
        ).scalars().all()
```

#### 3.2 Input Validation
```python
# Add comprehensive input validation
from marshmallow import Schema, fields, validate

class ImageUploadSchema(Schema):
    hospital_id = fields.Integer(required=True, validate=validate.Range(min=1))
    lab_unit_id = fields.Integer(required=True, validate=validate.Range(min=1))
    files = fields.Field(required=True, validate=validate.Length(min=1, max=100))
```

#### 3.3 Output Encoding
```python
# Always encode output in templates
{{ user_input | e }}  # Jinja2 auto-escaping (enabled by default)
```

## 4. Insecure Design (A04:2021)

### Current Implementation
- Basic RBAC system
- Logging system
- Error handling

### Recommended Protections

#### 4.1 Secure Workflow Design
```python
# Add multi-step approval for sensitive operations
@bp.route("/delete-patient-data/<int:patient_id>", methods=["POST"])
@login_required
@roles_required('admin', 'data_manager')
def delete_patient_data(patient_id):
    # Require confirmation and logging
    if not session.get(f'confirm_delete_{patient_id}'):
        flash("Please confirm this destructive action", "warning")
        return redirect(url_for('admin.confirm_delete', patient_id=patient_id))
    
    log_security_event(f"Patient data delete by {current_user.username}", patient_id)
    # Proceed with deletion
```

#### 4.2 Rate Limiting
```python
# Add rate limiting to sensitive endpoints
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route("/api/v1/upload", methods=["POST"])
@limiter.limit("10 per minute")
@login_required
def upload_api():
    # Your upload logic
    pass
```

## 5. Security Misconfiguration (A05:2021)

### Current Implementation
- Environment-based configuration
- CSRF protection enabled
- Security headers partially implemented

### Recommended Protections

#### 5.1 Security Headers
```python
# Add security headers middleware
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = \
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
    return response
```

#### 5.2 Secure Configuration
```python
# Add to app.py configuration
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only in production
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
```

#### 5.3 Error Handling
```python
# Don't expose sensitive information in error messages
@app.errorhandler(500)
def handle_500(e):
    app.logger.exception("Internal server error")
    return render_template("errors/500.html"), 500
```

## 6. Vulnerable and Outdated Components (A06:2021)

### Current Implementation
- Dependency management via requirements.txt.lock
- Regular updates

### Recommended Protections

#### 6.1 Dependency Scanning
```bash
# Add to CI/CD pipeline
pip install safety
safety check --json --output safety-report.json
pip-audit --requirement requirements.txt.lock --output-format json
```

#### 6.2 Automated Updates
```yaml
# .github/workflows/security.yml
name: Security Scan
on:
  schedule:
    - cron: '0 2 * * 1'  # Weekly on Monday
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run safety check
        run: |
          pip install safety
          safety check
```

## 7. Identification and Authentication Failures (A07:2021)

### Current Implementation
- Flask-Login for authentication
- Password complexity requirements
- Session management

### Recommended Protections

#### 7.1 Multi-Factor Authentication
```python
# Add TOTP support
import pyotp

def enable_totp(user):
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_secret(secret)
    db.commit()
    return secret

def verify_totp(user, token):
    secret = decrypt_secret(user.totp_secret)
    return pyotp.TOTP(secret).verify(token)
```

#### 7.2 Password Policy Enhancement
```python
# Update password policy in auth/security.py
def check_password_strength(pw: str, min_len: int = 12) -> tuple[bool, str]:
    # Increased minimum length
    # Check against compromised passwords API
    if is_password_compromised(pw):
        return False, "This password has been compromised in data breaches"
    # Additional checks...
```

#### 7.3 Session Security
```python
# Add session fixation protection
@app.before_request
def regenerate_session():
    if session.permanent and not session.get('_session_regenerated'):
        session.regenerate()
        session['_session_regenerated'] = True
```

## 8. Software and Data Integrity Failures (A08:2021)

### Current Implementation
- File upload validation
- Basic integrity checks

### Recommended Protections

#### 8.1 File Upload Security
```python
# Add file signature verification
def verify_file_signature(file_content, allowed_signatures):
    # Check file magic bytes
    file_signature = file_content[:8]
    for allowed in allowed_signatures:
        if file_signature.startswith(bytes.fromhex(allowed)):
            return True
    return False

# In upload.py
allowed_signatures = {
    'jpeg': 'ffd8ffe0',
    'png': '89504e47'
}
```

#### 8.2 Digital Signatures
```python
# Add digital signatures for sensitive data
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def sign_data(data, private_key):
    signature = private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return signature
```

## 9. Security Logging and Monitoring Failures (A09:2021)

### Current Implementation
- Basic logging in [`app.py`](app.py:112)
- Auth logging in [`auth/routes.py`](auth/routes.py:19)

### Recommended Protections

#### 9.1 Comprehensive Security Logging
```python
# Add security event logging
def log_security_event(event_type, user_id, details=None, ip=None):
    security_logger = logging.getLogger("security")
    security_logger.info(
        "Security Event - Type: %s, User: %s, IP: %s, Details: %s",
        event_type, user_id, ip or get_client_ip(), details or ""
    )

# Usage examples
log_security_event("LOGIN_FAILED", None, f"Username: {username}", ip)
log_security_event("PRIVILEGE_ESCALATION", current_user.id, "Role: admin assigned")
```

#### 9.2 Intrusion Detection
```python
# Add anomaly detection
def detect_suspicious_activity(user_id, action):
    from collections import defaultdict
    import time
    
    # Track recent activities
    if not hasattr(detect_suspicious_activity, 'activity_log'):
        detect_suspicious_activity.activity_log = defaultdict(list)
    
    now = time.time()
    detect_suspicious_activity.activity_log[user_id].append((action, now))
    
    # Clean old entries (older than 1 hour)
    detect_suspicious_activity.activity_log[user_id] = [
        (a, t) for a, t in detect_suspicious_activity.activity_log[user_id] 
        if now - t < 3600
    ]
    
    # Check for suspicious patterns
    recent_actions = [a for a, t in detect_suspicious_activity.activity_log[user_id]]
    if recent_actions.count("FILE_DOWNLOAD") > 100:
        log_security_event("SUSPICIOUS_ACTIVITY", user_id, "Excessive file downloads")
```

## 10. Server-Side Request Forgery (SSRF) (A10:2021)

### Current Implementation
- Limited external requests
- Basic URL validation

### Recommended Protections

#### 10.1 URL Validation
```python
# Add SSRF protection
from urllib.parse import urlparse

def is_safe_url(url):
    parsed = urlparse(url)
    
    # Block private IP ranges
    if parsed.hostname:
        import ipaddress
        try:
            ip = ipaddress.ip_address(parsed.hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass
    
    # Allow only specific schemes
    if parsed.scheme not in ['http', 'https']:
        return False
    
    # Block localhost references
    if 'localhost' in (parsed.hostname or ''):
        return False
    
    return True
```

#### 10.2 Whitelist Approach
```python
# Use whitelisting for external services
ALLOWED_SERVICES = {
    'api.example.com': 'https://api.example.com',
    'cdn.example.com': 'https://cdn.example.com'
}

def fetch_external_resource(resource_url):
    parsed = urlparse(resource_url)
    if parsed.netloc not in ALLOWED_SERVICES:
        raise ValueError("External service not allowed")
    
    # Proceed with request
    return requests.get(resource_url)
```

## Implementation Priority

### High Priority (Immediate)
1. Add security headers middleware
2. Implement comprehensive security logging
3. Add rate limiting to sensitive endpoints
4. Enhance password policy

### Medium Priority (Next Sprint)
1. Implement multi-factor authentication
2. Add file signature verification
3. Create automated dependency scanning
4. Enhance session security

### Low Priority (Future Releases)
1. Implement digital signatures
2. Add intrusion detection
3. Create comprehensive audit trails
4. Implement advanced SSRF protections

## Testing

### Security Testing Checklist
- [ ] Penetration testing by third party
- [ ] Automated security scanning in CI/CD
- [ ] Dependency vulnerability scanning
- [ ] OWASP ZAP or Burp Suite testing
- [ ] Manual code review for security flaws

### Monitoring
- [ ] Set up security alerting
- [ ] Monitor failed login attempts
- [ ] Track unusual data access patterns
- [ ] Regular security log reviews

## References
- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/2.2.x/security/)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)