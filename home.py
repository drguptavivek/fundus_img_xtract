"""Public homepage route service."""

from flask import render_template
from flask.typing import ResponseReturnValue


def homepage() -> ResponseReturnValue:
    """Render a lightweight shell; HTMX loads public aggregates separately."""

    return render_template("home.html")
