from flask import Flask

from auth.utils import get_client_ip


def _ip(headers, remote="10.0.0.9"):
    app = Flask(__name__)
    with app.test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": remote}):
        return get_client_ip()


def test_forwarded_header_is_not_reparsed_after_proxy_processing():
    assert _ip({"X-Forwarded-For": "203.0.113.5, 10.0.0.1"}) == "10.0.0.9"


def test_payload_in_xff_falls_back_to_remote_addr():
    assert _ip({"X-Forwarded-For": "x.oast.fun, 13.126.254.5"}) == "10.0.0.9"
    assert _ip({"X-Forwarded-For": "${jndi:ldap://x}, 1.2.3.4"}) == "10.0.0.9"


def test_client_supplied_real_ip_cannot_choose_the_lockout_bucket():
    assert _ip({"X-Forwarded-For": "bogus", "X-Real-IP": "198.51.100.2"}) == "10.0.0.9"


def test_trusted_proxy_hop_is_used_instead_of_attacker_supplied_prefix():
    from werkzeug.middleware.proxy_fix import ProxyFix
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    app.add_url_rule("/ip", view_func=get_client_ip)
    response = app.test_client().get("/ip", headers={"X-Forwarded-For": "203.0.113.5, 198.51.100.2"})
    assert response.text == "198.51.100.2"
