"""Patient-level rollup of the WAI answers.

Per-eye DR/DME comes from the single is_primary image per eye, per the vendor
contract. The rollup rules that matter clinically: either eye positive makes the
patient positive, and two ungradable eyes are "no finding", never "negative".
"""
from field_workbench.dto import AIEyeResultDTO
from field_workbench.status import _roll_up, wai_disease_kind
from models import Disease


def test_one_positive_eye_makes_the_patient_positive():
    eyes = [
        AIEyeResultDTO(eye="left", grade="No DR", positive=False, gradable=True),
        AIEyeResultDTO(eye="right", grade="Moderate NPDR", positive=True, gradable=True),
    ]
    assert _roll_up(eyes, run_finished=True) == "positive"


def test_both_eyes_negative_rolls_up_to_negative():
    eyes = [
        AIEyeResultDTO(eye="left", grade="No DR", positive=False, gradable=True),
        AIEyeResultDTO(eye="right", grade="No DR", positive=False, gradable=True),
    ]
    assert _roll_up(eyes, run_finished=True) == "negative"


def test_both_eyes_ungradable_is_not_a_negative_finding():
    """Reporting 'negative' here would assert absence of disease that was never assessed."""
    eyes = [
        AIEyeResultDTO(eye="left", grade="Not Gradable", positive=False, gradable=False),
        AIEyeResultDTO(eye="right", grade="Not Gradable", positive=False, gradable=False),
    ]
    assert _roll_up(eyes, run_finished=True) == "not_gradable"


def test_one_gradable_negative_eye_still_reports_negative():
    eyes = [
        AIEyeResultDTO(eye="left", grade="Not Gradable", positive=False, gradable=False),
        AIEyeResultDTO(eye="right", grade="No DR", positive=False, gradable=True),
    ]
    assert _roll_up(eyes, run_finished=True) == "negative"


def test_no_eyes_before_the_run_finishes_is_pending():
    assert _roll_up([], run_finished=False) == "pending"


def test_disease_kind_prefers_linkage_but_falls_back_to_name():
    dr_by_linkage = Disease(name="Diabetic Retinopathy", remidio_ocr_linkage="dr")
    dr_by_name = Disease(name="DR", remidio_ocr_linkage="none")
    dme = Disease(name="DME", remidio_ocr_linkage="none")
    glaucoma = Disease(name="Glaucoma", remidio_ocr_linkage="none")
    unrelated = Disease(name="AMD", remidio_ocr_linkage="amd")

    assert wai_disease_kind(dr_by_linkage) == "dr"
    assert wai_disease_kind(dr_by_name) == "dr"
    assert wai_disease_kind(dme) == "dme"
    assert wai_disease_kind(glaucoma) == "glaucoma"
    assert wai_disease_kind(unrelated) is None
