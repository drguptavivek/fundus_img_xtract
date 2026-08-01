import html
import re

from flask import render_template


def test_encounter_set_project_badge_truncates_after_75_characters(app):
    title = "Smartphone Imaging-Based Artificial Intelligence Model for Early Detection and Screening"

    with app.test_request_context():
        rendered = render_template(
            "remidio_api_uploads/_encounter_set_project_badge.html",
            detail={"project_title": title},
        )

    badge = re.search(r'<span[^>]*>\s*(.*?)\s*</span>', rendered, re.DOTALL)

    assert badge is not None
    assert html.unescape(badge.group(1)) == f"{title[:75]}…"
    assert f'title="{title}"' in rendered
