"""Version-stamped caching and its invalidation.

The security-relevant case is the scope fingerprint: a cache that outlives an
authorization change would keep serving patient data to someone whose grant was
revoked.
"""
from field_workbench import cache as field_cache


def test_bumping_a_project_changes_every_derived_key():
    before = field_cache.queue_cache_key(
        project_id=4242, date_value="2026-08-20", user_id=7, scope_fp="abc"
    )
    field_cache.bump_project(4242)
    after = field_cache.queue_cache_key(
        project_id=4242, date_value="2026-08-20", user_id=7, scope_fp="abc"
    )
    assert before != after


def test_bumping_an_encounter_also_invalidates_the_project_queue():
    queue_before = field_cache.queue_cache_key(
        project_id=4243, date_value="2026-08-20", user_id=7, scope_fp="abc"
    )
    detail_before = field_cache.detail_cache_key(
        encounter_id=99, project_id=4243, user_id=7, scope_fp="abc"
    )

    field_cache.bump_encounter(99, 4243)

    assert queue_before != field_cache.queue_cache_key(
        project_id=4243, date_value="2026-08-20", user_id=7, scope_fp="abc"
    )
    assert detail_before != field_cache.detail_cache_key(
        encounter_id=99, project_id=4243, user_id=7, scope_fp="abc"
    )


def test_different_users_never_share_a_cache_entry():
    first = field_cache.queue_cache_key(
        project_id=4244, date_value="2026-08-20", user_id=1, scope_fp="abc"
    )
    second = field_cache.queue_cache_key(
        project_id=4244, date_value="2026-08-20", user_id=2, scope_fp="abc"
    )
    assert first != second


def test_a_changed_grant_produces_a_different_key():
    """The regression test for scope_fp: revoking access must not serve stale rows."""
    wide = field_cache.scope_fingerprint(["field_optometrist"], [1, 2], [])
    narrowed = field_cache.scope_fingerprint(["field_optometrist"], [1], [])
    revoked_role = field_cache.scope_fingerprint([], [1, 2], [])

    assert wide != narrowed
    assert wide != revoked_role

    assert field_cache.queue_cache_key(
        project_id=4245, date_value="2026-08-20", user_id=1, scope_fp=wide
    ) != field_cache.queue_cache_key(
        project_id=4245, date_value="2026-08-20", user_id=1, scope_fp=narrowed
    )


def test_fingerprint_is_order_independent():
    assert field_cache.scope_fingerprint(
        ["b", "a"], [2, 1], []
    ) == field_cache.scope_fingerprint(["a", "b"], [1, 2], [])
