# Authentication Utilities Documentation

This document provides an overview of the utility functions available in the authentication module. These utilities are designed to handle client IP address retrieval and time-related operations for authentication purposes.

## Utility Functions

### `utcnow()` -> datetime

Returns the current datetime in UTC timezone.

**Returns:**
- `datetime`: Current datetime object with UTC timezone information

**Usage:**
```python
from auth.utils import utcnow

current_time = utcnow()
# Returns a timezone-aware datetime object representing the current time in UTC
```

**Notes:**
- This function is preferred over `datetime.utcnow()` which is deprecated as of Python 3.12
- Returns timezone-aware datetime objects which is important for consistent time handling across the application

### `get_client_ip()` -> str

Retrieves the client's IP address from the request, prioritizing the X-Forwarded-For header when available.

**Returns:**
- `str`: Client's IP address, or "0.0.0.0" if no IP can be determined

**Implementation Details:**
- First checks the X-Forwarded-For header (commonly set by proxies/load balancers)
- If X-Forwarded-For is not available or empty, falls back to request.remote_addr
- If no IP address is available, defaults to "0.0.0.0"
- Strips whitespace and takes the first IP if multiple IPs are present in the header

**Usage:**
```python
from auth.utils import get_client_ip

client_ip = get_client_ip()
# Returns the client's IP address as determined by the function
```

**Security Considerations:**
- When the application is behind a proxy, this function correctly prioritizes the X-Forwarded-For header
- The function assumes that if using a proxy, the proxy properly sets the X-Forwarded-For header
- Flask should be configured to not trust arbitrary headers to prevent IP spoofing