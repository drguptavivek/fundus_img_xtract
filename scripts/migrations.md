# Migration Scripts

## 2024-11-22 — Add User Timezone Preference

- **Script:** `scripts/migrations/20241122_add_user_timezone.py`
- **Purpose:** Adds the `timezone` column to the `users` table and backfills existing records with the default display timezone.
- **Run:**
  ```bash
  uv run scripts/migrations/20241122_add_user_timezone.py
  ```
- **Notes:**
  - Safe to run multiple times; the script exits early if the column already exists.
  - Update the `.env` variable `DEFAULT_DISPLAY_TIMEZONE` if you need a different default before running.
