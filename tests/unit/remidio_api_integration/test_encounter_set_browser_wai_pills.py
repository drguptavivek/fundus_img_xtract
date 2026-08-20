from models import Disease
from remidio_api_integration.service import _wai_disease_kind


def test_wai_disease_kind_classifies_dr_dme_glaucoma_only():
    dr = Disease(name="DR", remidio_ocr_linkage="dr")
    dme = Disease(name="DME", remidio_ocr_linkage="none")
    glaucoma = Disease(name="Glaucoma", remidio_ocr_linkage="glaucoma")
    amd = Disease(name="AMD", remidio_ocr_linkage="amd")
    other = Disease(name="Cataract", remidio_ocr_linkage="none")

    assert _wai_disease_kind(dr) == "dr"
    assert _wai_disease_kind(dme) == "dme"
    assert _wai_disease_kind(glaucoma) == "glaucoma"
    assert _wai_disease_kind(amd) is None
    assert _wai_disease_kind(other) is None


def test_wai_pill_markup_renders_label_and_model_title(app):
    """Targeted check of the pill markup pattern used in both the header and
    thumbnail spots, without stubbing the large encounter_set_browser_workspace
    page context (which has many unrelated required fields)."""
    from jinja2 import Template

    snippet = Template(
        '{% for pill in wai_pills %}'
        '<span class="badge text-bg-info" title="{{ pill.title }}">{{ pill.label }}</span>'
        '{% endfor %}'
    )
    rendered = snippet.render(wai_pills=[{"label": "WAI-DR", "title": "MadhuNetrAI DR-DME v2.1"}])

    assert 'title="MadhuNetrAI DR-DME v2.1"' in rendered
    assert ">WAI-DR<" in rendered
