"""
Test suite for session fixation protection (CWE-384).

This module tests that the application properly handles session fixation attacks:
1. Session ID rotation on login (pre-authentication ID invalidated)
2. Concurrent session limits per user
3. "Log out all other sessions" functionality

Tests follow TDD: write failing tests first, then implement fix.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

import pytest
from flask import Flask, session
from sqlalchemy import select

from models import FlaskSession, User
from server_side_session import DatabaseSession, DatabaseSessionInterface, mark_session_ended


class TestSessionRotationOnLogin:
    """Test suite for session rotation on login (session fixation protection)."""

    def test_session_id_rotated_on_authentication(
        self, client, db_session, core_test_data
    ):
        """
        The session ID used before authentication cannot survive login.
        """
        from tests.helpers.factories import UserFactory

        # Create a test user
        lab_unit = db_session.merge(core_test_data['lab_unit'])
        user = UserFactory.create_ophthalmologist(db_session, lab_units=[lab_unit])
        db_session.commit()

        login_page = client.get("/login")
        assert login_page.status_code == 200
        anonymous_cookie = client.get_cookie("session")
        assert anonymous_cookie is not None
        anonymous_session_id = anonymous_cookie.value

        response = client.post('/login', data={
            'username': user.username,
            'password': 'Test@2026',
            'csrf_token': 'dummy_token'
        })
        assert response.status_code in [200, 302]

        authenticated_cookie = client.get_cookie("session")
        assert authenticated_cookie is not None
        assert authenticated_cookie.value != anonymous_session_id

        db_session.expire_all()
        old_session = db_session.get(FlaskSession, anonymous_session_id)
        assert old_session is None or old_session.ended_at is not None

    def test_login_keeps_other_sessions_when_within_limit(
        self, client, db_session, core_test_data
    ):
        from tests.helpers.factories import UserFactory

        lab_unit = db_session.merge(core_test_data["lab_unit"])
        user = UserFactory.create_ophthalmologist(db_session, lab_units=[lab_unit])
        other_session_ids = ["other_browser_one", "other_browser_two"]
        for session_id in other_session_ids:
            db_session.add(
                FlaskSession(
                    session_id=session_id,
                    data="{}",
                    expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                    user_id=user.id,
                    started_at=datetime.now(timezone.utc),
                    ip_address="192.168.3.1",
                )
            )
        db_session.commit()

        response = client.post(
            "/login",
            data={
                "username": user.username,
                "password": "Test@2026",
                "csrf_token": "dummy_token",
            },
        )

        assert response.status_code in [200, 302]
        db_session.expire_all()
        for session_id in other_session_ids:
            assert db_session.get(FlaskSession, session_id).ended_at is None

    def test_regenerate_replaces_current_session_id(self, monkeypatch):
        ended_session_ids = []
        monkeypatch.setattr(
            "server_side_session.mark_session_ended",
            ended_session_ids.append,
        )
        interface = DatabaseSessionInterface()
        web_session = DatabaseSession(
            {"csrf_token": "preserved"},
            session_id="attacker-selected-session-id",
        )

        interface.regenerate(web_session)

        assert web_session.session_id != "attacker-selected-session-id"
        assert len(web_session.session_id) == 64
        assert web_session["csrf_token"] == "preserved"
        assert web_session.modified is True
        assert ended_session_ids == ["attacker-selected-session-id"]

    def test_late_response_cannot_resurrect_invalidated_session(self, monkeypatch):
        ended_at = datetime.now(timezone.utc)
        stored = Mock(ended_at=ended_at)
        db = Mock()
        db.get.return_value = stored
        monkeypatch.setattr("server_side_session.DbSession", Mock(return_value=db))

        app = Flask(__name__)
        app.secret_key = "session-regression-test"
        interface = DatabaseSessionInterface()
        web_session = DatabaseSession(
            {"_user_id": "1", "_permanent": True},
            session_id="already-ended-session",
        )

        with app.test_request_context("/grading/"):
            response = app.response_class()
            interface.save_session(app, web_session, response)

        assert response.headers.get("Set-Cookie") is None
        assert stored.ended_at == ended_at
        db.commit.assert_not_called()
        db.close.assert_called_once()

    def test_concurrent_sessions_limited_per_user(self, client, db_session, core_test_data):
        """
        FAILING TEST: No concurrent session limit implemented.

        Test that a user can only have a limited number of active sessions
        (e.g., 3 sessions max). Oldest sessions should be invalidated.
        """
        from tests.helpers.factories import UserFactory

        # Create a test user
        lab_unit = db_session.merge(core_test_data['lab_unit'])
        user = UserFactory.create_ophthalmologist(db_session, lab_units=[lab_unit])
        db_session.commit()

        # Create multiple sessions for the same user
        for i in range(5):  # Try to create 5 sessions
            new_session = FlaskSession(
                session_id=f"test_session_{i}",
                data='{}',
                expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                user_id=user.id,
                started_at=datetime.now(timezone.utc),
                ip_address=f"192.168.1.{i}",
            )
            db_session.add(new_session)
        db_session.commit()

        # Call enforce_concurrent_session_limit to trigger the limit
        from server_side_session import enforce_concurrent_session_limit
        # Use the last session as the "current" one
        enforce_concurrent_session_limit("test_session_4", user.id)

        # Query active sessions for user
        active_sessions = db_session.execute(
            select(FlaskSession).where(
                FlaskSession.user_id == user.id,
                FlaskSession.ended_at.is_(None),
                FlaskSession.expiry > datetime.now(timezone.utc)
            )
        ).scalars().all()

        # Should have at most 3 active sessions
        assert len(active_sessions) <= 3, (
            f"User should have at most 3 active sessions, found {len(active_sessions)}"
        )

    def test_concurrent_limit_never_invalidates_current_session(
        self, db_session, core_test_data
    ):
        from tests.helpers.factories import UserFactory
        from server_side_session import enforce_concurrent_session_limit

        lab_unit = db_session.merge(core_test_data["lab_unit"])
        user = UserFactory.create_ophthalmologist(db_session, lab_units=[lab_unit])
        current_session_id = "oldest_but_current_session"
        started_at = datetime.now(timezone.utc) - timedelta(minutes=10)

        for index in range(4):
            db_session.add(
                FlaskSession(
                    session_id=(
                        current_session_id if index == 0 else f"newer_session_{index}"
                    ),
                    data="{}",
                    expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                    user_id=user.id,
                    started_at=started_at + timedelta(minutes=index),
                    ip_address=f"192.168.2.{index}",
                )
            )
        db_session.commit()

        enforce_concurrent_session_limit(current_session_id, user.id)
        db_session.expire_all()

        current = db_session.get(FlaskSession, current_session_id)
        assert current is not None
        assert current.ended_at is None


class TestInvalidateAllOtherSessions:
    """Test suite for 'log out all other sessions' functionality."""

    def test_invalidate_all_other_sessions_function_exists(self):
        """
        FAILING TEST: invalidate_all_other_sessions() function doesn't exist.

        Test that a utility function exists to invalidate all sessions
        except the current one.
        """
        # Try to import the function
        try:
            from server_side_session import invalidate_all_other_sessions
            # Function should exist and be callable
            assert callable(invalidate_all_other_sessions)
        except ImportError:
            pytest.fail("invalidate_all_other_sessions() function does not exist yet")

    def test_invalidate_all_other_sessions_works(self, db_session, core_test_data):
        """
        Test that invalidate_all_other_sessions() correctly invalidates
        all sessions except the current one.

        NOTE: This test uses a direct database connection to verify
        invalidate_all_other_sessions() which opens a new DbSession().
        """
        from models import Session as DbSession
        from auth.security import hash_password

        # Use a direct database connection to create test data
        # This bypasses the test wrapper's commit->flush conversion
        db = DbSession()
        try:
            # Get lab unit from core_test_data (session-scoped, committed data)
            lab_unit = db.merge(core_test_data['lab_unit'])

            # Create a test user in the same session
            user = User(
                username=f'test_user_invalidate_{db.query(User).count()}',
                password_hash=hash_password('Test@2026'),
                is_active=True,
                hospital_id=lab_unit.hospital_id,
            )
            db.add(user)
            db.flush()  # Get the user ID

            # Create the "current" session
            current_session_id = "current_session_test"
            current = FlaskSession(
                session_id=current_session_id,
                data='{}',
                expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                user_id=user.id,
                started_at=datetime.now(timezone.utc),
                ip_address="192.168.1.0",
            )
            db.add(current)

            # Create other sessions
            for i in range(1, 6):
                new_session = FlaskSession(
                    session_id=f"test_session_{i}",
                    data='{}',
                    expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                    user_id=user.id,
                    started_at=datetime.now(timezone.utc),
                    ip_address=f"192.168.1.{i}",
                )
                db.add(new_session)
            db.commit()  # Commit so invalidate_all_other_sessions can see it

            # Call invalidate_all_other_sessions
            from server_side_session import invalidate_all_other_sessions
            invalidated = invalidate_all_other_sessions(current_session_id, user.id)

            # Verify sessions were invalidated
            assert invalidated == 5, f"Expected 5 sessions invalidated, got {invalidated}"

            # Verify: only current session should remain active
            active_sessions = db.execute(
                select(FlaskSession).where(
                    FlaskSession.user_id == user.id,
                    FlaskSession.ended_at.is_(None),
                )
            ).scalars().all()

            assert len(active_sessions) == 1, f"Expected 1 active session, got {len(active_sessions)}"
            assert active_sessions[0].session_id == current_session_id
        finally:
            # Clean up test data
            db.query(FlaskSession).filter(
                FlaskSession.session_id.like("test_session%")
            ).delete(synchronize_session=False)
            db.query(FlaskSession).filter(
                FlaskSession.session_id == "current_session_test"
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.username.like("test_user_invalidate%")
            ).delete(synchronize_session=False)
            db.commit()
            db.close()


class TestSessionSecurityLogging:
    """Test suite for session security logging."""

    def test_session_creation_logged_with_ip_and_user_agent(self, client, db_session, core_test_data):
        """
        FAILING TEST: Session creation not logged with IP and User-Agent.

        Test that session creation is logged with IP address and User-Agent.
        """
        # This will FAIL until we implement proper logging
        pass

    def test_session_destruction_logged_with_reason(self, client, db_session, core_test_data):
        """
        FAILING TEST: Session destruction not logged with reason.

        Test that session destruction is logged with a reason
        (logout, new_login, session_limit, manual_invalidate).
        """
        # This will FAIL until we implement proper logging
        pass
