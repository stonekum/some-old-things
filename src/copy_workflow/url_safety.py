from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests


class UnsafeURLError(ValueError):
    """Raised when a URL or HTTP response is unsafe to fetch."""


_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal"}


def assert_safe_url(url: str) -> None:
    """Reject URLs that could target local, private, metadata, or reserved hosts."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise UnsafeURLError(f"URL parse failed: {e}") from e

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError(f"Only http/https URLs are supported: {parsed.scheme!r}")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL is missing a hostname")

    normalized_host = host.rstrip(".").lower()
    if normalized_host in _BLOCKED_HOSTS or normalized_host.endswith(".localhost"):
        raise UnsafeURLError(f"Blocked unsafe hostname: {host}")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"Could not resolve host {host!r}: {e}") from e

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"Blocked unsafe address {addr} from host {host}")


def _content_type_allowed(content_type: str, allowed: tuple[str, ...]) -> bool:
    normalized = content_type.split(";", 1)[0].strip().lower()
    return any(
        normalized == item.lower().rstrip("*").rstrip("/")
        if not item.endswith("/")
        else normalized.startswith(item.lower())
        for item in allowed
    )


def safe_get(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    max_redirects: int = 3,
    max_bytes: int | None = None,
    allowed_content_types: tuple[str, ...] | None = None,
) -> requests.Response:
    """GET a URL after validating every redirect target before it is requested."""
    current_url = url
    for redirect_count in range(max_redirects + 1):
        assert_safe_url(current_url)
        response = session.get(
            current_url,
            headers=headers,
            timeout=timeout,
            stream=max_bytes is not None,
            allow_redirects=False,
        )

        if response.status_code in _REDIRECT_STATUS_CODES:
            if redirect_count >= max_redirects:
                raise UnsafeURLError(f"Too many redirects fetching {url}")
            location = response.headers.get("Location")
            if not location:
                raise UnsafeURLError(f"Redirect missing Location header for {current_url}")
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        if allowed_content_types is not None:
            content_type = response.headers.get("Content-Type", "")
            if not _content_type_allowed(content_type, allowed_content_types):
                raise UnsafeURLError(f"Blocked response Content-Type: {content_type!r}")

        if max_bytes is not None:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise UnsafeURLError(f"Response body is too large: {content_length} bytes")

            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise UnsafeURLError(f"Response body is too large: {len(content)} bytes")
            response._content = bytes(content)  # type: ignore[attr-defined]

        return response

    raise UnsafeURLError(f"Too many redirects fetching {url}")
