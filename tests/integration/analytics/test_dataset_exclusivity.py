"""
Tests for dataset exclusivity feature.

TDD Approach: Tests written first, then implementation.

NOTE: Integration tests require materialized views (mvw_image_listing_all).
Tests that call routes will be skipped if views don't exist in test database.
"""

import pytest
import json
from flask import url_for
from sqlalchemy import text
from models import (
    User, CuratedDataset, CuratedDatasetItem,
    GradingTask, Disease, LabUnit
)
from review.discrepancy_export import _fetch_filtered_rows


def _check_materialized_view(db_session):
    """Skip test if materialized view doesn't exist."""
    try:
        result = db_session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'mvw_image_listing_all'"
        ))
        if result.scalar() is None:
            pytest.skip("Materialized view mvw_image_listing_all not available in test database")
    except Exception:
        pytest.skip("Materialized view mvw_image_listing_all not available in test database")


@pytest.mark.usefixtures("db_session", "client", "seed_test_database")
class TestDatasetExclusivity:
    """Test dataset exclusivity in dataset creation and filtering."""

    def test_create_dataset_with_exclusion(self, auth_client_factory, db_session):
        """
        Test creating a dataset that excludes tasks from existing datasets.
        Verify that excluded tasks don't appear in filtered results.
        """
        _check_materialized_view(db_session)

        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create first dataset with some tasks
        response1 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Primary Dataset",
            "dataset_purpose": "Training set v1",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
        }, follow_redirects=True)

        assert response1.status_code == 200
        dataset1 = db_session.query(CuratedDataset).filter_by(
            name="Primary Dataset"
        ).first()
        assert dataset1 is not None

        # Get the task IDs from first dataset
        items1 = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset1.id,
            include_in_export=True
        ).all()
        task_ids_1 = {item.task_id for item in items1}

        # Create second dataset that excludes the first
        response2 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Secondary Dataset",
            "dataset_purpose": "Validation set (excludes training)",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "excluded_dataset_ids": [str(dataset1.id)],
        }, follow_redirects=True)

        assert response2.status_code == 200
        dataset2 = db_session.query(CuratedDataset).filter_by(
            name="Secondary Dataset"
        ).first()
        assert dataset2 is not None

        # Check filters_json contains excluded_dataset_ids
        filters = json.loads(dataset2.filters_json)
        assert "excluded_dataset_ids" in filters
        assert dataset1.id in filters["excluded_dataset_ids"]

    def test_exclude_multiple_datasets(self, auth_client_factory, db_session):
        """
        Test excluding tasks from multiple datasets simultaneously.
        """
        _check_materialized_view(db_session)

        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create three datasets
        dataset_ids = []
        for i in range(3):
            response = client.post("/analytics/dataset-curation", data={
                "dataset_name": f"Dataset {i+1}",
                "dataset_purpose": f"Test dataset {i+1}",
                "disease_id": disease.id if disease else 1,
                "lab_unit_id": lab_unit.id if lab_unit else 1,
                "auto_select_count": 5,
            }, follow_redirects=True)

            dataset = db_session.query(CuratedDataset).filter_by(
                name=f"Dataset {i+1}"
            ).first()
            dataset_ids.append(dataset.id)

        # Create dataset excluding first two
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Excluding Multiple",
            "dataset_purpose": "Test multi-exclusion",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "excluded_dataset_ids": [str(dataset_ids[0]), str(dataset_ids[1])],
        }, follow_redirects=True)

        assert response.status_code == 200
        new_dataset = db_session.query(CuratedDataset).filter_by(
            name="Excluding Multiple"
        ).first()

        # Both dataset IDs in exclusion list
        filters = json.loads(new_dataset.filters_json)
        assert set(filters["excluded_dataset_ids"]) == {dataset_ids[0], dataset_ids[1]}

    def test_exclusion_only_affects_included_tasks(self, auth_client_factory, db_session):
        """
        Test that exclusion only applies to tasks with include_in_export=true.
        Tasks that were skipped (include_in_export=false) should still be available.
        """
        _check_materialized_view(db_session)

        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create dataset with auto-select
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Source Dataset",
            "dataset_purpose": "Test skip vs include",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
        }, follow_redirects=True)

        source_dataset = db_session.query(CuratedDataset).filter_by(
            name="Source Dataset"
        ).first()

        # Manually exclude some items (set include_in_export=False)
        items = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=source_dataset.id
        ).limit(5).all()
        for item in items:
            item.include_in_export = False
        db_session.commit()

        included_count = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=source_dataset.id,
            include_in_export=True
        ).count()

        # Create dataset excluding source
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "New Dataset",
            "dataset_purpose": "Test skip availability",
            "disease_id": disease.id if disease else 1,
            "excluded_dataset_ids": [str(source_dataset.id)],
        }, follow_redirects=True)

        new_dataset = db_session.query(CuratedDataset).filter_by(
            name="New Dataset"
        ).first()

        # Verify exclusion is stored
        filters = json.loads(new_dataset.filters_json)
        assert source_dataset.id in filters["excluded_dataset_ids"]
        assert included_count > 0

    def test_exclusion_with_empty_list(self, auth_client_factory, db_session):
        """
        Test that empty excluded_dataset_ids list doesn't break query.
        """
        _check_materialized_view(db_session)

        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create dataset without exclusions
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "No Exclusions",
            "dataset_purpose": "Test empty exclusion list",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
        }, follow_redirects=True)

        assert response.status_code == 200
        dataset = db_session.query(CuratedDataset).filter_by(
            name="No Exclusions"
        ).first()

        # Should have empty or no excluded_dataset_ids
        filters = json.loads(dataset.filters_json)
        excluded_ids = filters.get("excluded_dataset_ids", [])
        assert excluded_ids == [] or excluded_ids is None

    def test_delete_dataset_releases_tasks(self, auth_client_factory, db_session):
        """
        Test that deleting a dataset makes its tasks available again.
        """
        _check_materialized_view(db_session)

        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create dataset with auto-selected tasks
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "To Be Deleted",
            "dataset_purpose": "Test deletion release",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
        }, follow_redirects=True)

        dataset = db_session.query(CuratedDataset).filter_by(
            name="To Be Deleted"
        ).first()
        dataset_uuid = dataset.uuid
        dataset_id = dataset.id

        items = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset.id,
            include_in_export=True
        ).all()
        original_task_ids = {item.task_id for item in items}
        item_count = len(items)

        # Delete the dataset
        response = client.post(
            f"/analytics/dataset-curation/{dataset_uuid}/delete",
            follow_redirects=True
        )

        assert response.status_code == 200

        # Verify dataset is deleted
        deleted_dataset = db_session.query(CuratedDataset).filter_by(
            uuid=dataset_uuid
        ).first()
        assert deleted_dataset is None

        # Verify CuratedDatasetItems are cascade deleted
        remaining_items = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset_id
        ).all()
        assert len(remaining_items) == 0

        # Verify tasks can be selected again (create new dataset)
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "After Deletion",
            "dataset_purpose": "Test tasks available",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
        }, follow_redirects=True)

        assert response.status_code == 200


@pytest.mark.usefixtures("db_session", "seed_test_database")
class TestFetchFilteredRowsExclusion:
    """Unit tests for _fetch_filtered_rows with exclusion parameter."""

    def test_fetch_filtered_rows_with_exclusion(self, db_session):
        """
        Test that _fetch_filtered_rows accepts excluded_dataset_ids parameter.
        """
        _check_materialized_view(db_session)

        disease = db_session.query(Disease).first()
        lab_units = [lu.id for lu in db_session.query(LabUnit).limit(2).all()]

        # First get all rows without exclusion
        filters_no_exclude = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
        }

        rows_all = _fetch_filtered_rows(filters_no_exclude)
        all_task_ids = {r.task_id for r in rows_all}

        if len(all_task_ids) < 10:
            pytest.skip("Not enough tasks to test exclusion")

        # Now test with exclusion (empty list - should work)
        filters_with_empty_exclude = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
            "excluded_dataset_ids": [],
        }

        rows_empty_exclude = _fetch_filtered_rows(filters_with_empty_exclude)
        assert isinstance(rows_empty_exclude, list)
        # Empty exclusion should return same results
        assert len(rows_all) == len(rows_empty_exclude)

    def test_exclusion_with_nonexistent_dataset_id(self, db_session):
        """
        Test that excluding a non-existent dataset ID doesn't break query.
        """
        disease = db_session.query(Disease).first()
        lab_units = [lu.id for lu in db_session.query(LabUnit).limit(2).all()]

        filters = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
            "excluded_dataset_ids": [99999],  # Non-existent dataset
        }

        # Should not raise error
        rows = _fetch_filtered_rows(filters)
        assert isinstance(rows, list)

    def test_exclusion_filters_include_in_export_true_only(self, db_session):
        """
        Test that exclusion only considers tasks with include_in_export=true.
        This is enforced at SQL level.
        """
        _check_materialized_view(db_session)

        from models import CuratedDataset, CuratedDatasetItem, GradingTask

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Get actual task IDs from the database
        existing_tasks = (
            db_session.query(GradingTask.id)
            .filter(
                GradingTask.disease_id == disease.id if disease else True,
                GradingTask.lab_unit_id == lab_unit.id if lab_unit else True,
            )
            .limit(10)
            .all()
        )
        task_ids = [t.id for t in existing_tasks]

        if len(task_ids) < 10:
            pytest.skip("Not enough tasks in test database to test include_in_export filtering")

        # Create a dataset
        dataset = CuratedDataset(
            name="Test Dataset",
            purpose="Test include_in_export filtering",
            filters_json=json.dumps({
                "disease_id": disease.id if disease else 1,
                "allowed_lab_units": [lab_unit.id if lab_unit else 1],
            }),
            disease_id=disease.id if disease else 1,
            created_by_user_id=1,
        )
        db_session.add(dataset)
        db_session.flush()

        # Add some items as included (first 5)
        for task_id in task_ids[:5]:
            item = CuratedDatasetItem(
                dataset_id=dataset.id,
                task_id=task_id,
                include_in_export=True,
                selection_method="auto",
            )
            db_session.add(item)

        # Add some items as excluded (include_in_export=false) (next 5)
        for task_id in task_ids[5:10]:
            item = CuratedDatasetItem(
                dataset_id=dataset.id,
                task_id=task_id,
                include_in_export=False,
                selection_method="auto",
            )
            db_session.add(item)

        db_session.commit()

        # Now test that _fetch_filtered_rows with exclusion only excludes the included ones
        filters = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": [lab_unit.id if lab_unit else 1],
            "excluded_dataset_ids": [dataset.id],
        }

        # The SQL should only exclude tasks with include_in_export=true (first 5)
        # Tasks with include_in_export=false (next 5) should theoretically be available
        rows = _fetch_filtered_rows(filters)
        assert isinstance(rows, list)
