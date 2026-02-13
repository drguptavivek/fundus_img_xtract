import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from utils.dualGradingEligibility import _has_user_graded_task_4weeks

def test_has_user_graded_task_4weeks_no_grades():
    """Verify returns False when user has no grades for the task."""
    # Setup
    db = MagicMock()
    user_id = 1
    task_id = 100
    
    # Mock query result (empty list)
    db.query.return_value.filter.return_value.all.return_value = []
    
    # Execute
    result = _has_user_graded_task_4weeks(db, user_id, task_id)
    
    # Verify
    assert result is False

def test_has_user_graded_task_4weeks_recent_grade():
    """Verify returns True when user has a grade within 4 weeks."""
    # Setup
    db = MagicMock()
    user_id = 1
    task_id = 100
    
    # Create a grade from 1 week ago
    recent_grade = MagicMock()
    recent_grade.created_at = datetime.now(timezone.utc) - timedelta(weeks=1)
    
    # Mock query result
    db.query.return_value.filter.return_value.all.return_value = [recent_grade]
    
    # Execute
    result = _has_user_graded_task_4weeks(db, user_id, task_id)
    
    # Verify
    assert result is True

def test_has_user_graded_task_4weeks_old_grade():
    """Verify returns False when user's last grade was > 4 weeks ago."""
    # Setup
    db = MagicMock()
    user_id = 1
    task_id = 100
    
    # Create a grade from 5 weeks ago
    old_grade = MagicMock()
    old_grade.created_at = datetime.now(timezone.utc) - timedelta(weeks=5)
    
    # Mock query result
    db.query.return_value.filter.return_value.all.return_value = [old_grade]
    
    # Execute
    result = _has_user_graded_task_4weeks(db, user_id, task_id)
    
    # Verify
    assert result is False

def test_has_user_graded_task_4weeks_multiple_grades_mixed():
    """Verify returns True if ANY grade is recent, even if old ones exist."""
    # Setup
    db = MagicMock()
    user_id = 1
    task_id = 100
    
    # Recent grade (1 week ago)
    recent_grade = MagicMock()
    recent_grade.created_at = datetime.now(timezone.utc) - timedelta(weeks=1)
    
    # Old grade (6 weeks ago)
    old_grade = MagicMock()
    old_grade.created_at = datetime.now(timezone.utc) - timedelta(weeks=6)
    
    # Mock query result
    db.query.return_value.filter.return_value.all.return_value = [old_grade, recent_grade]
    
    # Execute
    result = _has_user_graded_task_4weeks(db, user_id, task_id)
    
    # Verify
    assert result is True

def test_has_user_graded_task_4weeks_naive_datetime():
    """Verify robust handling of naive datetimes from DB (assumed UTC)."""
    # Setup
    db = MagicMock()
    user_id = 1
    task_id = 100
    
    # Create a grade from 1 week ago (naive)
    recent_grade = MagicMock()
    # Naive datetime (no tzinfo)
    recent_grade.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(weeks=1)
    
    # Mock query result
    db.query.return_value.filter.return_value.all.return_value = [recent_grade]
    
    # Execute
    result = _has_user_graded_task_4weeks(db, user_id, task_id)
    
    # Verify
    assert result is True
