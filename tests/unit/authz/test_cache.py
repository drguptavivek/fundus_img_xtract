from types import SimpleNamespace

from authz import AuthzDecision, GrantSource, ResourceRef
from authz import cache as authz_cache


class FakeCache:
    def __init__(self):
        self.values = {}
        self.timeouts = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, timeout=None):
        self.values[key] = value
        self.timeouts[key] = timeout

    def delete(self, key):
        self.values.pop(key, None)


class FailingCache:
    def get(self, _key):
        raise ConnectionError("redis unavailable")

    def set(self, _key, _value, timeout=None):
        raise ConnectionError("redis unavailable")

    def delete(self, _key):
        raise ConnectionError("redis unavailable")


def test_media_decision_cache_uses_900_second_ttl_and_shares_thumbnail_key(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(authz_cache, "cache", fake)
    resource = ResourceRef(
        type="encounter_file",
        id="uuid-1",
        attributes={"project_id": None, "hospital_id": 10, "lab_unit_id": 20},
    )
    decision = AuthzDecision.allow("media.image.view", GrantSource.LAB_UNIT_ASSIGNMENT)

    authz_cache.set_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
        decision=decision,
    )

    assert list(fake.timeouts.values()) == [900]
    cached = authz_cache.get_cached_decision(
        user_id=1,
        action="media.thumbnail.view",
        resource=resource,
    )
    assert cached is not None and cached.allowed is True


def test_invalid_hmac_is_not_cached_and_success_is_bounded_by_expiry(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(authz_cache, "cache", fake)
    monkeypatch.setattr(authz_cache.time, "time", lambda: 1_000)

    authz_cache.set_hmac_validation(
        token_hash="digest",
        media_uuid="uuid-1",
        hospital_id=10,
        expires=1_200,
    )

    assert list(fake.values.values()) == [True]
    assert list(fake.timeouts.values()) == [200]
    assert authz_cache.get_hmac_validation(
        token_hash="wrong",
        media_uuid="uuid-1",
        hospital_id=10,
        expires=1_200,
    ) is False


def test_expired_hmac_validation_is_not_cached(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(authz_cache, "cache", fake)
    monkeypatch.setattr(authz_cache.time, "time", lambda: 1_000)

    authz_cache.set_hmac_validation(
        token_hash="digest",
        media_uuid="uuid-1",
        hospital_id=10,
        expires=1_000,
    )

    assert fake.values == {}


def test_cache_outage_falls_back_without_returning_an_allow(monkeypatch):
    monkeypatch.setattr(authz_cache, "cache", FailingCache())
    resource = ResourceRef(type="encounter_file", id="uuid-1")

    cached = authz_cache.get_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
    )
    authz_cache.set_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
        decision=AuthzDecision.allow(
            "media.image.view",
            GrantSource.LAB_UNIT_ASSIGNMENT,
        ),
    )

    assert cached is None
    assert authz_cache.get_hmac_validation(
        token_hash="digest",
        media_uuid="uuid-1",
        hospital_id=10,
        expires=2_000,
    ) is False


def test_project_epoch_bump_makes_prior_decision_unreachable(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(authz_cache, "cache", fake)
    monkeypatch.setattr(authz_cache.time, "time_ns", lambda: 123456)
    resource = ResourceRef(
        type="encounter_file",
        id="uuid-1",
        attributes={"project_id": 22, "hospital_id": 10, "lab_unit_id": 20},
    )
    authz_cache.set_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
        decision=AuthzDecision.allow(
            "media.image.view",
            GrantSource.PROJECT_ROLE,
        ),
    )
    assert authz_cache.get_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
    ) is not None

    authz_cache._bump_epoch("project", 22)

    assert authz_cache.get_cached_decision(
        user_id=1,
        action="media.image.view",
        resource=resource,
    ) is None


def test_pending_invalidations_apply_only_after_commit(monkeypatch):
    bumped = []
    fake = FakeCache()
    monkeypatch.setattr(authz_cache, "cache", fake)
    monkeypatch.setattr(
        authz_cache,
        "_bump_epoch",
        lambda kind, value: bumped.append((kind, value)),
    )
    rolled_back = SimpleNamespace(info={})
    authz_cache.schedule_authorization_invalidation(
        rolled_back,
        user_ids=[3],
        project_ids=[4],
        hospital_ids=[5],
    )
    authz_cache._discard_authorization_changes(rolled_back)
    assert bumped == []

    committed = SimpleNamespace(info={})
    authz_cache.schedule_authorization_invalidation(
        committed,
        user_ids=[3],
        project_ids=[4],
        hospital_ids=[5],
    )
    authz_cache._apply_authorization_changes(committed)

    assert bumped == [
        ("user", 3),
        ("project", 4),
        ("hospital-signing", 5),
    ]
