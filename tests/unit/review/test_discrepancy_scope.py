from uuid import uuid4

from models import GradingTask, Project
from review.discrepancy_scope import list_discrepancy_filter_options
from tests.helpers.factories import ImageFactory, UserFactory


def _project_task(db_session, *, project, lab, disease, core_test_data, uploader):
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=lab.hospital_id,
        lab_unit_id=lab.id,
        user_id=uploader.id,
        disease_id=disease.id,
        camera_id=core_test_data["camera"].id,
        area_id=core_test_data["area"].id,
    )
    image.project_id = project.id
    task = GradingTask(
        uuid=str(uuid4()),
        direct_image_upload_id=image.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="final",
    )
    db_session.add(task)
    db_session.flush()


def test_project_options_restrict_diseases_and_labs_to_actual_tasks(
    db_session, core_test_data
):
    admin = UserFactory.create_admin(
        db_session,
        username=f"scope-admin-{uuid4().hex[:8]}",
    )
    first_project = Project(
        title=f"First review project {uuid4()}",
        code=f"FIRST-{uuid4().hex[:8]}",
    )
    second_project = Project(
        title=f"Second review project {uuid4()}",
        code=f"SECOND-{uuid4().hex[:8]}",
    )
    db_session.add_all([first_project, second_project])
    db_session.flush()
    first_lab = db_session.merge(core_test_data["lab_a1"])
    second_lab = db_session.merge(core_test_data["lab_b1"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    dr = db_session.merge(core_test_data["dr"])
    _project_task(
        db_session,
        project=first_project,
        lab=first_lab,
        disease=glaucoma,
        core_test_data=core_test_data,
        uploader=admin,
    )
    _project_task(
        db_session,
        project=second_project,
        lab=second_lab,
        disease=dr,
        core_test_data=core_test_data,
        uploader=admin,
    )

    options = list_discrepancy_filter_options(
        db_session,
        user=admin,
        allowed_lab_unit_ids={first_lab.id, second_lab.id},
        project_id=first_project.id,
    )

    assert {project.id for project in options.projects} == {
        first_project.id,
        second_project.id,
    }
    assert [(disease.id, disease.name) for disease in options.diseases] == [
        (glaucoma.id, glaucoma.name)
    ]
    assert [(lab.id, lab.hospital_id) for lab in options.lab_units] == [
        (first_lab.id, first_lab.hospital_id)
    ]
