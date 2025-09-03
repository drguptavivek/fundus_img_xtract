import os
from pathlib import Path
from models import DirectImageUpload, BASE_DIR

def test_path_properties():
    """
    Tests the path-related properties of the DirectImageUpload model.
    """
    # Create a mock DirectImageUpload instance
    upload = DirectImageUpload(
        folder_rel="files/direct_uploads/2023_01_01_user1",
        filename="test_image.jpg"
    )

    # Test the rel_dir property
    assert upload.rel_dir == "files/direct_uploads/2023_01_01_user1"

    # The model itself doesn't have an absolute path property,
    # but we can test the logic for constructing it.
    from direct_uploads.paths import abs_from_parts
    
    expected_abs_path = BASE_DIR / "files" / "direct_uploads" / "2023_01_01_user1" / "orig" / "test_image.jpg"
    
    # Test constructing the original image path
    actual_abs_path = abs_from_parts(upload.folder_rel, upload.filename, "orig")
    
    assert actual_abs_path == expected_abs_path
    assert os.path.isabs(actual_abs_path)

    # Test constructing an edited image path
    upload.edited_filename = "edited_image.png"
    expected_edited_path = BASE_DIR / "files" / "direct_uploads" / "2023_01_01_user1" / "edited" / "edited_image.png"
    actual_edited_path = abs_from_parts(upload.folder_rel, upload.edited_filename, "edited")

    assert actual_edited_path == expected_edited_path
