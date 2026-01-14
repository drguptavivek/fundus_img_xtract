
import pytest
from unittest.mock import MagicMock
from models import User, Role
from utils.hospital_scoping import apply_scoping

@pytest.fixture
def mock_dataset_creator():
    role = Role(name='dataset_creator')
    user = User(id=1, username='creator', hospital_id=1, roles=[role])
    return user

@pytest.fixture
def mock_analytics_viewer():
    role = Role(name='analytics_viewer')
    user = User(id=2, username='viewer', hospital_id=1, roles=[role])
    return user

def test_dataset_creator_scoping(mock_dataset_creator):
    # Case 1: Dataset creation (Cross-hospital allowed)
    query = MagicMock()
    model = MagicMock()

    # Should bypass filtering
    result = apply_scoping(query, model, mock_dataset_creator, 'dataset_creation')
    assert result == query

    # Case 2: Regular upload (Hospital-bound)
    # Should apply filtering (mock call count check would be better, but we return modified query)
    # For this unit test, we check if it falls through to hospital filtering logic
    # Since we can't easily inspect the query filter in this mock setup without complex sqlalchemy mocking,
    # we trust the logic flow: if it returned early, it would be 'query'.
    # If it applies filters, it calls query.filter().

    # Create a proper model mock that only has hospital_id attribute
    model = MagicMock(spec=['hospital_id'])  # Only has hospital_id, not lab_unit_id
    model.hospital_id = 1

    # Mock query.filter to return a new mock (not a string!)
    filtered_query = MagicMock()
    query.filter.return_value = filtered_query

    # Mock user with empty lab_units list
    mock_dataset_creator.lab_units = []

    result = apply_scoping(query, model, mock_dataset_creator, 'upload')
    # Result should be the filtered query (not a string)
    assert result == filtered_query
    # Verify that filter was called (hospital filtering was applied)
    assert query.filter.called

def test_analytics_viewer_scoping(mock_analytics_viewer):
    # Analytics viewer is strictly hospital bound
    query = MagicMock()
    filtered_query = MagicMock()
    query.filter.return_value = filtered_query

    # Create a proper model mock that only has hospital_id attribute
    model = MagicMock(spec=['hospital_id'])  # Only has hospital_id, not lab_unit_id
    model.hospital_id = 1

    # Mock user with empty lab_units list
    mock_analytics_viewer.lab_units = []

    # Should apply filtering
    result = apply_scoping(query, model, mock_analytics_viewer, 'analytics')
    assert result == filtered_query
    # Verify that filter was called (hospital filtering was applied)
    assert query.filter.called

def test_dataset_creator_research_access(mock_dataset_creator):
    query = MagicMock()
    model = MagicMock()
    # Research op -> allowed cross hospital
    result = apply_scoping(query, model, mock_dataset_creator, 'research')
    assert result == query
