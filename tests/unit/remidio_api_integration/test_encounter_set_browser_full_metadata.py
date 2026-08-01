from flask import render_template


def test_full_metadata_is_collapsed_and_contains_nested_audit_json(app):
    detail = {
        "full_metadata": {
            "encounter_metadata": {"patient": {"hospital_UHID": "MRN-1"}},
            "source_audit": {
                "upstream_session_payload": {"sessionId": "session-1", "futureField": "kept"},
                "upstream_image_inventory_payload": {"images": [{"filename": "exact.jpg"}]},
            },
            "image_metadata": [{"position": 1, "metadata": {"source_filename": "exact.jpg"}}],
        }
    }

    with app.test_request_context():
        rendered = render_template(
            "remidio_api_uploads/_encounter_set_full_metadata.html",
            detail=detail,
        )

    assert "<details" in rendered
    assert " open" not in rendered
    assert "Full metadata" in rendered
    assert "upstream_session_payload" in rendered
    assert "futureField" in rendered
    assert "exact.jpg" in rendered


def test_full_metadata_disclosure_is_absent_when_redacted(app):
    with app.test_request_context():
        rendered = render_template(
            "remidio_api_uploads/_encounter_set_full_metadata.html",
            detail={"full_metadata": None},
        )

    assert rendered.strip() == ""
