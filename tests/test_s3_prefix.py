from utils.s3_prefix import apply_global_prefix


def test_apply_global_prefix_adds_prefix():
    assert apply_global_prefix("files/direct_uploads/a.jpg") == "eyeimgmgr/files/direct_uploads/a.jpg"


def test_apply_global_prefix_keeps_existing_prefix():
    assert apply_global_prefix("eyeimgmgr/files/direct_uploads/a.jpg") == "eyeimgmgr/files/direct_uploads/a.jpg"


def test_apply_global_prefix_strips_leading_slash():
    assert apply_global_prefix("/files/direct_uploads/a.jpg") == "eyeimgmgr/files/direct_uploads/a.jpg"

