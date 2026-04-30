# Email Settings

This page documents the admin email configuration surface.

## Routes

- `GET /admin/email-settings`
- `GET /admin/email-settings/new`
- `POST /admin/email-settings/new`
- `GET /admin/email-settings/<int:settings_id>/edit`
- `POST /admin/email-settings/<int:settings_id>/edit`
- `GET /admin/email-settings/<int:settings_id>/test`
- `POST /admin/email-settings/<int:settings_id>/delete`
- `POST /admin/email-settings/<int:settings_id>/activate`
- `GET /admin/api/email-settings/test-current`
- `POST /admin/api/email-settings/send-sample`

## `GET /admin/email-settings`

HTML list page.

Auth:
- `@roles_required("admin")`

Response:
- `200 OK` HTML rendered from `templates/admin/email_settings.html`

Data passed to the template:
- `email_settings`
- `current_config`
- `config_source`

## `GET/POST /admin/email-settings/new`

Auth:
- `@roles_required("admin")`

CSRF:
- Required on `POST` via `{{ csrf_field() }}`

POST form fields:
- `smtp_server`
- `smtp_port`
- `smtp_username`
- `smtp_password`
- `from_email`
- `use_tls` checkbox (`on`)
- `use_ssl` checkbox (`on`)
- `debug_logging` checkbox (`on`)
- `connection_timeout`

Validation rules:
- `smtp_server`, `smtp_username`, `smtp_password`, and `from_email` are required
- `from_email` must contain `@`
- `smtp_port` must be `1..65535`
- `use_tls` and `use_ssl` cannot both be enabled
- `connection_timeout` must be `1..300`

Success:
- Redirects to `/admin/email-settings`

Failure:
- Re-renders the create template with flash messages or validation errors

## `GET/POST /admin/email-settings/<settings_id>/edit`

Same form fields and validation as create, plus:
- `is_active` checkbox

Behavior:
- Activating a config deactivates the current active config
- Password is still required in the form body

Success:
- Redirects to `/admin/email-settings`

## `GET /admin/email-settings/<settings_id>/test`

Tests one stored config.

Auth:
- `@roles_required("admin")`

Response `200`:
```json
{ "success": true, "message": "..." }
```

Known errors:
- `404 {"success": false, "message": "Email settings not found"}`
- `400 {"success": false, "message": "Configuration error: ..."}`
- `500 {"success": false, "message": "Test failed due to an internal error. Please check the logs."}`

## `POST /admin/email-settings/<settings_id>/delete`

CSRF:
- Required

Behavior:
- Refuses to delete the active config
- Redirects back to the list with flash messages

## `POST /admin/email-settings/<settings_id>/activate`

CSRF:
- Required

Behavior:
- Deactivates any existing active config, then activates the chosen row
- Redirects back to the list with flash messages

## `GET /admin/api/email-settings/test-current`

Tests the current active configuration.

Auth:
- `@roles_required("admin")`

Response `200`:
```json
{ "success": true, "message": "..." }
```

## `POST /admin/api/email-settings/send-sample`

Sends a test email through the current active config.

Auth:
- `@roles_required("admin")`

CSRF:
- Required. The page JS includes the token when it submits the sample-email form.

Request body fields:
- `recipient_email`
- `subject` optional
- `message` optional

Success `200`:
```json
{
  "success": true,
  "message": "Sample email sent successfully to test@example.com. Please check your inbox."
}
```

Validation errors:
- `400 {"success": false, "message": "Recipient email address is required."}`
- `400 {"success": false, "message": "Invalid recipient email address format."}`
- `400 {"success": false, "message": "No email configuration found. Please create and activate email settings first."}`

Failure:
- `500 {"success": false, "message": "Failed to send email. Please check the logs."}`

## CSRF Rules

- All create/edit/delete/activate/sample-email POSTs require CSRF.
- The template uses hidden `csrf_token` fields and JS reads them before calling `fetch()`.
