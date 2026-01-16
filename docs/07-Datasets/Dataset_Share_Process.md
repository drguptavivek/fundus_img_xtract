# Dataset Share Process

This document describes the end-to-end process for sharing curated datasets.

## Overview

1. Create and screen a curated dataset.
2. Finalize the dataset (locks selections).
3. Create one or more shares (token + OTP).
4. Share the link and OTP via separate channels.
5. Recipient verifies and generates an export for download.

## Detailed flow

### 1) Dataset creation and screening
- Create a curated dataset from analytics.
- Perform manual or auto screening and confirm selections.
- Finalize the dataset to lock selections. Finalization is required for export and sharing.

### 2) Share creation
- Open the dataset shares page and create a share.
- The system generates:
  - A share token (link).
  - An OTP (case-insensitive, time-bound).
- The download link is emailed to the recipient (no OTP in email).
- The OTP is emailed to the share creator (CC main admin).

### 3) Share management
- Multiple shares can be active at the same time.
- Shares can be activated or deactivated from the share list.
- Regenerating an OTP invalidates the previous OTP for that share.

### 4) Download and export
- Recipient opens the link and enters dataset name + OTP.
- On successful verification:
  - The system shows dataset details (disease, image count, share time).
  - The user can generate an export if not already ready.
- Exports are available for 20 hours and can be regenerated when needed.

## Roles
- Share creation and management: `dataset_creator`, `admin`.
- Dataset list visibility: same as dataset curation list roles.

## Security and audit
- Download routes are rate limited and lock out abusive attempts.
- All share creation, regeneration, activation, and downloads are logged.
