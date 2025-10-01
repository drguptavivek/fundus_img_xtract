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

## 2024-11-29 — Track Lab Unit on Jobs

- **Script:** `scripts/migrations/20241129_add_job_lab_unit_id.py`
- **Purpose:** Adds a nullable `lab_unit_id` column (indexed) to the `jobs` table so uploads can be tied back to a specific lab unit.
- **Run:**
  ```bash
  uv run scripts/migrations/20241129_add_job_lab_unit_id.py
  ```
- **Notes:**
  - Safe to run repeatedly; the script will no-op if the column already exists.

## 2024-11-29 — Add Notification Sender Tracking

- **Script:** `scripts/migrations/20241129_add_notification_sender.py`
- **Purpose:** Adds a `sender_user_id` column (with index) to the `notifications` table so “sent” messages retain author attribution.
- **Run:**
  ```bash
  uv run scripts/migrations/20241129_add_notification_sender.py
  ```
- **Notes:**
  - Safe to rerun; the script exits early if the column already exists.
