from types import SimpleNamespace

from flask import render_template_string


def test_fixed_scheme_grade_button_targets_matching_grade_template(app):
    scheme = SimpleNamespace(
        id=42,
        name="AMD",
        disease_gradings=[
            SimpleNamespace(
                is_active=True,
                display_order=1,
                impression="Referable AMD",
                features=[SimpleNamespace(sr_no=1, label="Drusen")],
            )
        ],
    )

    with app.test_request_context("/admin/upload-profiles"):
        markup = render_template_string(
            """
            {% from "admin/partials/upload_profile_modals.html" import scheme_grade_button, scheme_grade_template %}
            <div>
              {{ scheme_grade_button("Show grades for " ~ scheme.name, false, scheme.id) }}
              {{ scheme_grade_template(scheme) }}
            </div>
            """,
            scheme=scheme,
        )

    assert 'data-scheme-id="42"' in markup
    assert 'data-scheme-name="AMD"' in markup
    assert 'aria-label="Show grades for AMD"' in markup
    assert 'title="Show grades for AMD"' in markup
    assert '<div class="fw-semibold mb-1">AMD</div>' not in markup
    assert "Referable AMD" in markup
    assert "Drusen" in markup
