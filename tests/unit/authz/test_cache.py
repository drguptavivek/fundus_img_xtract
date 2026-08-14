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
