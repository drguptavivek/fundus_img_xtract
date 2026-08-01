from uuid import uuid4

from tests.conftest import create_authenticated_client
from tests.helpers.factories import UserFactory


def test_iitk_admin_page_and_partial_render_directly(app, db_session, core_test_data):
    admin_user = UserFactory.create_admin(db_session, username=f"iitk_admin_{uuid4().hex[:8]}")
    client = create_authenticated_client(app, admin_user, db_session)

    page = client.get("/admin/iitk")
    partial = client.get("/admin/iitk/workspace")

    assert page.status_code == 200
    assert partial.status_code == 200
    assert b"IITK API Integration" in page.data
    assert b"API token" in partial.data
    assert b"csrf_token" in partial.data
