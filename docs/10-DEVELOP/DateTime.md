## DATE TIME
Date Time:
   - The application avoids legacy options like naive datetime storage
   - All datetime fields use the timezone-aware approach
   - The application correctly uses datetime.now(timezone.utc) instead of datetime.utcnow() (which is deprecated as of Python 3.12)
   - Resolves the appropriate timezone based on:
        - User's profile timezone setting (if user is logged in)
        - Application's DEFAULT_DISPLAY_TIMEZONE configuration
        - Fallback to DEFAULT_TIMEZONE if not configured
   - In app.py, the filter is registered as user_datetime, not format_user_datetime. 
   - Use user_datetime for display: {{ some_datetime_value | user_datetime }} or  {{ some_datetime_value | user_datetime("%B %d, %Y at %I:%M %p") }}