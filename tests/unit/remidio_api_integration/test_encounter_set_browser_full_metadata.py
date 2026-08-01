from flask import render_template


def test_full_metadata_opens_fullscreen_modal_with_only_upstream_json(app):
    detail = {
        "id": 3737,
        "full_metadata": {
            "session": {"sessionId": "session-1", "futureField": "kept"},
            "image_inventory": {"images": [{"filename": "exact.jpg"}]},
        }
    }

    with app.test_request_context():
        rendered = render_template(
            "remidio_api_uploads/_encounter_set_full_metadata.html",
            detail=detail,
        )

    assert 'data-bs-toggle="modal"' in rendered
    assert 'data-bs-target="#encounter-full-metadata-3737"' in rendered
    assert "modal-dialog modal-fullscreen" in rendered
    assert "Full metadata" in rendered
    assert "IITK upstream payload" in rendered
    assert "futureField" in rendered
    assert "exact.jpg" in rendered
    assert "encounter_metadata" not in rendered
    assert "image_metadata" not in rendered


def test_full_metadata_disclosure_is_absent_when_redacted(app):
    with app.test_request_context():
        rendered = render_template(
            "remidio_api_uploads/_encounter_set_full_metadata.html",
            detail={"full_metadata": None},
        )

    assert rendered.strip() == ""
