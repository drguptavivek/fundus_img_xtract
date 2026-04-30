# Dataset API Surface

This folder documents the dataset share and download workflow.

## Page

- [Sharing and Download](sharing-download.md)

## Contract notes

- The browser share flow uses CSRF-protected forms.
- The download flow mixes HTML form posts with one JSON polling endpoint.
- Token, OTP, and file-name validation are enforced in code; invalid requests often return the `download_invalid.html` page with `404` or `429`.
