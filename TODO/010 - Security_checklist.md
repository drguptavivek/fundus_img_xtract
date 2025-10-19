

Prevent
- Cross-Site Scripting (XSS)
- SQL injection attacks
- Path traversal attacks
- Secrets leakage

Use
- strict CSP headers
- NONCEs
- Track illegal 404 requests. - Source n Ip adn PAThs.
- Rate Limiting (applied to all non-login routes):
  - Email-related endpoints: 20 requests per minute
    - /email-sse (Server-Sent Events)
    - /check-email-status (Email status polling)
    - /check-session (Session validation)
  - Documentation endpoints: 20 requests per minute
    - /docs/ (Documentation index)
    - /docs/api.md (API documentation)
    - /docs/api.html (API documentation HTML)
    - /docs/openapi.yaml (OpenAPI specification)
    - /docs/swagger (Swagger UI)
    - /docs/swagger.json (Swagger JSON)
    - /help/ (Help documentation)
    - /help/<path:doc_path> (Help documentation paths)
- Server side valdiation of input
- Validate all client provided data before processing
- Disallow insecute HTTP methods
- Validate data from redirects
- Validate data length
- Validate data range


Auth
- Require authentication for all pages and resources, except those specifically intended to be public


Session management
- Use the server or framework’s session management controls. The application should recognize only these session identifiers as valid
- Session identifier creation must always be done on a trusted system (server side not client side)
- Set the domain and path for cookies containing authenticated session identifiers to an appropriately restricted value for the site
- 