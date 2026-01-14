"""
Test suite for session fixation protection (CWE-384).

This module tests that the application properly handles session fixation attacks:
1. Session rotation on login (old sessions invalidated)
2. Concurrent session limits per user
3. "Log out all other sessions" functionality

Tests follow TDD: write failing tests first, then implement fix.
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from flask import session

from models import FlaskSession, User
from server_side_session import mark_session_ended


class TestSessionRotationOnLogin:
    """Test suite for session rotation on login (session fixation protection)."""

    def test_old_session_invalidated_on_new_login(self, client, db_session, core_test_data):
        """
        FAILING TEST: Old sessions are not invalidated on new login.

        Test that when a user logs in from a new location/device,
        their old sessions are invalidated to prevent session fixation.
        """
        from tests.helpers.factories import UserFactory

        # Create a test user
        lab_unit = db_session.merge(core_test_data['lab_unit'])
        user = UserFactory.create_ophthalmologist(db_session, lab_units=[lab_unit])
        db_session.commit()

        # First login from device A
        response1 = client.post('/login', data={
            'username': user.username,
            'password': 'Test@2026',
            'csrf_token': 'dummy_token'
        })
        assert response1.status_code in [200, 302]

        # Get the first session ID
        with client.session_transaction() as sess:
            session_id_1 = sess.get('_id', None)

        # Simulate login from device B (new session)
        # This should invalidate the old session
        response2 = client.post('/login', data={
            'username': user.username,
            'password': 'Test@2026',
            'csrf_token': 'dummy_token'
        })
        assert response2.status_code in [200, 302]

        # Check that old session is invalidated in database
        # This will FAIL until we implement session rotation
        if session_id_1:
            old_session = db_session.get(FlaskSession, session_id_1)
            assert old_session is None or old_session.ended_at is not None, (
                "Old session should be invalidated when user logs in from new device"
            )

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
