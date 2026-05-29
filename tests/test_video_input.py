"""Tests for video_input.py — covers the stub transcriber + validators.

Real ASR backend tests come later once a backend is wired.
"""
import importlib.util
import sys
from pathlib import Path


def _load_video_input():
    spec = importlib.util.spec_from_file_location(
        "_video_input_under_test",
        Path(__file__).resolve().parents[1] / "video_input.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_video_input_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_validate_upload_accepts_mp4():
    mod = _load_video_input()
    ok, err = mod.validate_upload("clip.mp4", 1024 * 1024)
    assert ok
    assert err == ""


def test_validate_upload_rejects_unknown_ext():
    mod = _load_video_input()
    ok, err = mod.validate_upload("clip.exe", 1024)
    assert not ok
    assert ".exe" in err


def test_validate_upload_rejects_oversize():
    mod = _load_video_input()
    # 51 MB > 50 MB cap
    ok, err = mod.validate_upload("clip.mp4", 51 * 1024 * 1024)
    assert not ok
    assert "MB" in err


def test_stub_transcriber_returns_placeholder():
    mod = _load_video_input()
    t = mod.StubTranscriber()
    res = t.transcribe(b"fake-video-bytes", "test.mp4", "video/mp4")
    assert res.backend == "stub"
    assert res.is_placeholder is True
    assert "占位" in res.notes
    # 示例文本应当包含可下游消费的真实段落（让 extract 不报 empty）
    assert len(res.text) > 100
    assert "test.mp4" in res.text  # filename echoed back


def test_default_transcriber_is_stub_for_now():
    mod = _load_video_input()
    t = mod.get_default_transcriber()
    assert t.name == "stub"
