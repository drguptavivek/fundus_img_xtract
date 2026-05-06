from flask import Flask

from utils import cache_invalidation


class FakeRedisClient:
    def __init__(self, keys):
        self.keys = set(keys)

    def scan_iter(self, match, count=1000):
        prefix = match.removesuffix("*")
        for key in list(self.keys):
            if key.startswith(prefix):
                yield key

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.keys:
                self.keys.remove(key)
                deleted += 1
        return deleted


class FakeRedisBackend:
    key_prefix = "fim:cache:"

    def __init__(self, keys):
        self._write_client = FakeRedisClient(keys)


class FakeLocalBackend:
    key_prefix = "fim:cache:"

    def __init__(self, keys):
        self._cache = {key: "value" for key in keys}


class FakeCache:
    def __init__(self, backend):
        self.cache = backend


def test_delete_cache_keys_by_route_prefix_deletes_only_discrepancy_redis_keys(monkeypatch):
    app = Flask(__name__)
    backend = FakeRedisBackend(
        {
            "fim:cache:discrepancy-review:v2:13:disease_id=1",
            "fim:cache:discrepancy-review:v2:14:disease_id=1",
            "fim:cache:other-route:v1",
        }
    )
    monkeypatch.setattr(cache_invalidation, "cache", FakeCache(backend))

    with app.app_context():
        deleted = cache_invalidation.delete_cache_keys_by_route_prefix("discrepancy-review:")

    assert deleted == 2
    assert backend._write_client.keys == {"fim:cache:other-route:v1"}


def test_delete_cache_keys_by_route_prefix_handles_local_cache_backend(monkeypatch):
    app = Flask(__name__)
    backend = FakeLocalBackend(
        [
            "fim:cache:discrepancy-review:v2:13:disease_id=1",
            "fim:cache:other-route:v1",
        ]
    )
    monkeypatch.setattr(cache_invalidation, "cache", FakeCache(backend))

    with app.app_context():
        deleted = cache_invalidation.delete_cache_keys_by_route_prefix("discrepancy-review:")

    assert deleted == 1
    assert list(backend._cache.keys()) == ["fim:cache:other-route:v1"]
