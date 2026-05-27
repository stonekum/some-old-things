from __future__ import annotations

import socket

import pytest
import requests

from copy_workflow.crawlers._common import download_images
from copy_workflow.url_safety import UnsafeURLError, assert_safe_url, safe_get


def _resolve_to(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http:///missing-host",
    ],
)
def test_assert_safe_url_rejects_unsupported_or_missing_host(url: str) -> None:
    with pytest.raises(UnsafeURLError):
        assert_safe_url(url)


@pytest.mark.parametrize(
    "url, ip",
    [
        ("http://localhost:8501/", "127.0.0.1"),
        ("http://127.0.0.1/admin", "127.0.0.1"),
        ("http://10.0.0.5/", "10.0.0.5"),
        ("http://172.16.0.1/", "172.16.0.1"),
        ("http://192.168.1.1/", "192.168.1.1"),
        ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
        ("http://metadata.google.internal/", "169.254.169.254"),
        ("http://example.test/", "240.0.0.1"),
    ],
)
def test_assert_safe_url_rejects_private_link_local_metadata_and_reserved(
    monkeypatch: pytest.MonkeyPatch, url: str, ip: str
) -> None:
    _resolve_to(monkeypatch, ip)

    with pytest.raises(UnsafeURLError):
        assert_safe_url(url)


def test_assert_safe_url_allows_public_http(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, "93.184.216.34")

    assert_safe_url("https://example.com/path")


class FakeResponse:
    def __init__(
        self,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes = b"ok",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._content = content

    @property
    def content(self) -> bytes:
        return self._content

    def iter_content(self, chunk_size: int = 1):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, bool]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs.get("allow_redirects")))
        return self.responses.pop(0)


def test_safe_get_manually_validates_each_redirect_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _resolve_to(monkeypatch, "93.184.216.34")
    session = FakeSession(
        [
            FakeResponse(
                "https://example.com/start",
                status_code=302,
                headers={"Location": "https://example.com/next"},
            ),
            FakeResponse("https://example.com/next", content=b"done"),
        ]
    )

    response = safe_get(session, "https://example.com/start")

    assert response.content == b"done"
    assert session.calls == [
        ("https://example.com/start", False),
        ("https://example.com/next", False),
    ]


def test_safe_get_blocks_redirect_to_private_host_before_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host, port):
        ip = "93.184.216.34" if host == "example.com" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    session = FakeSession(
        [
            FakeResponse(
                "https://example.com/start",
                status_code=302,
                headers={"Location": "http://127.0.0.1/admin"},
            )
        ]
    )

    with pytest.raises(UnsafeURLError):
        safe_get(session, "https://example.com/start")

    assert session.calls == [("https://example.com/start", False)]


def test_safe_get_rejects_response_that_exceeds_max_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _resolve_to(monkeypatch, "93.184.216.34")
    session = FakeSession([FakeResponse("https://example.com/image.jpg", content=b"abcdef")])

    with pytest.raises(UnsafeURLError, match="too large"):
        safe_get(session, "https://example.com/image.jpg", max_bytes=5)


def test_download_images_rejects_non_image_content_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _resolve_to(monkeypatch, "93.184.216.34")
    session = FakeSession(
        [
            FakeResponse(
                "https://example.com/not-image.jpg",
                headers={"Content-Type": "text/html; charset=utf-8"},
                content=b"<html></html>",
            )
        ]
    )

    assert download_images(session, ["https://example.com/not-image.jpg"], tmp_path, "image") == 0
    assert list(tmp_path.iterdir()) == []
