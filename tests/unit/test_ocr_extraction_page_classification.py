import importlib
import sys
from types import SimpleNamespace

sys.modules.setdefault("pytesseract", SimpleNamespace(image_to_string=lambda _region: ""))
ocr_extraction = importlib.import_module("ocr_extraction")


class _FakeImage:
    def __init__(self, regions):
        self.regions = regions

    def crop(self, coords):
        return self.regions.get(coords, "")


def test_classify_report_page_detects_dr_dr_amd_and_glaucoma(monkeypatch):
    diabetic_coords = (0, 200, 1200, 400)
    glaucoma_coords = (0, 400, 1200, 600)

    monkeypatch.setattr(ocr_extraction.pytesseract, "image_to_string", lambda region: region)

    assert (
        ocr_extraction._classify_report_page(
            _FakeImage({diabetic_coords: "Diabetic Retinopathy Report"}),
            diabetic_report_coords=diabetic_coords,
            glaucoma_report_coords=glaucoma_coords,
        )
        == "dr"
    )
    assert (
        ocr_extraction._classify_report_page(
            _FakeImage({diabetic_coords: "DR and AMD Report"}),
            diabetic_report_coords=diabetic_coords,
            glaucoma_report_coords=glaucoma_coords,
        )
        == "dr_amd"
    )
    assert (
        ocr_extraction._classify_report_page(
            _FakeImage({glaucoma_coords: "Glaucoma Report"}),
            diabetic_report_coords=diabetic_coords,
            glaucoma_report_coords=glaucoma_coords,
        )
        == "glaucoma"
    )


def test_extract_dr_amd_page_results_only_extracts_amd_for_combined_page(monkeypatch):
    result_coords = (0, 560, 2000, 820)
    qualitative_coords = (50, 3100, 1600, 3200)
    image = _FakeImage(
        {
            result_coords: (
                "Result DR: No signs of DR detected. "
                "Result AMD: Signs of AMD detected. DR Screening Interval: 12 months"
            ),
            qualitative_coords: "Warning: Images insufficient for accurate DR and AMD screening",
        }
    )
    monkeypatch.setattr(ocr_extraction.pytesseract, "image_to_string", lambda region: region)

    dr_result, dr_qual, amd_result, amd_qual = ocr_extraction._extract_dr_amd_page_results(
        image,
        result_coords=result_coords,
        qualitative_coords=qualitative_coords,
        page_type="dr_amd",
    )
    assert dr_result == "No signs of DR detected."
    assert dr_qual == "Warning: Images insufficient for accurate DR and AMD screening"
    assert amd_result == "Signs of AMD detected."
    assert amd_qual == "Warning: Images insufficient for accurate DR and AMD screening"

    _dr_result, _dr_qual, amd_result, amd_qual = ocr_extraction._extract_dr_amd_page_results(
        image,
        result_coords=result_coords,
        qualitative_coords=qualitative_coords,
        page_type="dr",
    )
    assert amd_result is None
    assert amd_qual is None


def test_extract_dr_amd_page_results_handles_single_combined_result_label(monkeypatch):
    result_coords = (0, 560, 2000, 820)
    qualitative_coords = (50, 3100, 1600, 3200)
    image = _FakeImage(
        {
            result_coords: "Result: No signs of DR or AMD detected. Re-examine after 12 months for AI DR Screening",
            qualitative_coords: "",
        }
    )
    monkeypatch.setattr(ocr_extraction.pytesseract, "image_to_string", lambda region: region)

    dr_result, _dr_qual, amd_result, _amd_qual = ocr_extraction._extract_dr_amd_page_results(
        image,
        result_coords=result_coords,
        qualitative_coords=qualitative_coords,
        page_type="dr_amd",
    )

    assert dr_result == "No signs of DR or AMD detected. Re-examine after 12 months for AI"
    assert amd_result == "No signs of DR or AMD detected. Re-examine after 12 months for AI"
