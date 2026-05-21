from contextlib import contextmanager
from uuid import uuid4

from models import Hospital, LabUnit, User
from upload_metadata import service
from upload_metadata.service import FieldDefinitionInput, create_field_definition, list_field_definitions


def test_upload_metadata_field_definition_create_and_list(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(service.db_transaction_manager, "transaction_scope", use_test_session)
    suffix = uuid4().hex[:8]
    user = User(username=f"metadata_manager_{suffix}", full_name="Metadata Manager", password_hash="x", is_active=True)
    hospital = Hospital(name=f"Metadata Hospital {suffix}")
    lab = LabUnit(name=f"Metadata Lab {suffix}", hospital=hospital)
    user.lab_units.append(lab)
    db_session.add_all([user, hospital, lab])
    db_session.flush()
    monkeypatch.setattr(service, "manager_lab_unit_ids", lambda user_id: {lab.id} if user_id == user.id else set())

    result = create_field_definition(
        user.id,
        FieldDefinitionInput(
            scope="image",
            key=f"laterality_{suffix}",
            label="Eye Laterality",
            sctid="123456789",
            field_type="select",
            selection_mode="single",
            options_json=["OD", "OS"],
            required_for_verification_default=True,
        ),
    )

    assert result.success is True
    fields = list_field_definitions(user.id)
    created = next(field for field in fields if field["key"] == f"laterality_{suffix}")
    assert created["scope"] == "image"
    assert created["sctid"] == "123456789"
    assert created["options"] == [{"value": "OD", "label": "OD"}, {"value": "OS", "label": "OS"}]


def test_upload_metadata_field_definition_rejects_invalid_scope():
    result = service.validate_field_definition_input(
        FieldDefinitionInput(
            scope="encounter_set",
            key="foo",
            label="Foo",
            field_type="text",
        )
    )

    assert result == "Field scope must be patient, encounter, image, document, or upload."


def test_upload_metadata_field_definition_key_is_global(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(service.db_transaction_manager, "transaction_scope", use_test_session)
    suffix = uuid4().hex[:8]
    user = User(username=f"metadata_manager_global_{suffix}", full_name="Metadata Manager", password_hash="x", is_active=True)
    hospital = Hospital(name=f"Metadata Hospital Global {suffix}")
    lab = LabUnit(name=f"Metadata Lab Global {suffix}", hospital=hospital)
    user.lab_units.append(lab)
    db_session.add_all([user, hospital, lab])
    db_session.flush()
    monkeypatch.setattr(service, "manager_lab_unit_ids", lambda user_id: {lab.id} if user_id == user.id else set())

    shared_key = f"shared_field_{suffix}"
    first = create_field_definition(
        user.id,
        FieldDefinitionInput(scope="patient", key=shared_key, label="Patient Shared Field", field_type="text"),
    )
    second = create_field_definition(
        user.id,
        FieldDefinitionInput(scope="image", key=shared_key, label="Image Shared Field", field_type="text"),
    )

    assert first.success is True
    assert second.success is False
    assert second.message == "Upload metadata field key already exists."
