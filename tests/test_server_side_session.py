import json
from datetime import timedelta

import pytest

from server_side_session import DatabaseSessionInterface
from models import Session as DbSession, FlaskSession


def test_session_interface_round_trip(app):
    app.session_interface = DatabaseSessionInterface()
    app.secret_key = "test-secret"
    app.permanent_session_lifetime = timedelta(minutes=5)

    client = app.test_client()

    with client.session_transaction() as sess:
        sess['foo'] = 'bar'

    # Get the session cookie
    session_cookie_name = app.session_cookie_name
    cookies = client.cookie_jar
    if 'localhost.local' in cookies._cookies and '/' in cookies._cookies['localhost.local']:
        session_cookie = cookies._cookies['localhost.local']['/'][session_cookie_name]
        session_id = session_cookie.value
        
        with DbSession() as db:
            stored = db.get(FlaskSession, session_id)
            assert stored is not None
            data = json.loads(stored.data)
            assert data['foo'] == 'bar'

        client2 = app.test_client()
        client2.set_cookie('localhost', session_cookie_name, session_id)
        with client2.session_transaction() as sess2:
            assert sess2['foo'] == 'bar'
