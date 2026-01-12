
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from analytics.utils import (
    _summarize_grade,
    _summarize_consensus,
    GradeSummary,
    ConsensusSummary,
    group_task_details_by_image,
    build_pagination_params,
    fetch_image_task_details
)
from models import Grade, Consensus, DiseaseGrading, User

class TestAnalyticsUtils:
    
    def test_summarize_grade(self):
        """Test _summarize_grade helper function."""
        # Case 1: None input
        assert _summarize_grade(None) is None

        # Case 2: Valid grade
        mock_grade = MagicMock(spec=Grade)
        mock_grade.role_slot = "resident"
        mock_grade.label = MagicMock(spec=DiseaseGrading)
        mock_grade.label.impression = "Referable"
        mock_grade.grader = MagicMock(spec=User)
        mock_grade.grader.username = "dr_test"
        mock_grade.comment = "Test comment"
        mock_grade.updated_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        summary = _summarize_grade(mock_grade)
        assert isinstance(summary, GradeSummary)
        assert summary.role == "resident"
        assert summary.impression == "Referable"
        assert summary.grader == "dr_test"
        assert summary.comment == "Test comment"
        assert summary.updated_at == "2025-01-01T12:00:00+00:00"

        # Case 3: Grade without label (e.g. just started)
        mock_grade.label = None
        summary = _summarize_grade(mock_grade)
        assert summary.impression is None

    def test_summarize_consensus(self):
        """Test _summarize_consensus helper function."""
        # Case 1: None input
        assert _summarize_consensus(None) is None

        # Case 2: Valid consensus
        mock_consensus = MagicMock(spec=Consensus)
        mock_consensus.final_label = MagicMock(spec=DiseaseGrading)
        mock_consensus.final_label.impression = "Referable"
        mock_consensus.final_grade_name = None
        mock_consensus.method = "manual"
        mock_consensus.decided_by = MagicMock(spec=User)
        mock_consensus.decided_by.username = "arbitrator_test"
        mock_consensus.decided_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        summary = _summarize_consensus(mock_consensus)
        assert isinstance(summary, ConsensusSummary)
        assert summary.impression == "Referable"
        assert summary.method == "manual"
        assert summary.decided_by == "arbitrator_test"
        assert summary.decided_at == "2025-01-01T12:00:00+00:00"
        
        # Case 3: Consensus with final_grade_name but no label object
        mock_consensus.final_label = None
        mock_consensus.final_grade_name = "Non-Referable"
        summary = _summarize_consensus(mock_consensus)
        assert summary.impression == "Non-Referable"

    def test_group_task_details_by_image(self):
        """Test grouping task details by image ID."""
        details = [
            {"task_id": 1, "encounter_file_id": 101, "disease_name": "Glaucoma"},
            {"task_id": 2, "encounter_file_id": 101, "disease_name": "DR"},
            {"task_id": 3, "encounter_file_id": 102, "disease_name": "Glaucoma"},
        ]
        
        grouped = group_task_details_by_image(details)
        assert len(grouped) == 2
        assert len(grouped[101]) == 2
        assert len(grouped[102]) == 1
        
        # Verify sorting (by disease name)
        # DR comes before Glaucoma alphabetically
        assert grouped[101][0]["disease_name"] == "DR"
        assert grouped[101][1]["disease_name"] == "Glaucoma"

    def test_build_pagination_params(self):
        """Test building pagination parameters."""
        filters = {"hospital_id": 1, "status": "", "search": None}
        target_page = 2
        
        params = build_pagination_params(filters, target_page)
        
        assert params["page"] == 2
        assert params["hospital_id"] == 1
        assert "status" not in params
        assert "search" not in params
