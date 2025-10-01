import json
from datetime import timedelta

import pytest

from server_side_session import DatabaseSessionInterface
from models import Session as DbSession, FlaskSession


def test_session_interface_round_trip(app_factory):
    app = app_factory()
    app.session_interface = DatabaseSessionInterface()
    app.secret_key = "test-secret"
    app.permanent_session_lifetime = timedelta(minutes=5)

    client = app.test_client()

    with client.session_transaction() as sess:
        sess['foo'] = 'bar'

    session_cookie = client.cookie_jar._cookies['localhost.local']['/'][app.session_cookie_name]
    session_id = session_cookie.value

    with DbSession() as db:
        stored = db.get(FlaskSession, session_id)
        assert stored is not None
        data = json.loads(stored.data)
        assert data['foo'] == 'bar'

    client2 = app.test_client()
    client2.set_cookie('localhost', app.session_cookie_name, session_id)
    with client2.session_transaction() as sess2:
        assert sess2['foo'] == 'bar'
