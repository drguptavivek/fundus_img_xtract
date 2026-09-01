"""Public analytics page route."""

from flask import render_template


def public_analytics():
    """Render the public KPI shell; HTMX loads aggregate data separately."""

    return render_template("public/analytics.html")
