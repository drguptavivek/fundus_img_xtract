# Viewer Settings Persistence

This document describes the implementation of persistent viewer settings and presets for the Fundus Image Manager application.

## Overview

The viewer settings and presets functionality has been migrated from localStorage to database persistence, allowing user settings to persist across sessions and devices.

## Database Schema

Two new tables have been added to the database:

### ViewerSettings Table

Stores user-specific viewer settings that persist across sessions.

**Columns:**
- `id`: Primary key
- `user_id`: Foreign key to users table (unique)
- `loupe_size`: Loupe magnifier size (100-500)
- `loupe_zoom`: Loupe magnification level (1.0-4.0)
- `loupe_enabled`: Whether loupe is enabled (boolean)
- `zoom`: Image zoom level (40-500%)
- `pan_x`: Horizontal pan position (-600 to 600)
- `pan_y`: Vertical pan position (-600 to 600)
- `brightness`: Image brightness (0.5-1.5)
- `contrast`: Image contrast (0.5-1.5)
- `filter`: Current filter (none, redfree, greenboost, bluemono, gray, contrast)
- `created_at`: Timestamp when settings were created
- `updated_at`: Timestamp when settings were last updated

### ViewerPresets Table

Stores up to 5 named presets per user for quick access to viewer configurations.

**Columns:**
- `id`: Primary key
- `user_id`: Foreign key to users table
- `slot_number`: Preset slot (1-5)
- `name`: Optional preset name for user reference
- All viewer settings columns (loupe_size, loupe_zoom, loupe_enabled, zoom, pan_x, pan_y, brightness, contrast, filter)
- `created_at`: Timestamp when preset was created
- `updated_at`: Timestamp when preset was last updated

## API Endpoints

### GET /api/viewer/settings

Retrieves the current user's viewer settings.

**Response:**
```json
{
  "loupe_size": 200,
  "loupe_zoom": 2.0,
  "loupe_enabled": false,
  "zoom": 100,
  "pan_x": 0,
  "pan_y": 0,
  "brightness": 1.0,
  "contrast": 1.0,
  "filter": "none"
}
```

### POST /api/viewer/settings

Saves the current user's viewer settings.

**Request:**
```json
{
  "loupe_size": 200,
  "loupe_zoom": 2.0,
  "loupe_enabled": false,
  "zoom": 100,
  "pan_x": 0,
  "pan_y": 0,
  "brightness": 1.0,
  "contrast": 1.0,
  "filter": "none"
}
```

### GET /api/viewer/presets

Retrieves all presets for the current user.

**Response:**
```json
{
  "1": {
    "id": 1,
    "name": "High Contrast",
    "loupe_size": 250,
    "loupe_zoom": 2.5,
    "loupe_enabled": true,
    "zoom": 150,
    "pan_x": 10,
    "pan_y": -5,
    "brightness": 1.2,
    "contrast": 1.3,
    "filter": "contrast"
  },
  "2": { ... },
  ...
}
```

### POST /api/viewer/presets/{slot_number}

Saves a preset to the specified slot (1-5).

**Request:**
```json
{
  "name": "My Preset",
  "loupe_size": 200,
  "loupe_zoom": 2.0,
  "loupe_enabled": false,
  "zoom": 100,
  "pan_x": 0,
  "pan_y": 0,
  "brightness": 1.0,
  "contrast": 1.0,
  "filter": "none"
}
```

### DELETE /api/viewer/presets/{slot_number}

Deletes a preset from the specified slot (1-5).

## Frontend Changes

The frontend JavaScript has been updated to use the API endpoints instead of localStorage:

1. **API Functions Added:**
   - `fetchViewerSettings()`: Retrieves settings from API
   - `saveViewerSettings()`: Saves settings to API
   - `fetchViewerPresets()`: Retrieves presets from API
   - `saveViewerPreset()`: Saves a single preset to API
   - `deleteViewerPreset()`: Deletes a preset from API

2. **Async Initialization:**
   - Settings are now loaded asynchronously from the API
   - Fallback to default values if API fails

3. **Backward Compatibility:**
   - Legacy localStorage functions are retained for fallback
   - Existing localStorage data will be migrated on first load

## Migration

### Database Migration

Run the migration script to add the new tables:

```bash
uv run python scripts/migrate_viewer_settings.py
```

### Testing

Test the implementation:

```bash
uv run python scripts/test_viewer_settings.py
```

## Benefits

1. **Cross-Device Persistence**: Settings now persist across browsers and devices
2. **User-Specific**: Each user has their own settings and presets
3. **Centralized Management**: Settings can be managed centrally if needed
4. **Backup Friendly**: Database can be backed up along with other user data

## Security Considerations

- All API endpoints require user authentication
- Settings are isolated per user (no cross-user access)
- Input validation is performed on all settings values