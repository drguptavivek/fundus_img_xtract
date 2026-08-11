"""Private browser-session token handoff for server-rendered workbenches."""

from __future__ import annotations

from flask import session as flask_session


def remember_session_token(session_uuid: str, token: str, generation: int) -> None:
    """Keep a workbench bearer token out of URLs during page navigation."""
    flask_session[f"grading_workbench:{session_uuid}"] = {
        "token": token,
        "generation": generation,
    }
