# Scoping APIs

These endpoints expose the current user’s hospital context and operation-scoping metadata.

## Index

- [Hospital Context](hospital-context.md)
- [Operation](operation.md)

## Contract Rules

- The routes are JSON GET endpoints.
- They use Flask-Login session auth.
- No CSRF token is required because there are no mutating requests in this surface.
