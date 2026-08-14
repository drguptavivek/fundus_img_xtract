# S3 Storage Setup Guide

This guide explains how to configure S3-compatible storage for your hospital's medical images.

## Overview

The system supports S3-compatible storage providers including:
- **AWS S3** - Amazon Web Services Simple Storage Service
- **Cloudflare R2** - Zero-egress S3-compatible storage
- **Hetzner** - Hetzner Object Storage
- **Google Cloud Storage** - S3-compatible API
- **Azure Blob Storage** - S3-compatible API
- **MinIO** - Self-hosted S3-compatible storage
- **Other** - Any S3-compatible service

## Prerequisites

Before configuring S3 storage, you need:

1. **S3-Compatible Account** - An account with your chosen provider
2. **S3 Bucket** - A bucket created in your account
3. **Access Credentials** - Access Key ID and Secret Access Key
4. **Admin Access** - Admin role in the application

## Configuration Steps

### Step 1: Navigate to S3 Configurations

1. Log in as an admin user
2. Navigate to **Admin** → **S3 Configurations**

### Step 2: Create New S3 Configuration

1. Click **Add New Configuration**
2. Fill in the required fields:

#### Basic Settings

| Field | Description | Example |
|-------|-------------|---------|
| **Hospital** | Select your hospital | Your Hospital Name |
| **Name** | Configuration name (unique per hospital) | Production S3 |
| **Provider** | S3-compatible provider | aws, r2, hetzner, gcp, azure, minio, other |
| **Bucket Name** | Your S3 bucket name | my-hospital-images |
| **Region** | Bucket region | us-east-1, auto, etc. |
| **Endpoint URL** | For non-AWS providers | https://...r2.cloudflarestorage.com |
| **S3 Base Folder** | Fixed global prefix (not editable) | /eyeimgmgr/ |
| **Addressing Style** | How to address the bucket | auto (recommended) |

#### Addressing Style Options

| Style | When to Use | Notes |
|-------|-------------|-------|
| **auto** | Most S3-compatible services | Let boto3 decide (default) |
| **virtual** | Cloudflare R2, custom endpoints | Uses `bucket.endpoint.com` format |
| **path** | Legacy MinIO, some custom services | Uses `endpoint.com/bucket` format |

#### Credentials

| Field | Description |
|-------|-------------|
| **Access Key ID** | Your S3 access key |
| **Secret Access Key** | Your S3 secret key (encrypted before storage) |

#### Auto-Rotation (Optional)

| Setting | Description |
|---------|-------------|
| **Enable Auto-Rotation** | Automatically rotate HMAC signing pepper |
| **Rotation Time** | Time of day to rotate (e.g., 02:00:00) |
| **Timezone** | Timezone for rotation (e.g., Asia/Kolkata) |

> **Note**: Manual pepper rotation is always available via the S3 config edit page.

#### Local-First Storage (Default)

All uploads are saved to local storage first. S3 sync is handled as a background process to ensure uploads are never lost if S3 is unavailable.

### Step 3: Test Connection

1. After filling in all fields, click **Test Connection**
2. The system will:
   - Verify credentials are correct
   - Check bucket access
   - List buckets (if supported by provider)
   - Display connection status

### Step 4: Save Configuration

1. If connection test passes, click **Save**
2. The configuration is saved but **not yet active**
3. Credentials are encrypted with your hospital's unique key

### Step 5: Activate Configuration

1. Click **Activate** on your new configuration
2. Only **one** configuration can be active per hospital
3. Once active, new uploads will use S3 storage

## File Storage Behavior

### S3 Path Mapping (Local → S3)

S3 keys mirror the local `/files/` path structure. The fixed global prefix `/eyeimgmgr/` is applied at upload/access time (not stored in the DB).

**Rule**: `S3 full key = eyeimgmgr/<local path relative to BASE_DIR>`

| Variant | Local Path | Stored `s3_object_key` | S3 Full Key |
|---|---|---|---|
| Direct upload original | `files/direct_uploads/<folder_rel>/<filename>` | `files/direct_uploads/<folder_rel>/<filename>` | `eyeimgmgr/files/direct_uploads/<folder_rel>/<filename>` |
| Direct upload edited | `files/direct_uploads/<folder_rel>/edited/<edited_filename>` | `files/direct_uploads/<folder_rel>/edited/<edited_filename>` | `eyeimgmgr/files/direct_uploads/<folder_rel>/edited/<edited_filename>` |
| Direct upload thumbnail (orig) | `files/direct_uploads/<folder_rel>/<thumbnail_filename>` | `files/direct_uploads/<folder_rel>/<thumbnail_filename>` | `eyeimgmgr/files/direct_uploads/<folder_rel>/<thumbnail_filename>` |
| Direct upload thumbnail (edited) | `files/direct_uploads/<folder_rel>/<edited_thumbnail_filename>` | `files/direct_uploads/<folder_rel>/<edited_thumbnail_filename>` | `eyeimgmgr/files/direct_uploads/<folder_rel>/<edited_thumbnail_filename>` |
| Encounter image | `files/zip_upload_images/<zip_folder_name>/<filename>` | `files/zip_upload_images/<zip_folder_name>/<filename>` | `eyeimgmgr/files/zip_upload_images/<zip_folder_name>/<filename>` |
| Encounter thumbnail | `files/zip_upload_images/<zip_folder_name>/<thumbnail_filename>` | `files/zip_upload_images/<zip_folder_name>/<thumbnail_filename>` | `eyeimgmgr/files/zip_upload_images/<zip_folder_name>/<thumbnail_filename>` |
| Encounter PDF | `files/zip_upload_pdfs/<zip_folder_name>/<filename>` | `files/zip_upload_pdfs/<zip_folder_name>/<filename>` | `eyeimgmgr/files/zip_upload_pdfs/<zip_folder_name>/<filename>` |

## Accessing S3 Files

### Via Application

Files stored in S3 are accessed through normal application URLs:
- Image viewing pages
- Direct image links
- Thumbnail previews

The application automatically:
1. Validates HMAC tokens for security
2. Generates presigned S3 URLs (time-limited)
3. Redirects the browser to download directly from S3

### Presigned URL TTL

Presigned URLs expire based on file size:

| File Size | URL Valid For |
|-----------|---------------|
| < 10 MB | 2 minutes |
| < 50 MB | 5 minutes |
| < 100 MB | 7.5 minutes |
| < 500 MB | 10 minutes |
| ≥ 500 MB | 15 minutes |

## Managing S3 Configurations

### Edit Configuration

1. Navigate to **Admin** → **S3 Configurations**
2. Click **Edit** on your configuration
3. Modify settings as needed
4. Click **Save Changes**

### Test Connection

Use **Test Connection** button to verify:
- Credentials are still valid
- Bucket is accessible
- No configuration issues

### Rotate HMAC Pepper

The HMAC signing pepper adds an extra layer of security to file URLs.

**Manual Rotation**:
1. Click **Rotate Pepper** on your configuration
2. Old pepper remains valid for 24 hours (grace period)
3. New URLs use the new pepper immediately

**Auto-Rotation** (if enabled):
- Runs at scheduled time daily
- Automatically generates new pepper
- Maintains 24-hour grace period

### Switch Active Configuration

To switch to a different S3 configuration:

1. Create the new configuration (if not exists)
2. Test the new configuration
3. Click **Activate** on the new configuration
4. The old configuration is automatically deactivated

> **Warning**: Only one configuration can be active per hospital. Activating a new config deactivates the current one.

### Archive Configuration

To remove an old configuration:

1. Click **Archive** on the configuration
2. Configuration is marked as archived
3. Archived configs don't appear in active lists
4. **No data is deleted** - this just hides the config

## Troubleshooting

### Connection Test Fails

**Error**: "Bucket not found"
- **Solution**: Verify bucket name matches exactly (case-sensitive)

**Error**: "Access denied"
- **Solution**: Check access key permissions (needs `s3:ListBucket` and `s3:PutObject`)

**Error**: "No such host"
- **Solution**: Verify endpoint URL is correct for your provider

### Files Not Uploading to S3

**Check**:
1. Configuration is **active** (not just saved)
2. Hospital ID matches the configuration
3. Check application logs for S3 upload errors; local fallback is automatic

### Addressing Style Issues

If files aren't uploading correctly:

1. Try **"auto"** addressing style first (works for most providers)
2. For **Cloudflare R2**: Use **"virtual"**
3. For **MinIO** (self-hosted): Try **"path"** if auto doesn't work
4. Check your provider's documentation for recommended style

## Security Features

### Hospital Isolation

- Each hospital's data is encrypted with a unique key
- Keys are derived from the master key using hospital ID
- Cross-hospital access is blocked at the application level

### HMAC URL Signing

- All media URLs include an HMAC token
- Tokens are hospital-specific (uses hospital's pepper)
- Tokens expire automatically (prevents link sharing)
- 24-hour grace period after pepper rotation

### Credential Encryption

- Access keys are encrypted before storage
- Encrypted with hospital-specific derived keys
- Master key never stored in the database
- Decryption keys cleared after each request

## Migration from Local Storage

If you have existing files stored locally:

1. Set up S3 configuration for your hospital
2. Contact your system administrator
3. Migration scripts can transfer existing files to S3
4. Files remain accessible during migration

## Support

For issues or questions:

1. Check this guide's troubleshooting section
2. Review the admin S3 configuration page for error messages
3. Contact your system administrator

## Quick Reference: Addressing Styles

```
┌─────────────────────────────────────────────────────────────────┐
│ Provider              │ Recommended Style │ Notes                │
├─────────────────────────────────────────────────────────────────┤
│ AWS S3                 │ auto              │ Default works best   │
│ Cloudflare R2          │ virtual           │ Requires vhost       │
│ MinIO                  │ auto or path      │ Try auto first      │
│ Hetzner                │ auto              │ Should work         │
│ Google Cloud Storage   │ auto              │ S3-compatible API   │
│ Azure Blob Storage     │ auto              │ S3-compatible API   │
│ Other (custom)         │ auto → virtual → path│ Try in order       │
└─────────────────────────────────────────────────────────────────┘
```
