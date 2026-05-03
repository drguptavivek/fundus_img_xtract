from types import SimpleNamespace

from authz import AuthzActor, GrantSource
from authz.adapters import (
    actor_from_user,
    admin_global_grant,
    grading_slot_grant,
    hospital_scope_grant,
    lab_unit_assignment_grants,
    upload_profile_grant,
)


def test_actor_from_user_normalizes_roles_and_hospital() -> None:
    user = SimpleNamespace(
        id=10,
        hospital_id=20,
        roles=[SimpleNamespace(name="admin"), SimpleNamespace(name="data_manager")],
    )

    actor = actor_from_user(user)

    assert actor == AuthzActor(id=10, roles=frozenset({"admin", "data_manager"}), hospital_id=20)


def test_general_scope_grants_come_from_admin_hospital_and_lab_units() -> None:
    admin_actor = AuthzActor(id=1, roles=frozenset({"admin"}), hospital_id=None)
    site_actor = AuthzActor(id=2, roles=frozenset({"local_admin"}), hospital_id=10)
    lab_user = SimpleNamespace(lab_units=[SimpleNamespace(id=30), SimpleNamespace(id=31)])

    assert admin_global_grant(admin_actor).source == GrantSource.ADMIN_GLOBAL
    assert hospital_scope_grant(site_actor).hospital_id == 10
    assert [grant.lab_unit_id for grant in lab_unit_assignment_grants(lab_user)] == [30, 31]


def test_upload_profile_adapter_preserves_profile_dimensions() -> None:
    profile = SimpleNamespace(
        project_id=20,
        lab_unit_id=30,
        disease_ids=frozenset({40}),
        camera_ids=frozenset({50}),
        area_ids=frozenset({60}),
        upload_kinds=frozenset({"direct_image"}),
    )

    grant = upload_profile_grant(profile)

    assert grant.source == GrantSource.UPLOAD_PROFILE
    assert grant.attributes["project_id"] == 20
    assert grant.attributes["disease_ids"] == frozenset({40})
    assert grant.attributes["upload_kinds"] == frozenset({"direct_image"})


def test_grading_slot_adapter_preserves_slot_flags() -> None:
    slot = SimpleNamespace(
        disease_id=40,
        lab_unit_id=30,
        can_grade_resident=True,
        can_grade_resident2=False,
        can_arbitrate=True,
    )

    grant = grading_slot_grant(slot)

    assert grant.source == GrantSource.GRADING_SLOT
    assert grant.lab_unit_id == 30
    assert grant.attributes["disease_id"] == 40
    assert grant.attributes["can_grade_resident"] is True
    assert grant.attributes["can_arbitrate"] is True
