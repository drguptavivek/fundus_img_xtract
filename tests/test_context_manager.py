"""Test script to validate that the new task route uses proper database context management."""
import sys
import os

# Add the project root directory to the Python path to import modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import inspect
from tasks.route_task_details import view_task_details
from db_transaction_manager import get_db_session
from models import Session as ModelSession


def test_context_manager_usage():
    """Verify that the new route function properly uses the database context manager."""
    # Read the source code of the route function to verify context manager usage
    route_source = inspect.getsource(view_task_details)
    
    # Check that the function uses the context manager
    assert 'with get_db_session()' in route_source, "Route function should use get_db_session context manager"
    assert 'db.close()' not in route_source, "Route function should not manually close database session"
    assert 'Session()' not in route_source, "Route function should not create Session directly"
    
    print("✓ Database context manager usage is correct in the new route")
    
    # Read the entire file content to check for imports
    with open(os.path.join(project_root, 'tasks/route_task_details.py'), 'r') as f:
        file_content = f.read()
    
    # Verify imports are in the file
    assert 'from db_transaction_manager import get_db_session' in file_content, \
        "Route file should import get_db_session from db_transaction_manager"
    
    print("✓ Import statements are correct in the route file")


if __name__ == "__main__":
    test_context_manager_usage()
    print("\nAll tests passed! The new route properly uses database context management.")