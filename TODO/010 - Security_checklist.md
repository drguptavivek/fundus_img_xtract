

Prevent
- Cross-Site Scripting (XSS)
- SQL injection attacks
- Path traversal attacks
- Secrets leakage

Use
- strict CSP headers
- NONCEs
- Track illegal 404 requests. - Source n Ip adn PAThs. 
- Rate Limiting
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