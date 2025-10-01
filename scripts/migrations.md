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

## 2024-11-29 — Enable Server-side Sessions

- **Script:** `scripts/migrations/20241129_add_flask_sessions.py`
- **Purpose:** Creates the `flask_sessions` table used to persist session data between server restarts.
- **Run:**
  ```bash
  uv run scripts/migrations/20241129_add_flask_sessions.py
  ```
- **Notes:**
  - Safe to run multiple times; it no-ops when the table already exists.

- **Script:** `scripts/migrations/20241129_add_flask_session_user_id.py`
- **Purpose:** Adds a nullable `user_id` column (indexed) to `flask_sessions` to track session owners.
- **Run:**
  ```bash
  uv run scripts/migrations/20241129_add_flask_session_user_id.py
  ```
- **Notes:**
  - Safe to rerun; it exits early if the column already exists.

## 2024-11-30 — Track Session Lifetimes

- **Script:** `scripts/migrations/20241130_add_flask_session_timestamps.py`
- **Purpose:** Adds `started_at` (UTC, non-null) and `ended_at` (nullable) columns to `flask_sessions` so the app can record session lifetimes.
- **Run:**
  ```bash
  uv run scripts/migrations/20241130_add_flask_session_timestamps.py
  ```
- **Notes:**
  - Requires the earlier `flask_sessions` migrations. Safe to rerun; it skips work if the columns already exist.

## 2024-10-01 — Per-user Notification Read Tracking

- **Script:** `scripts/migrations/20241001_add_notification_reads.py`
- **Purpose:** Adds `notification_reads` table to record which users have read broadcast notifications.
- **Run:**
  ```bash
  uv run scripts/migrations/20241001_add_notification_reads.py
  ```
- **Notes:**
  - Creates indices and a uniqueness constraint. Safe to rerun; it no-ops if the table exists.
