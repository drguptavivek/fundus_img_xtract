from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
import requests

from services.wadhwani_glaucoma_client import (
    UPLOAD_CONNECT_RETRIES,
    WadhwaniClientError,
    _build_http_session,
    _http_session,
    upload_prediction_file,
)


def test_http_session_reuses_connections_and_retries_only_put_requests():
    session = _build_http_session()
    adapter = session.get_adapter("https://")
    retry = adapter.max_retries

    assert adapter._pool_connections > 0
    assert adapter._pool_maxsize > 0
    assert retry.connect == UPLOAD_CONNECT_RETRIES
    assert retry.read == UPLOAD_CONNECT_RETRIES
    assert retry.allowed_methods == frozenset({"PUT"})
    assert 503 in retry.status_forcelist


def test_http_sessions_are_reused_per_thread_but_not_shared_between_threads():
    main_session = _http_session()
    assert _http_session() is main_session

    with ThreadPoolExecutor(max_workers=1) as executor:
        worker_session = executor.submit(_http_session).result()

    assert worker_session is not main_session


def test_upload_network_failure_does_not_expose_presigned_url(monkeypatch):
    presigned_url = "https://glycoma-images.s3.amazonaws.com/image.png?X-Amz-Signature=secret"

    def _raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError(f"failed to resolve {presigned_url}")

    monkeypatch.setattr(
        "services.wadhwani_glaucoma_client._http_session",
        lambda: SimpleNamespace(put=_raise_connection_error),
    )

    with pytest.raises(WadhwaniClientError) as exc_info:
        upload_prediction_file(
            upload_url=presigned_url,
            content_type="image/png",
            image_bytes=b"image",
        )

    assert exc_info.value.step == "upload"
    assert "after retrying" in str(exc_info.value)
    assert "glycoma-images" not in str(exc_info.value)
    assert "X-Amz-Signature" not in str(exc_info.value)
