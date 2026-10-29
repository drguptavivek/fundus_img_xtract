from flask import Flask
from flask_limiter import Limiter

from verify_encounter_set.rate_limits import configure_review_rate_limit


def test_review_limit_overrides_default_without_affecting_other_routes():
    app = Flask(__name__)
    app.config["RATELIMIT_ENABLED"] = True
    Limiter(key_func=lambda: "user", app=app, default_limits=["2 per hour"], storage_uri="memory://")
    def review():
        return "ok"

    def other():
        return "ok"

    app.add_url_rule("/review", "verify_encounter_set.mark_reviewed", review, methods=["POST"])
    app.add_url_rule("/other", "other", other, methods=["POST"])
    configure_review_rate_limit(app)

    client = app.test_client()
    assert all(client.post("/review").status_code == 200 for _ in range(1000))
    assert client.post("/review").status_code == 429
    assert [client.post("/other").status_code for _ in range(3)] == [200, 200, 429]
