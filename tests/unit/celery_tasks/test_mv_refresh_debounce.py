import pytest
from celery.exceptions import MaxRetriesExceededError, Retry

from celery_tasks.tasks import mv_tasks


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


def test_debounce_queues_only_first_refresh(monkeypatch):
    client = FakeRedis()
    queued = []
    monkeypatch.setattr(mv_tasks, "_redis_client", lambda: client)
    monkeypatch.setattr(
        mv_tasks.refresh_image_listing_v2_task,
        "apply_async",
        lambda **kwargs: queued.append(kwargs),
    )

    assert mv_tasks.queue_debounced_image_listing_refresh(1) is True
    assert mv_tasks.queue_debounced_image_listing_refresh(1) is False
    assert len(queued) == 1
    assert queued[0]["kwargs"]["disease_id"] == 1
    assert queued[0]["kwargs"]["scheduled_generation"] == client.values[
        "review-mv-refresh:scheduled:1"
    ]
    assert queued[0]["countdown"] == mv_tasks._DEBOUNCE_SECONDS


def test_stale_queued_refresh_is_skipped_after_lock_generation_changes(monkeypatch):
    client = FakeRedis()
    client.values["review-mv-refresh:dirty:7"] = "new-generation"
    client.values["review-mv-refresh:scheduled:7"] = "new-generation"
    monkeypatch.setattr(mv_tasks, "build_task_app", lambda: object())
    monkeypatch.setattr(mv_tasks, "_redis_client", lambda: client)
    refresh_calls = []
    monkeypatch.setattr(
        mv_tasks,
        "refresh_image_listing_mv_for_disease",
        lambda *args, **kwargs: refresh_calls.append((args, kwargs)),
    )

    result = mv_tasks.refresh_image_listing_v2_task.run(
        disease_id=7,
        schedule_time="review_submission",
        scheduled_generation="old-generation",
    )

    assert result["skipped"] == 1
    assert result["refreshed"] == 0
    assert refresh_calls == []


def test_disease_refresh_error_is_raised_as_retry(monkeypatch):
    client = FakeRedis()
    client.values["review-mv-refresh:dirty:7"] = "generation"
    client.values["review-mv-refresh:scheduled:7"] = "generation"
    monkeypatch.setattr(mv_tasks, "build_task_app", lambda: object())
    monkeypatch.setattr(mv_tasks, "_redis_client", lambda: client)
    monkeypatch.setattr(
        mv_tasks,
        "refresh_image_listing_mv_for_disease",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("refresh failed")),
    )

    retry_calls = []

    def retry(**kwargs):
        retry_calls.append(kwargs)
        raise Retry()

    monkeypatch.setattr(mv_tasks.refresh_image_listing_v2_task, "retry", retry)

    with pytest.raises(Retry):
        mv_tasks.refresh_image_listing_v2_task.run(
            disease_id=7,
            schedule_time="review_submission",
        )

    assert len(retry_calls) == 1
    assert isinstance(retry_calls[0]["exc"], RuntimeError)
    assert retry_calls[0]["countdown"] == 30


def test_exhausted_refresh_retry_releases_disease_lock(monkeypatch):
    client = FakeRedis()
    dirty_key = "review-mv-refresh:dirty:7"
    lock_key = "review-mv-refresh:scheduled:7"
    client.values[dirty_key] = "generation"
    client.values[lock_key] = "generation"
    monkeypatch.setattr(mv_tasks, "build_task_app", lambda: object())
    monkeypatch.setattr(mv_tasks, "_redis_client", lambda: client)
    monkeypatch.setattr(
        mv_tasks,
        "refresh_image_listing_mv_for_disease",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("refresh failed")),
    )
    monkeypatch.setattr(
        mv_tasks.refresh_image_listing_v2_task,
        "retry",
        lambda **kwargs: (_ for _ in ()).throw(MaxRetriesExceededError()),
    )

    with pytest.raises(MaxRetriesExceededError):
        mv_tasks.refresh_image_listing_v2_task.run(disease_id=7)

    assert lock_key not in client.values
