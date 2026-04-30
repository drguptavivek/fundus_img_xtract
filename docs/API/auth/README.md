# Auth JSON Helpers

This folder documents the browser-facing helper routes in `auth/routes.py` that support the login, CAPTCHA, email-status, and session-ping flows.

## Index

- [Helpers](helpers.md)

## Contract Rules

- These routes are under `/auth`, not `/api`.
- The helper routes documented here are GET-only except for the session keepalive helper.
- No route in this folder expects a CSRF token because the documented endpoints are not HTML form submissions.
- HTML form routes such as `/auth/login`, `/auth/forgot-password`, and `/auth/reset-password` are outside this JSON/SSE helper contract.
