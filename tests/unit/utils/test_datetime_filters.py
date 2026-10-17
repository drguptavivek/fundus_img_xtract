from flask import Flask

from utils.datetime_filters import format_user_datetime


def test_iso_string_is_formatted_like_a_datetime():
    app = Flask(__name__)
    with app.test_request_context():
        assert format_user_datetime("2026-10-17T12:00:00+00:00", "%Y-%m-%d") == "2026-10-17"
        assert format_user_datetime("2026-10-17T12:00:00Z", "%Y-%m-%d") == "2026-10-17"
