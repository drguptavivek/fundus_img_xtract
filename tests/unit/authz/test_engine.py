from authz import AuthzActor, GrantSource, RelationshipGrant, ResourceRef, authorize


def test_upload_create_requires_upload_profile_relationship() -> None:
    actor = AuthzActor(id=1, roles=frozenset({"fileUploader"}), hospital_id=10)
    upload_selection = ResourceRef(
        type="upload_selection",
        attributes={
            "project_id": 20,
            "lab_unit_id": 30,
            "disease_id": 40,
            "camera_id": 50,
            "area_id": 60,
            "upload_kind": "direct_image",
        },
    )
    matching_profile = RelationshipGrant(
        source=GrantSource.UPLOAD_PROFILE,
        attributes={
            "project_id": 20,
            "lab_unit_id": 30,
            "disease_ids": frozenset({40}),
            "camera_ids": frozenset({50}),
            "area_ids": frozenset({60}),
            "upload_kinds": frozenset({"direct_image"}),
        },
    )

    allowed = authorize(actor, "upload.direct.create", upload_selection, grants=[matching_profile])
    denied_without_profile = authorize(actor, "upload.direct.create", upload_selection, grants=[])
    denied_with_site_admin_scope = authorize(
        AuthzActor(id=2, roles=frozenset({"local_admin"}), hospital_id=10),
        "upload.direct.create",
        upload_selection,
        grants=[RelationshipGrant(source=GrantSource.HOSPITAL_SCOPE, hospital_id=10)],
    )

    assert allowed.allowed is True
    assert allowed.grant_source == GrantSource.UPLOAD_PROFILE
    assert denied_without_profile.allowed is False
    assert denied_without_profile.reason == "missing_relationship"
    assert denied_with_site_admin_scope.allowed is False
    assert denied_with_site_admin_scope.reason == "missing_role"


def test_grading_submit_requires_matching_slot_relationship() -> None:
    actor = AuthzActor(id=1, roles=frozenset({"resident"}), hospital_id=10)
    task = ResourceRef(
        type="grading_task",
        id=100,
        attributes={"disease_id": 40, "lab_unit_id": 30},
    )
    resident_slot = RelationshipGrant(
        source=GrantSource.GRADING_SLOT,
        lab_unit_id=30,
        attributes={
            "disease_id": 40,
            "can_grade_resident": True,
            "can_grade_resident2": False,
            "can_arbitrate": False,
        },
    )
    wrong_slot = RelationshipGrant(
        source=GrantSource.GRADING_SLOT,
        lab_unit_id=31,
        attributes={"disease_id": 40, "can_grade_resident": True},
    )

    allowed = authorize(actor, "grading.resident.submit", task, grants=[resident_slot])
    denied = authorize(actor, "grading.resident.submit", task, grants=[wrong_slot])

    assert allowed.allowed is True
    assert allowed.grant_source == GrantSource.GRADING_SLOT
    assert denied.allowed is False
    assert denied.reason == "missing_relationship"


def test_general_actions_accept_lab_unit_hospital_or_admin_scope() -> None:
    encounter = ResourceRef(
        type="encounter",
        id=200,
        attributes={"hospital_id": 10, "lab_unit_id": 30},
    )

    site_admin_decision = authorize(
        AuthzActor(id=1, roles=frozenset({"local_admin"}), hospital_id=10),
        "analytics.encounters.view",
        encounter,
        grants=[RelationshipGrant(source=GrantSource.HOSPITAL_SCOPE, hospital_id=10)],
    )
    data_manager_decision = authorize(
        AuthzActor(id=2, roles=frozenset({"data_manager"}), hospital_id=10),
        "analytics.encounters.view",
        encounter,
        grants=[RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=30)],
    )
    admin_decision = authorize(
        AuthzActor(id=3, roles=frozenset({"admin"}), hospital_id=None),
        "analytics.encounters.view",
        encounter,
        grants=[RelationshipGrant(source=GrantSource.ADMIN_GLOBAL)],
    )
    denied_wrong_lab = authorize(
        AuthzActor(id=4, roles=frozenset({"data_manager"}), hospital_id=10),
        "analytics.encounters.view",
        encounter,
        grants=[RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=31)],
    )

    assert site_admin_decision.allowed is True
    assert site_admin_decision.grant_source == GrantSource.HOSPITAL_SCOPE
    assert data_manager_decision.allowed is True
    assert data_manager_decision.grant_source == GrantSource.LAB_UNIT_ASSIGNMENT
    assert admin_decision.allowed is True
    assert admin_decision.grant_source == GrantSource.ADMIN_GLOBAL
    assert denied_wrong_lab.allowed is False
    assert denied_wrong_lab.reason == "missing_relationship"


def test_verification_actions_are_general_scoped_actions() -> None:
    direct_upload = ResourceRef(
        type="direct_image_upload",
        id=300,
        attributes={"hospital_id": 10, "lab_unit_id": 30},
    )
    encounter = ResourceRef(
        type="encounter",
        id=400,
        attributes={"hospital_id": 10, "lab_unit_id": 30},
    )
    data_manager = AuthzActor(id=1, roles=frozenset({"data_manager"}), hospital_id=10)
    site_admin = AuthzActor(id=2, roles=frozenset({"local_admin"}), hospital_id=10)

    direct_decision = authorize(
        data_manager,
        "verification.direct.update",
        direct_upload,
        grants=[RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=30)],
    )
    remidio_decision = authorize(
        site_admin,
        "verification.remidio.update",
        encounter,
        grants=[RelationshipGrant(source=GrantSource.HOSPITAL_SCOPE, hospital_id=10)],
    )
    pregraded_decision = authorize(
        data_manager,
        "verification.pregraded.update",
        direct_upload,
        grants=[RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=30)],
    )

    assert direct_decision.allowed is True
    assert remidio_decision.allowed is True
    assert pregraded_decision.allowed is True
