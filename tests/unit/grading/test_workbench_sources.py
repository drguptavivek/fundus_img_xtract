from __future__ import annotations

from grading.workbench.sources import _media


class _NoMetadataQuery:
    def filter(self, *_args):
        return self

    def first(self):
        return None


class _NoMetadataSession:
    def query(self, _model):
        return _NoMetadataQuery()


def test_workbench_media_uses_scoped_universal_grading_routes():
    media = _media(_NoMetadataSession(), "direct_image_upload", "image-uuid", None)

    assert media.media_url == "/media/img/image-uuid"
    assert media.thumbnail_url == "/media/img/image-uuid/thumbnail"
