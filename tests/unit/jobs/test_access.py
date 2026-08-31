from __future__ import annotations

from jobs.access import job_visible_to_actor
from models import Job


def _job(*, owner_id=1, lab_unit_id=None, upload_type="processing"):
    return Job(
        token=f"job-{owner_id}-{lab_unit_id}-{upload_type}",
        uploader_user_id=owner_id,
        lab_unit_id=lab_unit_id,
        upload_type=upload_type,
    )


def test_null_lab_job_is_owner_or_admin_only():
    job = _job(owner_id=1)

    assert job_visible_to_actor(job, user_id=1, is_admin=False, allowed_lab_unit_ids={2})
    assert job_visible_to_actor(job, user_id=9, is_admin=True, allowed_lab_unit_ids=set())
    assert not job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={2})


def test_ownerless_null_lab_job_is_admin_only():
    job = _job(owner_id=None)

    assert job_visible_to_actor(job, user_id=9, is_admin=True, allowed_lab_unit_ids=set())
    assert not job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={2})


def test_non_null_job_uses_exact_lab_scope():
    job = _job(owner_id=1, lab_unit_id=2)

    assert job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={2})
    assert not job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={3})


def test_export_job_remains_owner_or_admin_even_with_lab_lineage():
    job = _job(owner_id=1, lab_unit_id=2, upload_type="dataset_export")

    assert job_visible_to_actor(job, user_id=1, is_admin=False, allowed_lab_unit_ids=set())
    assert not job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={2})


def test_classical_lab_assignment_does_not_spill_into_project_job():
    job = _job(owner_id=1, lab_unit_id=2)
    job.project_id = 7

    assert not job_visible_to_actor(job, user_id=9, is_admin=False, allowed_lab_unit_ids={2})
