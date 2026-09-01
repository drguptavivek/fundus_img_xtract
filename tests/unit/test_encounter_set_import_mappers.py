from contextlib import contextmanager

from encounter_set_types import import_mappers
from encounter_set_types.import_mappers import MapperInput
from encounter_set_types.models import EncounterSetImportMapperAudit, EncounterSetImportMapperRevision, EncounterSetType
from models import EncounterSetImage, PatientEncounters
from tests.unit.test_encounter_set_types import encounter_set_type_scope  # noqa: F401


def _dto(name="Corneal opacity mapper"):
    return MapperInput(
        name=name,
        source_headers=["instance_id", "participant_id"],
        mapping={
            "column_mappings": [{"source_column": "participant_id", "canonical_key": "project_participant_id", "scope": "patient"}],
            "reserved_columns": [{"source_column": "instance_id", "role": "encounter_identity", "canonical_key": "project_unique_id_patient"}],
            "excluded_columns": [], "defaults": {}, "value_mappings": {},
        },
    )


def test_mapper_revision_lifecycle_is_immutable_and_audited(db_session, encounter_set_type_scope, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(import_mappers.db_transaction_manager, "transaction_scope", use_test_session)
    monkeypatch.setattr(import_mappers, "manager_lab_unit_ids", lambda _user_id: {encounter_set_type_scope["lab_id"]})
    encounter_type = EncounterSetType(
        name="Mapper test type", code=f"mapper_{encounter_set_type_scope['suffix']}",
        metadata_schema_json={"fields": [{"key": "project_participant_id", "scope": "patient", "required_at_upload": True}]},
        asset_rules_json={}, created_by_user_id=encounter_set_type_scope["admin_user"].id,
    )
    db_session.add(encounter_type); db_session.flush()
    user_id = encounter_set_type_scope["admin_user"].id

    before_clinical = (db_session.query(PatientEncounters).count(), db_session.query(EncounterSetImage).count())
    created = import_mappers.create_draft(user_id, encounter_type.id, _dto())
    revision_id = created.payload["mapper_revision"]["id"]
    assert created.status_code == 201
    assert import_mappers.finalize(user_id, revision_id).success
    immutable = import_mappers.update_draft(user_id, revision_id, _dto("changed"))
    assert immutable.status_code == 409
    assert import_mappers.delete_draft(user_id, revision_id).status_code == 409

    cloned = import_mappers.clone(user_id, revision_id)
    assert cloned.payload["mapper_revision"]["revision"] == 2
    assert cloned.payload["mapper_revision"]["status"] == "draft"
    clone_id = cloned.payload["mapper_revision"]["id"]
    assert import_mappers.delete_draft(user_id, clone_id).success
    assert import_mappers.retire(user_id, revision_id).payload["mapper_revision"]["status"] == "retired"
    assert [row.action for row in db_session.query(EncounterSetImportMapperAudit).order_by(EncounterSetImportMapperAudit.id)] == [
        "created", "finalized", "cloned", "deleted", "retired"
    ]
    assert db_session.get(EncounterSetImportMapperRevision, revision_id).status == "retired"
    assert (db_session.query(PatientEncounters).count(), db_session.query(EncounterSetImage).count()) == before_clinical


def test_mapper_api_is_admin_only(client, encounter_set_type_scope):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(encounter_set_type_scope["user"].id)
        sess["_fresh"] = True
    response = client.get("/api/encounter-set-types/999/import-mappers")
    assert response.status_code == 403


def test_mapper_mutation_requires_csrf_when_enabled(app, client, encounter_set_type_scope, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(encounter_set_type_scope["admin_user"].id)
        sess["_fresh"] = True
    response = client.post("/api/encounter-set-types/999/import-mappers", json={})
    assert response.status_code == 400
