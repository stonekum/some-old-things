"""Tests for the SSRF guard in app._assert_safe_url.

Loads app.py as a module without running the Streamlit body (st.* calls
happen at module load time but headless mode is fine for syntax verification).
"""
import importlib.util
import socket
import sys
from pathlib import Path

import pytest


def _load_app_module():
    """Load app.py without depending on Streamlit being running."""
    spec = importlib.util.spec_from_file_location(
        "_app_under_test",
        Path(__file__).resolve().parents[1] / "app.py",
    )
    module = importlib.util.module_from_spec(spec)
    # Set env so the password gate is open (empty APP_PASSWORD = no gate)
    sys.modules["_app_under_test"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        # st.stop() raises SystemExit; we don't care for these tests
        pass
    return module


@pytest.fixture(scope="module")
def app_mod():
    return _load_app_module()


def test_blocks_non_http_scheme(app_mod):
    with pytest.raises(ValueError, match="仅支持 http/https"):
        app_mod._assert_safe_url("file:///etc/passwd")
    with pytest.raises(ValueError, match="仅支持 http/https"):
        app_mod._assert_safe_url("ftp://example.com/x")
    with pytest.raises(ValueError, match="仅支持 http/https"):
        app_mod._assert_safe_url("gopher://example.com/x")


def test_blocks_localhost(app_mod):
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://localhost:8501/")
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://127.0.0.1/admin")


def test_blocks_private_ranges(app_mod):
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://10.0.0.5/")
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://192.168.1.1/")
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://172.16.0.1/")


def test_blocks_link_local_metadata(app_mod):
    # AWS / GCP / Azure metadata service is at 169.254.169.254
    with pytest.raises(ValueError, match="禁止访问"):
        app_mod._assert_safe_url("http://169.254.169.254/latest/meta-data/")


def test_blocks_missing_host(app_mod):
    with pytest.raises(ValueError):
        app_mod._assert_safe_url("http:///x")


def test_allows_public_https(app_mod):
    original_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]
        return original_getaddrinfo(host, port, *args, **kwargs)

    app_mod.socket.getaddrinfo = fake_getaddrinfo
    app_mod._assert_safe_url("https://example.com/path")
