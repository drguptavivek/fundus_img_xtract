
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
    
    # Let's mock query.filter to return a new mock
    query.filter.return_value = "filtered_query"
    model.hospital_id = 1
    
    result = apply_scoping(query, model, mock_dataset_creator, 'upload')
    assert result == "filtered_query"

def test_analytics_viewer_scoping(mock_analytics_viewer):
    # Analytics viewer is strictly hospital bound
    query = MagicMock()
    query.filter.return_value = "filtered_query"
    model = MagicMock()
    model.hospital_id = 1
    
    # Should apply filtering
    result = apply_scoping(query, model, mock_analytics_viewer, 'analytics')
    assert result == "filtered_query"

def test_dataset_creator_research_access(mock_dataset_creator):
    query = MagicMock()
    model = MagicMock()
    # Research op -> allowed cross hospital
    result = apply_scoping(query, model, mock_dataset_creator, 'research')
    assert result == query
