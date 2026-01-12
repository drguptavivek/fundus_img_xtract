
import pytest
from unittest.mock import MagicMock, patch
from utils.taskUtils import get_task_detail
from models import GradingTask, LabUnit, Hospital, Disease, EncounterFile, DirectImageUpload, User

@pytest.fixture
def mock_db_session():
    return MagicMock()

@pytest.fixture
def mock_task():
    task = MagicMock(spec=GradingTask)
    task.id = 1
    task.state = 'pending'
    task.created_at = '2023-01-01'
    task.updated_at = '2023-01-01'
    
    # Setup relationships
    task.disease = MagicMock(spec=Disease)
    task.disease.name = 'DR'
    
    task.lab_unit = MagicMock(spec=LabUnit)
    task.lab_unit.hospital = MagicMock(spec=Hospital)
    task.lab_unit.hospital.name = 'Hospital B'
    task.lab_unit.hospital_id = 2  # Task is in Hospital 2
    
    # Mock image
    task.encounter_file = MagicMock(spec=EncounterFile)
    task.encounter_file.uuid = 'img-uuid-123'
    task.encounter_file.patient_id = '12345678'
    task.encounter_file.patient_name = 'John Doe'
    task.direct_image = None
    
    task.grades = []
    task.consensus = None
    
    return task

@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_global_admin_cross_hospital(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 1: Global Admin Cross-Hospital
    Expectation: PII is NOT masked.
    """
    # Setup User: Global Admin from Hospital 1
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 1
    
    # Mock Roles - list of Role objects
    role_admin = MagicMock()
    role_admin.name = 'admin'
    mock_current_user.roles = [role_admin]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == '12345678'
    assert result['patient_name'] == 'John Doe'


@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_global_admin_mixed_roles(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 2: Global Admin + Resident (Mixed Roles)
    Expectation: PII is NOT masked (Optimistic: Admin wins).
    """
    # Setup User: Admin + Resident
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 1
    
    role_resident = MagicMock()
    role_resident.name = 'resident'
    role_admin = MagicMock()
    role_admin.name = 'admin'
    
    # Order should not matter, but typically we want to test if presence of admin overrides others
    mock_current_user.roles = [role_resident, role_admin]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == '12345678'
    assert result['patient_name'] == 'John Doe'


@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_resident_cross_hospital(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 3: Resident Cross-Hospital
    Expectation: PII is MASKED.
    """
    # Setup User: Resident from Hospital 1
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 1
    
    role_resident = MagicMock()
    role_resident.name = 'resident'
    mock_current_user.roles = [role_resident]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == 'P****678'
    assert result['patient_name'] == 'Anonymous'


@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_resident_same_hospital(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 4: Resident Same-Hospital
    Expectation: PII is MASKED (Resident always masked).
    """
    # Setup User: Resident from Hospital 2 (Same as Task)
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 2
    
    role_resident = MagicMock()
    role_resident.name = 'resident'
    mock_current_user.roles = [role_resident]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == 'P****678'
    assert result['patient_name'] == 'Anonymous'


@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_data_manager_same_hospital(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 5: Data Manager Same-Hospital
    Expectation: PII is NOT masked.
    """
    # Setup User: Data Manager from Hospital 2 (Same as Task)
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 2
    
    role_dm = MagicMock()
    role_dm.name = 'data_manager'
    mock_current_user.roles = [role_dm]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == '12345678'
    assert result['patient_name'] == 'John Doe'


@patch('utils.taskUtils.current_user')
@patch('utils.taskUtils.apply_scoping')
def test_get_task_detail_data_manager_cross_hospital(mock_scoping, mock_current_user, mock_db_session, mock_task):
    """
    Test Case 6: Data Manager Cross-Hospital
    Expectation: PII is MASKED (Different hospital).
    """
    # Setup User: Data Manager from Hospital 1 (Diff from Task)
    mock_current_user.is_authenticated = True
    mock_current_user.hospital_id = 1
    
    role_dm = MagicMock()
    role_dm.name = 'data_manager'
    mock_current_user.roles = [role_dm]
    
    # Setup DB Query Mock
    mock_query = MagicMock()
    mock_scoping.return_value = mock_query
    mock_query.filter.return_value.options.return_value.first.return_value = mock_task
    
    # Execute
    result = get_task_detail(mock_db_session, 1)
    
    # Verify
    assert result['patient_id'] == 'P****678'
    assert result['patient_name'] == 'Anonymous'
