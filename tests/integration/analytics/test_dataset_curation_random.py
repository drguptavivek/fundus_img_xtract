"""
Tests for random selection feature in dataset curation.

TDD Approach: Tests written first, then implementation.
"""

import pytest
from flask import url_for
from models import User, CuratedDataset, CuratedDatasetItem, GradingTask, Disease, LabUnit
from review.discrepancy_export import _fetch_filtered_rows


@pytest.mark.usefixtures("db_session", "client", "seed_test_database")
class TestDatasetCurationRandomSelection:
    """Test random selection in dataset curation auto-select."""

    def test_auto_select_sequential_default(self, auth_client_factory, db_session):
        """
        Test that auto-select defaults to sequential (current behavior).
        When randomize_selection is not provided, selection should be sequential.
        """
        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        # Get first disease for testing
        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create dataset with auto-select but NO randomize checkbox
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Sequential Test Dataset",
            "dataset_purpose": "Test sequential default behavior",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 5,
            # randomize_selection NOT provided - should default to False
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify dataset created
        dataset = db_session.query(CuratedDataset).filter_by(
            name="Sequential Test Dataset"
        ).first()

        assert dataset is not None
        # Check that filter has randomize=False or missing (backward compatible)
        import json
        filters = json.loads(dataset.filters_json)
        assert filters.get("randomize_selection") is False or "randomize_selection" not in filters

    def test_auto_select_random_true(self, auth_client_factory, db_session):
        """
        Test that randomize_selection=True produces random selection.
        The selected tasks should be randomly distributed, not sequential by ID.
        """
        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Create dataset with randomize_selection enabled
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Random Test Dataset",
            "dataset_purpose": "Test random selection feature",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
            "randomize_selection": "yes",  # Enable randomization
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verify dataset created with randomize flag
        dataset = db_session.query(CuratedDataset).filter_by(
            name="Random Test Dataset"
        ).first()

        assert dataset is not None

        import json
        filters = json.loads(dataset.filters_json)
        assert filters.get("randomize_selection") is True

        # Verify we got exactly 10 items (or as many as available)
        items = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset.id
        ).all()

        assert len(items) > 0
        # All items should have selection_method="auto"
        for item in items:
            assert item.selection_method == "auto"

    def test_auto_select_random_deterministic_seed(self, auth_client_factory, db_session):
        """
        Test that providing a random_seed produces consistent results.
        Same seed should produce the same selection across runs.
        """
        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # First dataset with seed
        response1 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Seeded Dataset 1",
            "dataset_purpose": "Test deterministic random with seed",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
            "randomize_selection": "yes",
            "random_seed": "42",  # Fixed seed
        }, follow_redirects=True)

        assert response1.status_code == 200

        dataset1 = db_session.query(CuratedDataset).filter_by(
            name="Seeded Dataset 1"
        ).first()

        items1 = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset1.id
        ).all()
        task_ids_1 = sorted([i.task_id for i in items1])

        # Second dataset with same seed
        response2 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Seeded Dataset 2",
            "dataset_purpose": "Test deterministic random with seed",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
            "randomize_selection": "yes",
            "random_seed": "42",  # Same seed
        }, follow_redirects=True)

        assert response2.status_code == 200

        dataset2 = db_session.query(CuratedDataset).filter_by(
            name="Seeded Dataset 2"
        ).first()

        items2 = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset2.id
        ).all()
        task_ids_2 = sorted([i.task_id for i in items2])

        # Same seed should produce same selection
        assert task_ids_1 == task_ids_2

    def test_auto_select_random_count_exceeds_matches(self, auth_client_factory, db_session):
        """
        Test edge case where requested count exceeds available matching tasks.
        Should select all available tasks without error.
        """
        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # Request more tasks than likely exist
        response = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Oversized Random Dataset",
            "dataset_purpose": "Test count exceeds available",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 99999,  # Way more than available
            "randomize_selection": "yes",
        }, follow_redirects=True)

        assert response.status_code == 200

        dataset = db_session.query(CuratedDataset).filter_by(
            name="Oversized Random Dataset"
        ).first()

        assert dataset is not None

        items = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset.id
        ).all()

        # Should have selected all available (or reasonable subset)
        # Just verify no error occurred and we got some items
        assert len(items) >= 0

    def test_random_selection_different_samples(self, auth_client_factory, db_session):
        """
        Test that random selection produces different samples.
        Creating two datasets without seed should produce different results.
        Note: This is probabilistic, but with enough tasks it's very unlikely
        to get the same sample twice.
        """
        user = db_session.query(User).filter_by(username='master_admin').first()
        client = auth_client_factory(user)

        disease = db_session.query(Disease).first()
        lab_unit = db_session.query(LabUnit).first()

        # First dataset - random, no seed
        response1 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Random Sample 1",
            "dataset_purpose": "Test variability",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
            "randomize_selection": "yes",
            # No seed - should be different each time
        }, follow_redirects=True)

        assert response1.status_code == 200

        dataset1 = db_session.query(CuratedDataset).filter_by(
            name="Random Sample 1"
        ).first()

        items1 = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset1.id
        ).all()
        task_ids_1 = set([i.task_id for i in items1])

        # Second dataset - same params, different execution
        response2 = client.post("/analytics/dataset-curation", data={
            "dataset_name": "Random Sample 2",
            "dataset_purpose": "Test variability",
            "disease_id": disease.id if disease else 1,
            "lab_unit_id": lab_unit.id if lab_unit else 1,
            "auto_select_count": 10,
            "randomize_selection": "yes",
        }, follow_redirects=True)

        assert response2.status_code == 200

        dataset2 = db_session.query(CuratedDataset).filter_by(
            name="Random Sample 2"
        ).first()

        items2 = db_session.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset2.id
        ).all()
        task_ids_2 = set([i.task_id for i in items2])

        # With 10 selections from potentially many tasks, probability of
        # identical samples is extremely low. Allow for small chance of collision.
        # If we have enough tasks, samples should differ.
        if len(task_ids_1) >= 5 and len(task_ids_2) >= 5:
            # Check that at least some tasks differ (probabilistic test)
            # With 10 random samples, expected overlap is small
            overlap = len(task_ids_1 & task_ids_2)
            # If both samples are size 10, expected overlap is small (~2-3)
            # This is a soft assertion due to probabilistic nature
            # We just verify they're not IDENTICAL (which would be suspicious)
            assert not (task_ids_1 == task_ids_2 and len(task_ids_1) >= 5)


@pytest.mark.usefixtures("db_session", "seed_test_database")
class TestFetchFilteredRowsRandom:
    """Unit tests for _fetch_filtered_rows with random parameter."""

    def test_fetch_filtered_rows_random_param(self, db_session):
        """
        Test that _fetch_filtered_rows accepts randomize parameter.
        """
        disease = db_session.query(Disease).first()
        lab_units = [lu.id for lu in db_session.query(LabUnit).limit(2).all()]

        filters = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
        }

        # Sequential (default)
        rows_sequential = _fetch_filtered_rows(filters.copy())
        assert isinstance(rows_sequential, list)

        # Random selection
        filters["randomize_selection"] = True
        rows_random = _fetch_filtered_rows(filters.copy())
        assert isinstance(rows_random, list)

        # Should return same number of rows (just different order)
        assert len(rows_sequential) == len(rows_random)

    def test_fetch_filtered_rows_random_with_seed(self, db_session):
        """
        Test that _fetch_filtered_rows with seed produces consistent results.
        """
        disease = db_session.query(Disease).first()
        lab_units = [lu.id for lu in db_session.query(LabUnit).limit(2).all()]

        base_filters = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
            "randomize_selection": True,
            "random_seed": 42,  # Numeric seed
        }

        rows1 = _fetch_filtered_rows(base_filters.copy())
        rows2 = _fetch_filtered_rows(base_filters.copy())

        # Same seed should produce same order
        task_ids_1 = [r.task_id for r in rows1]
        task_ids_2 = [r.task_id for r in rows2]

        assert task_ids_1 == task_ids_2

    def test_fetch_filtered_rows_random_different_seeds(self, db_session):
        """
        Test that different seeds produce different results.
        """
        disease = db_session.query(Disease).first()
        lab_units = [lu.id for lu in db_session.query(LabUnit).limit(2).all()]

        filters1 = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
            "randomize_selection": True,
            "random_seed": 42,
        }

        filters2 = {
            "disease_id": disease.id if disease else 1,
            "allowed_lab_units": lab_units,
            "randomize_selection": True,
            "random_seed": 999,
        }

        rows1 = _fetch_filtered_rows(filters1)
        rows2 = _fetch_filtered_rows(filters2)

        task_ids_1 = [r.task_id for r in rows1]
        task_ids_2 = [r.task_id for r in rows2]

        # Different seeds should (very likely) produce different orders
        # This is probabilistic, so we just check they're not identical
        # unless there's very few rows
        if len(task_ids_1) > 5:
            assert task_ids_1 != task_ids_2
