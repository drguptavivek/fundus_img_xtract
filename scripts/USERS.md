

```bash
python -m scripts.create_user

python -m scripts.assign_roles admin --roles admin


python -m scripts.assign_roles alice --roles admin data_manager
python -m scripts.assign_roles bob   --roles fileUploader


1. scripts/list_users.py

  Features:
  - Lists all active users by default
  - Shows username, email, roles, and creation date
  - Optional -v/--verbose flag for detailed information (ID, full name, timezone, last login, etc.)
  - Optional -a/--all flag to include inactive users
  - Proper timezone handling (displays dates in IST)

  Usage:
  # Basic user list
  uv run python -m scripts.list_users

  # Detailed information
  uv run python -m scripts.list_users --verbose

  # Include inactive users
  uv run python -m scripts.list_users --all

  # Both verbose and all users
  uv run python -m scripts.list_users -v -a

  2. scripts/reset_user_password.py


  Usage:
  # Interactive mode (will prompt for password and confirmation)
  uv run python -m scripts.reset_user_password admin

  # Interactive mode with force (no confirmation prompt)
  uv run python -m scripts.reset_user_password admin --force

  # Non-interactive mode with password provided
  uv run python -m scripts.reset_user_password admin --password newpassword123

  # Combined force and password
  uv run python -m scripts.reset_user_password admin -f -p newpassword123

```


