 # Security Block Logic in app.py and auth system:

## 1. Authentication and Authorization:
- **Global authentication guard**: The `_require_login_everywhere()` function in app.py requires authentication for all routes except:
  - `/` (homepage)
  - `/login`
  - `/static/` files
  - `/favicon.ico`
  - `/style_guide`
- **Flask-Login**: Used for user session management with proper user loader
- **CSRF Protection**: Enabled via Flask-WTF with a 1-hour time limit

## 2. Login Security Features:
- **Rate limiting**: 
  - Max 5 failed attempts per username in 30 minutes
  - Max 5 failed attempts per IP in 10 minutes
- **Account locking**: 
  - User accounts locked for 4 hours after repeated failures
  - IPs locked for 4 hours after repeated failures
- **Password security**: 
  - Argon2id hashing with pepper
  - Strong password requirements (min 10 chars, uppercase, lowercase, special chars)
  - Protection against common weak patterns

## 3. Session Security:
- **Inactivity timeout**: Configurable sliding window (default 30 minutes)
- **Secure cookies**: HTTPOnly, SameSite, and Secure flags (configurable)
- **Session refresh**: Cookie refreshed on each request

## 4. 404 Error Handling:
- **Custom 404 page**: Template at `templates/errors/404.html` that extends `error.html`
- **Error logging**: 404 errors are logged to the HTTP error log
- **User-friendly error page**: Shows error code, title, and message with navigation options

## 5. Additional Security Measures:
- **Audit logging**: Login attempts are recorded in the `login_attempts` table
- **IP locking**: Failed attempts trigger IP-based locks
- **User locking**: Repeated failures lock user accounts
- **Password policy**: Enforced strong password requirements
- **Input validation**: Username and password validation with regex patterns

## 6. Error Handling:
- **Custom error pages**: Specific templates for 404, 405, 500, 501 errors
- **Fallback error handler**: Generic handler for other HTTP exceptions
- **Logging**: Separate logging for successful requests and errors
- **Security error handling**: CSRF errors show user-friendly messages

## 7. Logging System:
- **Comprehensive logging**: Detailed documentation available in [Logging.md](Logging.md)
- **HTTP request logging**: All requests logged with IP, method, URL, status, and duration
- **Authentication logging**: Login attempts stored in database for audit purposes
- **Security event logging**: Account locks, IP blocks, and other security events tracked
- **Log rotation**: Automatic log file rotation to prevent excessive disk usage

## 8. Grading System Access Controls:
- **Role-based access**: Detailed documentation available in [Grading.md](Grading.md)
- **Granular permissions**: Different roles have access to different grading features
- **LabUnit restrictions**: Ophthalmologists can only access images from their own facilities
- **Masked grading**: Patient information hidden during grading to prevent bias
- **Audit trails**: All grading activities logged for compliance and quality assurance

The security implementation is quite comprehensive, with proper authentication, rate limiting, account locking, and error handling. The 404 errors are handled gracefully with custom error pages that maintain the site's styling while providing helpful navigation options back to valid pages. For detailed information about the logging system, see [Logging.md](Logging.md). For information about grading system access controls, see [Grading.md](Grading.md).