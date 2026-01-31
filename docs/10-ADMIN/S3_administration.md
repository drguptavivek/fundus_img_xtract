# S3 Administration

## Overview

Administering S3 storage configurations for hospitals. This guide covers creating, managing, and monitoring S3 configurations through the admin interface.

## S3 Configuration Management

### Creating a New S3 Configuration

**Route:** `GET /admin/s3-configs/create`

**Required Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| Hospital | Select hospital (scoping) | City Eye Hospital |
| Name | Display name | Production R2 Bucket |
| Provider | S3 provider | r2, aws, hetzner, minio, other |
| Bucket Name | S3 bucket name | `fundus-images-prod` |
| Region | AWS region or equivalent | `auto`, `us-east-1`, `eu-central-1` |
| Endpoint URL | Custom endpoint (non-AWS) | `https://<account>.r2.cloudflarestorage.com` |
| Access Key | S3 access key | `AKIAIOSFODNN7EXAMPLE` |
| Secret Key | S3 secret key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| Addressing Style | How to address bucket | `virtual`, `path`, or `auto` |

**Optional Fields:**

| Field | Description | Default |
|-------|-------------|---------|
| Rotation Enabled | Enable credential rotation | `False` |
| Rotate After Days | Days between rotations | `90` |
| Cleanup Local After Upload | Delete local files after S3 upload | `False` |

### Addressing Styles

| Style | URL Format | Use Case |
|-------|-----------|----------|
| `virtual` | `https://bucket.endpoint.com/key` | AWS S3, R2 (default) |
| `path` | `https://endpoint.com/bucket/key` | MinIO, some custom S3 |
| `auto` | Let boto3 decide | Recommended for most cases |

### Provider-Specific Configuration

#### Cloudflare R2

```
Provider: r2
Endpoint URL: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
Region: auto (or leave blank)
Addressing Style: virtual
```

#### AWS S3

```
Provider: aws
Endpoint URL: (leave blank for AWS)
Region: us-east-1 (or your region)
Addressing Style: auto (or virtual)
```

#### MinIO (Self-hosted)

```
Provider: minio
Endpoint URL: http://localhost:9000
Region: us-east-1
Addressing Style: path
```

#### Hetzner Storage Box

```
Provider: hetzner
Endpoint URL: https://<your-project>.your-objectstorage.com
Region: <provided by Hetzner>
Addressing Style: virtual
```

## Managing S3 Configurations

### Viewing All Configurations

**Route:** `GET /admin/s3-configs`

Displays all S3 configurations with:
- Hospital name
- Provider badge (R2, AWS, etc.)
- Bucket name
- Active status
- Sync status counts (pending/in-progress/success/failed)

### Editing a Configuration

**Route:** `GET /admin/s3-configs/<id>/edit`

**Editable Fields:**
- Name
- Bucket name
- Region
- Endpoint URL
- Access key / Secret key
- Rotation settings
- Active status

**Important:** Disabling a config (`is_active=False`) causes new uploads to fall back to local storage.

### Deleting a Configuration

**Route:** `POST /admin/s3-configs/<id>/delete`

**Constraints:**
- Cannot delete active configuration
- Must disable before deletion
- Files with `s3_config_id` pointing to deleted config will show as orphaned

## S3 Sync Status Dashboard

### Hospital-Level Dashboard

**Route:** `GET /admin/s3-sync-hospital/<hospital_id>`

**Displays:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Hospital: City Eye Hospital                                    │
│  S3 Config: Production R2 (r2)                                  │
│  Bucket: fundus-images-prod                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Sync Status Counts                                             │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐      │
│  │ Pending  │ In Prog  │ Success  │ Failed   │ Total    │      │
│  │    12    │     3    │   1450   │    2     │  1467    │      │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘      │
│                                                                 │
│  Failed Syncs (2)                                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ File Type   │ Variant │ File          │ Attempts │ Error│   │
│  │─────────────┼─────────┼───────────────┼──────────┼──────│   │
│  │ direct_upld │ thumb   │ abc-123...jpg │    3     │ CN...│   │
│  │ encounter   │ edited  │ def-456...jpg │    2     │ TL...│   │
│  └─────────────────────────────────────────────────────────┘   │
│                    [Retry All]                                 │
│                                                                 │
│  Recent Sync Activity (last 50)                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Status │ Type     │ Variant │ Updated At                │   │
│  │────────┼──────────┼─────────┼───────────────────────────│   │
│  │ ✓      │ enc_file │ orig    │ 2026-01-31 18:45:23      │   │
│  │ ✓      │ enc_file │ thumb   │ 2026-01-31 18:45:22      │   │
│  │ ✓      │ dir_upld │ orig    │ 2026-01-31 18:45:20      │   │
│  │ ⚠      │ enc_set  │ edited  │ 2026-01-31 18:44:15      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Retry Failed Syncs

**Route:** `POST /admin/api/s3-sync-retry/<sync_id>`

**Action:** Re-queues the file for S3 upload

**Response:**
```json
{
  "success": true,
  "message": "Sync retry queued"
}
```

### System-Wide Dashboard

**Route:** `GET /admin/s3-sync-dashboard`

**Displays:**
- All hospitals with S3 configuration
- Per-hospital sync status counts
- Overall summary statistics
- Links to hospital detail pages

## Credential Rotation

### Manual Rotation

**Route:** `GET /admin/s3-configs/<id>/rotate-credentials`

**Process:**
1. User enters new access key and secret key
2. System updates `access_key_encrypted` and `secret_key_encrypted`
3. Updates `last_rotation_at` timestamp
4. Calculates `next_rotation_at` based on `rotate_after_days`

### Automatic Rotation (Future)

**Not yet implemented.** Planned feature:
- Background job checks `next_rotation_at` daily
- Sends alerts when rotation is due
- May integrate with cloud provider APIs for automatic key rotation

## URL Signing Configuration

### URL Signing Pepper

The `url_signing_pepper` field is used to generate HMAC-signed URLs for secure media access.

**Purpose:**
- Prevents unauthorized URL guessing
- Time-limited access tokens
- Per-hospital secret for isolation

**Generated URL Format:**
```
/media/<uuid>?token=<hmac_signature>&expires=<unix_timestamp>
```

## Validation and Testing

### Test Connection

**Route:** `POST /admin/s3-configs/<id>/test`

**Tests:**
1. Decrypt credentials
2. Create S3 client
3. Attempt `head_bucket` operation
4. Report success or error

**Possible Errors:**

| Error | Cause | Solution |
|-------|-------|----------|
| `InvalidAccessKeyId` | Wrong access key | Verify credentials |
| `SignatureDoesNotMatch` | Wrong secret key | Verify secret key |
| `NoSuchBucket` | Bucket doesn't exist | Create bucket first |
| `AccessDenied` | Insufficient permissions | Check IAM policy |
| `ConnectionError` | Wrong endpoint URL | Verify endpoint |

### Bucket Requirements

**Required:**
- Bucket must exist before configuration
- IAM user must have `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`
- IAM user must have `s3:ListBucket` for testing

**CORS Configuration (optional):**

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"]
    }
  ]
}
```

## Audit Logging

All S3 operations are logged:

```
# Uploads
S3_FILE_UPLOADED | s3_config_id=1 | hospital_id=5 | object_key=files/... | bucket=fundus-prod | etag="abc123"

# Deletions
S3_FILE_DELETED | s3_config_id=1 | hospital_id=5 | object_key=files/...

# Sync status changes
S3_SYNC_STATUS_UPDATE | sync_id=123 | status=success | attempt_count=1
```

**Log Locations:**
- Application logs: `logs/s3_sync.log`
- Security audit: `logs/security.audit.log`

## Troubleshooting

### Common Issues

**Uploads stuck in "pending":**
- Check Celery worker is running
- Review S3 credentials
- Verify network connectivity to S3 endpoint

**High "failed" count:**
- Check failed syncs for error patterns
- Verify bucket permissions
- Check S3 quota limits

**Local files not deleted after S3 upload:**
- Verify `cleanup_local_after_s3_upload` is enabled
- Check `S3_FALLBACK_CONTROL` environment variable

### Health Check

**Route:** `GET /admin/api/s3-health/<config_id>`

**Response:**
```json
{
  "status": "healthy",
  "bucket_accessible": true,
  "credentials_valid": true,
  "last_sync_at": "2026-01-31T18:45:00Z"
}
```

## Related Documentation

- [S3 Storage System](../00-Core/S3_storage_system.md) - Architecture and data models
- [S3 Sync Tracking](../16-NewFeature/S3/S3_sync_tracking.md) - Sync status API
- [Security](../09-Security/S3_security.md) - Encryption and access control
