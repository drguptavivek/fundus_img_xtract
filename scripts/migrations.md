# Database Migrations

This document outlines the database migration scripts and their usage.

## 1. Create Direct Image Uploads Table

This migration creates the `direct_image_uploads` table, which is used to store metadata for images uploaded directly through the web interface.

**Script:** `scripts/migrate_direct_uploads.py`

**Usage:**

To run this migration, execute the `setup_db.py` script with the `--migrate-direct-uploads` flag:

```bash
python scripts/setup_db.py --migrate-direct-uploads
```

This command will create the `direct_image_uploads` table if it does not already exist.

## 2. Add Edited Image Path Column

This migration adds the `edited_image_path` column to the `direct_image_uploads` table, which is used to store the path to edited versions of images.

**Script:** `scripts/migrate_direct_uploads_edited_image.py`

**Usage:**

To run this migration, execute the `setup_db.py` script with the `--migrate-direct-uploads-edited-image` flag:

```bash
python scripts/setup_db.py --migrate-direct-uploads-edited-image
```

This command will add the `edited_image_path` column to the `direct_image_uploads` table if it does not already exist.
