from models import EncounterSetGradingPackage, PatientEncounters


def test_frozen_record_api_hides_encounter_without_current_allocation(
    client,
    login_user,
    db_session,
    resident_user,
    core_test_data,
    monkeypatch,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    encounter = PatientEncounters(
        name="Scoped grading record",
        patient_id="SCOPED-GRADING-RECORD",
        capture_date="2026-08-14",
        lab_unit_id=lab.id,
        is_set_based=True,
    )
    package = EncounterSetGradingPackage(
        patient_encounter=encounter,
        name="Scoped package",
        code="scoped_package",
        grading_mode="unified",
        state="final",
    )
    db_session.add(package)
    db_session.flush()
    login_user(resident_user.username, "Test@2026")
    checked = []

    def deny(_db, candidate, *, user_id):
        checked.append((candidate.id, user_id))
        return False

    monkeypatch.setattr(
        "api.encounter_set_grading.can_view_package_record",
        deny,
    )

    response = client.get(
        f"/api/encounter-sets/{encounter.uuid}/grading-records"
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "error": "EncounterSet not found.",
    }
    assert checked == [(package.id, resident_user.id)]


def test_frozen_record_api_returns_only_currently_authorized_packages(
    client,
    login_user,
    db_session,
    resident_user,
    core_test_data,
    monkeypatch,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    encounter = PatientEncounters(
        name="Partially scoped grading record",
        patient_id="PARTIAL-SCOPED-GRADING-RECORD",
        capture_date="2026-08-14",
        lab_unit_id=lab.id,
        is_set_based=True,
    )
    packages = [
        EncounterSetGradingPackage(
            patient_encounter=encounter,
            name=code,
            code=code,
            grading_mode="unified",
            state="final",
        )
        for code in ("allowed", "denied")
    ]
    db_session.add_all(packages)
    db_session.flush()
    login_user(resident_user.username, "Test@2026")
    monkeypatch.setattr(
        "api.encounter_set_grading.can_view_package_record",
        lambda _db, candidate, user_id: candidate.code == "allowed",
    )
    monkeypatch.setattr("api.encounter_set_grading.reconcile_package_state", lambda db, package: None)
    monkeypatch.setattr(
        "api.encounter_set_grading.package_record_dto",
        lambda package, viewer_user_id: {"code": package.code},
    )

    response = client.get(f"/api/encounter-sets/{encounter.uuid}/grading-records")

    assert response.status_code == 200
    assert response.get_json()["packages"] == [{"code": "allowed"}]
