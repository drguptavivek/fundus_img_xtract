from uuid import uuid4

from models import EncounterSetImage
from remidio_api_integration.service import _encounter_set_image_row


def test_encounter_set_browser_uses_named_gaze_position_when_available():
    image = EncounterSetImage(
        uuid=str(uuid4()),
        spatial_position=4,
        original_filename="unused.jpg",
        folder_rel="files/test",
        metadata_json={"gaze_position": "up_right", "laterality": "ou"},
    )

    row = _encounter_set_image_row(image)

    assert row["position"] == 4
    assert row["position_label"] == "up_right"


def test_encounter_set_browser_falls_back_to_numeric_position():
    image = EncounterSetImage(
        uuid=str(uuid4()),
        spatial_position=4,
        original_filename="unused.jpg",
        folder_rel="files/test",
        metadata_json={},
    )

    assert _encounter_set_image_row(image)["position_label"] == "Position 4"
