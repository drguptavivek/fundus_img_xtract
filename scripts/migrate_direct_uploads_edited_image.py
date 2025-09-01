from sqlalchemy import text
from models import engine
from sqlalchemy.exc import OperationalError

def migrate(dry_run=False):
    print(f"{'[DRY RUN] ' if dry_run else ''}Adding edited_image_path column to direct_image_uploads table...", flush=True)
    
    try:
        # Try to add the column
        if not dry_run:
            with engine.connect() as connection:
                # Check if the column already exists
                column_exists = False
                
                # Different approach for different databases
                if engine.dialect.name == 'sqlite':
                    # For SQLite, check the table info
                    result = connection.execute(text("PRAGMA table_info(direct_image_uploads)"))
                    columns = [row[1] for row in result.fetchall()]
                    column_exists = 'edited_image_path' in columns
                else:
                    # For other databases (PostgreSQL, MySQL, etc.), check information_schema
                    try:
                        result = connection.execute(text("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'direct_image_uploads' 
                            AND column_name = 'edited_image_path'
                        """))
                        column_exists = result.fetchone() is not None
                    except OperationalError:
                        # Fallback method
                        try:
                            connection.execute(text("SELECT edited_image_path FROM direct_image_uploads LIMIT 1"))
                            column_exists = True
                        except OperationalError:
                            column_exists = False
                
                if column_exists:
                    print("Column 'edited_image_path' already exists in direct_image_uploads table.", flush=True)
                    return
                
                # Add the column
                connection.execute(text("ALTER TABLE direct_image_uploads ADD COLUMN edited_image_path VARCHAR(1024)"))
                connection.commit()
                print("Successfully added 'edited_image_path' column to direct_image_uploads table.", flush=True)
        else:
            print("Would add 'edited_image_path' column to direct_image_uploads table.", flush=True)
                
    except Exception as e:
        # Check if the error is because the column already exists
        error_msg = str(e).lower()
        if "duplicate" in error_msg or "already exists" in error_msg:
            print("Column 'edited_image_path' already exists in direct_image_uploads table.", flush=True)
        else:
            print(f"Error adding 'edited_image_path' column: {e}", flush=True)
            if not dry_run:
                raise