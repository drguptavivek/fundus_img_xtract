import json

from data_authorization.models import LAB_UNIT_SCOPE, ProjectRoleGrant
from datasets.authorization import (
    can_export_dataset,
    can_manage_dataset,
    can_share_dataset,
    can_view_dataset,
    dataset_creation_lab_unit_ids,
)
from models import (
    CuratedDataset,
    CuratedDatasetItem,
    Project,
    ProjectLabUnit,
    Role,
    User,
)
from tests.helpers.factories import UserFactory
from tests.helpers.test_factories import TestDataFactory


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_legacy_admin_managed_dataset_remains_active_but_admin_only(db_session, core_test_data):
    disease = db_session.merge(core_test_data["glaucoma"])
    actor = User(username="legacy_dataset_actor", password_hash="x", is_active=True)
    actor.roles.append(_role(db_session, "dataset_creator"))
    dataset = CuratedDataset(
        name="Legacy classical",
        purpose="Legacy",
        filters_json=json.dumps({"allowed_lab_units": [core_test_data["lab_a1"].id]}),
        disease_id=disease.id,
        admin_managed=True,
        context_kind="classical",
    )
    admin = UserFactory.create_admin(db_session, username="legacy_dataset_admin")
    db_session.add_all([actor, dataset])
    db_session.flush()

    assert not can_manage_dataset(db_session, user=actor, dataset=dataset)
    assert can_manage_dataset(db_session, user=admin, dataset=dataset)


def test_classical_dataset_requires_every_task_in_classical_scope(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    actor = User(
        username="classical_dataset_creator",
        password_hash="x",
        is_active=True,
        roles=[_role(db_session, "dataset_creator")],
        lab_units=[lab],
    )
    task = TestDataFactory.create_grading_task(db_session, lab_unit_id=lab.id, disease_id=disease.id)
    dataset = CuratedDataset(
        name="Classical scoped",
        purpose="Scope test",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=disease.id,
        created_by_user_id=None,
        context_kind="classical",
        admin_managed=False,
    )
    db_session.add_all([actor, dataset])
    db_session.flush()
    dataset.created_by_user_id = actor.id
    db_session.add(CuratedDatasetItem(dataset_id=dataset.id, task_id=task.id, include_in_export=True))
    db_session.flush()

    assert can_manage_dataset(db_session, user=actor, dataset=dataset)
    other_project = Project(title="Other dataset project", code="OTHER_DATASET", active=True)
    db_session.add(other_project)
    db_session.flush()
    task.project_id = other_project.id
    db_session.flush()
    assert not can_manage_dataset(db_session, user=actor, dataset=dataset)


def test_site_dataset_creator_needs_create_and_share_flags(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    project = Project(title="Dataset site project", code="DATASET_SITE", active=True)
    actor = User(username="site_dataset_creator", password_hash="x", is_active=True)
    db_session.add_all([project, actor])
    db_session.flush()
    role = _role(db_session, "dataset_creator")
    db_session.add_all([
        ProjectLabUnit(
            project_id=project.id,
            lab_unit_id=lab.id,
            active=True,
            sites_can_create_datasets=True,
            sites_can_share_datasets=False,
        ),
        ProjectRoleGrant(
            project_id=project.id,
            user_id=actor.id,
            role_id=role.id,
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
            active=True,
        ),
    ])
    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab.id)
    encounter.project_id = project.id
    db_session.flush()
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab.id,
        filename="project_dataset.jpg",
    )
    encounter_file.project_id = project.id
    db_session.flush()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        encounter_file_id=encounter_file.id,
    )
    task.project_id = project.id
    dataset = CuratedDataset(
        name="Project site dataset",
        purpose="Site flags",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=disease.id,
        created_by_user_id=actor.id,
        context_kind="project",
        project_id=project.id,
        admin_managed=False,
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(CuratedDatasetItem(dataset_id=dataset.id, task_id=task.id, include_in_export=True))
    db_session.flush()

    assert dataset_creation_lab_unit_ids(
        db_session, user=actor, context_kind="project", project_id=project.id
    ) == frozenset({lab.id})
    assert can_manage_dataset(db_session, user=actor, dataset=dataset)
    assert not can_share_dataset(db_session, user=actor, dataset=dataset)


def test_dataset_export_requires_export_role_instead_of_curation_role(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    actor = User(
        username="dataset_export_scope",
        password_hash="x",
        is_active=True,
        roles=[_role(db_session, "dataset_creator")],
        lab_units=[lab],
    )
    task = TestDataFactory.create_grading_task(
        db_session, lab_unit_id=lab.id, disease_id=disease.id
    )
    dataset = CuratedDataset(
        name="Export role gate",
        purpose="Export scope",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=disease.id,
        created_by_user_id=actor.id,
        context_kind="classical",
        is_finalized=True,
    )
    db_session.add_all([actor, dataset])
    db_session.flush()
    db_session.add(CuratedDatasetItem(dataset_id=dataset.id, task_id=task.id))
    db_session.flush()

    assert not can_export_dataset(db_session, user=actor, dataset=dataset)
    actor.roles.append(_role(db_session, "data_exporter"))
    db_session.flush()
    assert can_export_dataset(db_session, user=actor, dataset=dataset)


def test_project_pii_exporter_can_export_without_data_exporter(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_a1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    project = Project(title="PII dataset export", code="PII_DATASET_EXPORT", active=True)
    actor = User(
        username="project_pii_dataset_export",
        password_hash="x",
        is_active=True,
        roles=[_role(db_session, "pii_exporter")],
    )
    db_session.add_all([project, actor])
    db_session.flush()
    db_session.add_all(
        [
            ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True),
            ProjectRoleGrant(
                project_id=project.id,
                user_id=actor.id,
                role_id=_role(db_session, "pii_exporter").id,
                scope_type="project",
                active=True,
            ),
        ]
    )
    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab.id)
    encounter.project_id = project.id
    db_session.flush()
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab.id,
        filename="project_pii_dataset.jpg",
    )
    encounter_file.project_id = project.id
    db_session.flush()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        encounter_file_id=encounter_file.id,
    )
    task.project_id = project.id
    dataset = CuratedDataset(
        name="Project PII export",
        purpose="Export scope",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=disease.id,
        created_by_user_id=actor.id,
        context_kind="project",
        project_id=project.id,
        is_finalized=True,
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(CuratedDatasetItem(dataset_id=dataset.id, task_id=task.id))
    db_session.flush()

    assert can_export_dataset(db_session, user=actor, dataset=dataset)


def test_admin_export_still_denies_invalid_dataset_task_lineage(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_a1"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    dr = db_session.merge(core_test_data["dr"])
    admin = UserFactory.create_admin(db_session, username="invalid_lineage_admin")
    wrong_disease_task = TestDataFactory.create_grading_task(
        db_session, lab_unit_id=lab.id, disease_id=dr.id
    )
    dataset = CuratedDataset(
        name="Invalid lineage export",
        purpose="Fail closed",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=glaucoma.id,
        context_kind="classical",
        is_finalized=True,
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(
        CuratedDatasetItem(dataset_id=dataset.id, task_id=wrong_disease_task.id)
    )
    db_session.flush()

    assert not can_export_dataset(db_session, user=admin, dataset=dataset)


def test_admin_view_denies_task_with_broken_source_hospital_lineage(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_a1"])
    other_lab = db_session.merge(core_test_data["lab_b1"])
    disease = db_session.merge(core_test_data["glaucoma"])
    admin = UserFactory.create_admin(db_session, username="invalid_view_lineage_admin")
    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab.id)
    encounter_file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=lab.id,
        filename="invalid_view_lineage.jpg",
    )
    encounter_file.hospital_id = other_lab.hospital_id
    db_session.flush()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab.id,
        disease_id=disease.id,
        encounter_file_id=encounter_file.id,
    )
    dataset = CuratedDataset(
        name="Invalid lineage view",
        purpose="Fail closed",
        filters_json=json.dumps({"allowed_lab_units": [lab.id]}),
        disease_id=disease.id,
        context_kind="classical",
        is_finalized=True,
    )
    db_session.add(dataset)
    db_session.flush()
    db_session.add(CuratedDatasetItem(dataset_id=dataset.id, task_id=task.id))
    db_session.flush()

    assert not can_view_dataset(db_session, user=admin, dataset=dataset)
