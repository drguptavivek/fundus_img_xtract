import json

import pytest

from models import Role, UserDiseaseUnitRole
from tests.helpers.factories import UserFactory


@pytest.mark.integration
class TestUserManagerGradingEligibility:
    @staticmethod
    def _make_user_manager(db_session, user):
        user = db_session.merge(user)
        role = db_session.query(Role).filter_by(name="user_manager").one_or_none()
        if role is None:
            role = Role(name="user_manager")
            db_session.add(role)
            db_session.flush()
        user.roles.append(role)
        db_session.flush()

    def test_user_manager_can_edit_users_in_own_hospital(
        self, auth_client, site_admin_hospital_a, db_session, hospital_data, core_test_data
    ):
        user_a = UserFactory.create_with_hospital(
            db_session,
            role_name="ophthalmologist",
            hospital_id=hospital_data["hospital_a"]["hospital"].id,
            lab_unit_ids=[hospital_data["hospital_a"]["lab_units"][0].id],
            username="eligibility_user_a",
        )

        self._make_user_manager(db_session, site_admin_hospital_a)
        client = auth_client(site_admin_hospital_a)
        response = client.get(f"/admin/grading-eligibility/{user_a.id}")
        assert response.status_code == 200

        payload = [
            {
                "disease_id": core_test_data["glaucoma"].id,
                "lab_unit_id": hospital_data["hospital_a"]["lab_units"][0].id,
                "can_grade_resident": True,
                "can_grade_resident2": False,
                "can_arbitrate": False,
                "active": True,
            }
        ]

        response = client.post(
            f"/admin/grading-eligibility/{user_a.id}",
            data={"items": json.dumps(payload)},
            follow_redirects=True,
        )
        assert response.status_code == 200

        record = (
            db_session.query(UserDiseaseUnitRole)
            .filter(
                UserDiseaseUnitRole.user_id == user_a.id,
                UserDiseaseUnitRole.disease_id == core_test_data["glaucoma"].id,
                UserDiseaseUnitRole.lab_unit_id == hospital_data["hospital_a"]["lab_units"][0].id,
            )
            .first()
        )
        assert record is not None
        assert record.can_grade_resident is True

    def test_user_manager_cannot_edit_users_outside_hospital(
        self, auth_client, site_admin_hospital_a, db_session, hospital_data
    ):
        user_b = UserFactory.create_with_hospital(
            db_session,
            role_name="ophthalmologist",
            hospital_id=hospital_data["hospital_b"]["hospital"].id,
            lab_unit_ids=[hospital_data["hospital_b"]["lab_units"][0].id],
            username="eligibility_user_b",
        )

        self._make_user_manager(db_session, site_admin_hospital_a)
        client = auth_client(site_admin_hospital_a)
        response = client.get(f"/admin/grading-eligibility/{user_b.id}", follow_redirects=False)
        assert response.status_code == 302

    def test_user_manager_cannot_assign_cross_hospital_lab_units(
        self, auth_client, site_admin_hospital_a, db_session, hospital_data, core_test_data
    ):
        user_a = UserFactory.create_with_hospital(
            db_session,
            role_name="ophthalmologist",
            hospital_id=hospital_data["hospital_a"]["hospital"].id,
            lab_unit_ids=[hospital_data["hospital_a"]["lab_units"][0].id],
            username="eligibility_user_a_cross",
        )

        self._make_user_manager(db_session, site_admin_hospital_a)
        client = auth_client(site_admin_hospital_a)
        payload = [
            {
                "disease_id": core_test_data["glaucoma"].id,
                "lab_unit_id": hospital_data["hospital_b"]["lab_units"][0].id,
                "can_grade_resident": True,
                "can_grade_resident2": False,
                "can_arbitrate": False,
                "active": True,
            }
        ]

        response = client.post(
            f"/admin/grading-eligibility/{user_a.id}",
            data={"items": json.dumps(payload)},
            follow_redirects=True,
        )
        assert response.status_code == 200

        record = (
            db_session.query(UserDiseaseUnitRole)
            .filter(
                UserDiseaseUnitRole.user_id == user_a.id,
                UserDiseaseUnitRole.disease_id == core_test_data["glaucoma"].id,
                UserDiseaseUnitRole.lab_unit_id == hospital_data["hospital_b"]["lab_units"][0].id,
            )
            .first()
        )
        assert record is None

    def test_local_admin_alone_cannot_manage_grading_eligibility(
        self, auth_client, site_admin_hospital_a, db_session, hospital_data
    ):
        target = UserFactory.create_with_hospital(
            db_session,
            role_name="ophthalmologist",
            hospital_id=hospital_data["hospital_a"]["hospital"].id,
            lab_unit_ids=[],
            username="eligibility_local_admin_denied",
        )
        response = auth_client(site_admin_hospital_a).get(
            f"/admin/grading-eligibility/{target.id}"
        )
        assert response.status_code == 403
