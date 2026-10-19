from flask import Flask

from auth.utils import get_client_ip


def _ip(headers, remote="10.0.0.9"):
    app = Flask(__name__)
    with app.test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": remote}):
        return get_client_ip()


def test_valid_forwarded_ip_is_used():
    assert _ip({"X-Forwarded-For": "203.0.113.5, 10.0.0.1"}) == "203.0.113.5"


def test_payload_in_xff_falls_back_to_remote_addr():
    assert _ip({"X-Forwarded-For": "x.oast.fun, 13.126.254.5"}) == "10.0.0.9"
    assert _ip({"X-Forwarded-For": "${jndi:ldap://x}, 1.2.3.4"}) == "10.0.0.9"


def test_invalid_xff_uses_valid_real_ip():
    assert _ip({"X-Forwarded-For": "bogus", "X-Real-IP": "198.51.100.2"}) == "198.51.100.2"
