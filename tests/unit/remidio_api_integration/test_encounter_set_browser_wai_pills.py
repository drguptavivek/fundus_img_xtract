from jinja2 import Environment, FileSystemLoader

from models import Disease
from remidio_api_integration.wai_pills import (
    WaiResult,
    display_grade,
    encounter_pills,
    grade_rank,
    status_label,
    image_pills,
    is_positive_impression,
    wai_disease_kind,
)


def test_wai_disease_kind_classifies_dr_dme_glaucoma_only():
    dr = Disease(name="DR", remidio_ocr_linkage="dr")
    dme = Disease(name="DME", remidio_ocr_linkage="none")
    glaucoma = Disease(name="Glaucoma", remidio_ocr_linkage="glaucoma")
    amd = Disease(name="AMD", remidio_ocr_linkage="amd")
    other = Disease(name="Cataract", remidio_ocr_linkage="none")

    assert wai_disease_kind(dr) == "dr"
    assert wai_disease_kind(dme) == "dme"
    assert wai_disease_kind(glaucoma) == "glaucoma"
    assert wai_disease_kind(amd) is None
    assert wai_disease_kind(other) is None


def test_positive_impressions_per_kind():
    assert is_positive_impression("dr", "Moderate NPDR")
    assert is_positive_impression("dr", "PDR")
    assert is_positive_impression("dr", "Mild DR")
    assert not is_positive_impression("dr", "No DR")
    assert not is_positive_impression("dr", "Not Gradable")
    assert is_positive_impression("dme", "M1 Referable Diabetic Maculopathy")
    assert not is_positive_impression("dme", "M0 No DME")
    assert is_positive_impression("glaucoma", "Suspect")
    assert is_positive_impression("glaucoma", "glaucoma")
    assert not is_positive_impression("glaucoma", "Normal")
    assert not is_positive_impression("glaucoma", None)


def test_pill_labels_and_plus_marker():
    pills = image_pills({
        "dr": WaiResult("MN v1", positive=True),
        "dme": WaiResult("MN v1", positive=False),
        "glaucoma": WaiResult("RPC v2", positive=True),
    })
    assert [(p["label"], p["positive"]) for p in pills] == [
        ("MN-DR+", True), ("MN-DME", False), ("RPC-Glau+", True),
    ]
    assert "refer advised" in pills[0]["title"]


def test_encounter_pill_is_positive_when_any_image_is():
    pills = encounter_pills({
        1: {"glaucoma": WaiResult("RPC v2", False, "Normal"), "dr": WaiResult("MN v1", False, "Mild DR")},
        2: {"glaucoma": WaiResult("RPC v2", True, "Suspect"), "dr": WaiResult("MN v1", True, "PDR")},
        3: {"dr": WaiResult("MN v1", True, "Moderate NPDR"), "glaucoma": WaiResult("RPC v2", False, "Not Gradable")},
    })
    assert [(p["label"], p["positive"], p["grade"]) for p in pills] == [
        ("MN-DR+", True, "PDR"), ("RPC-Glau+", True, "Suspect"),
    ]


def test_pill_macros_render_red_for_positive_and_refer():
    env = Environment(loader=FileSystemLoader("templates"))
    module = env.get_template("remidio_api_uploads/_wai_pills.html").module

    html = module.wai_pills(image_pills({"dr": WaiResult("MN v1", positive=True)}))
    assert "text-bg-danger" in html and ">MN-DR+<" in html and 'title="MN v1 - refer advised"' in html
    html = module.wai_pills(image_pills({"dr": WaiResult("MN v1", positive=True, grade="Mild DR")}), show_grade=True)
    assert ">MN-DR+ · Mild DR<" in html
    html = module.wai_pills(image_pills({"dr": WaiResult("MN v1", positive=False)}))
    assert "text-bg-info" in html and ">MN-DR<" in html
    assert ">Remidio Refer<" in module.refer_pill("yes")
    assert str(module.refer_pill("no")).strip() == ""


def test_image_pill_carries_exact_grade():
    (pill,) = image_pills({"dr": WaiResult("MN v1", positive=True, grade="Moderate NPDR")})
    assert pill["grade"] == "Moderate NPDR" and pill["kind_label"] == "MN-DR"
    assert pill["title"].startswith("Moderate NPDR (")


def test_grade_rank_orders_severity_and_ignores_non_grades():
    assert grade_rank("dr", "PDR") > grade_rank("dr", "Moderate NPDR") > grade_rank("dr", "No DR")
    assert grade_rank("dr", "Not Gradable") == grade_rank("dr", "Other Retinal") == -1
    assert grade_rank("glaucoma", "Glaucoma") > grade_rank("glaucoma", "Suspect")


def test_glaucoma_model_positive_is_displayed_as_refer_and_still_refers():
    assert display_grade("glaucoma", "Glaucoma") == "Refer"
    assert display_grade("glaucoma", "Normal") == "Normal"
    assert display_grade("dr", "PDR") == "PDR"
    assert is_positive_impression("glaucoma", "Glaucoma")  # the stored impression still refers
    assert is_positive_impression("glaucoma", "Suspect")


def test_status_label_matches_browse_header_pill():
    assert status_label("dr", ["No DR", "Moderate NPDR"]) == "MN-DR+ · Moderate NPDR"
    assert status_label("dr", ["No DR"]) == "MN-DR · No DR"
    assert status_label("dme", [None]) == "MN-DME"
    assert status_label("glaucoma", ["Normal", "Glaucoma"]) == "RPC-Glau+ · Refer"
    assert status_label("glaucoma", []) == "RPC-Glau"
    assert status_label("dr", ["Not Gradable"]) == "MN-DR · Not Gradable"
