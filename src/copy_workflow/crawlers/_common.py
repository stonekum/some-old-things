from __future__ import annotations

import re
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..url_safety import UnsafeURLError, safe_get


MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Raster formats only — SVG is XML that can carry scripts/external entities,
# so we never persist attacker-supplied SVG bytes to disk under an .jpg name.
_RASTER_CONTENT_TYPES: tuple[str, ...] = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)
_EXT_BY_CONTENT_TYPE: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def make_session(user_agent: str, referer: str | None = None) -> requests.Session:
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({"User-Agent": user_agent})
    if referer:
        s.headers["Referer"] = referer
    return s


def sanitize_filename(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()[:120]


def read_links(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def save_text(out_path: Path, body: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")


def download_images(
    session: requests.Session, urls: list[str], out_dir: Path, prefix: str
) -> int:
    count = 0
    for idx, url in enumerate(urls, start=1):
        try:
            r = safe_get(
                session,
                url,
                timeout=20,
                max_bytes=MAX_IMAGE_BYTES,
                allowed_content_types=_RASTER_CONTENT_TYPES,
            )
            if not r.content:
                continue
            # Pick the real extension from the response's Content-Type rather
            # than blindly writing .jpg — a PNG written as .jpg can confuse
            # downstream tools, and we already rejected non-raster types above.
            ctype = (r.headers.get("Content-Type", "").split(";", 1)[0]).strip().lower()
            ext = _EXT_BY_CONTENT_TYPE.get(ctype, "jpg")
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{prefix}_{idx}.{ext}").write_bytes(r.content)
            count += 1
        except (OSError, UnsafeURLError, requests.RequestException, ValueError):
            continue
    return count
