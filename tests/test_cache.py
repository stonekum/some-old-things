from pathlib import Path

from copy_workflow.cache import JSONCache, cache_key


def test_cache_key_stable():
    a = cache_key("hello", "world", "deepseek-chat")
    b = cache_key("hello", "world", "deepseek-chat")
    assert a == b


def test_cache_key_different_for_different_inputs():
    assert cache_key("a") != cache_key("b")
    assert cache_key("a", "b") != cache_key("ab", "")


def test_cache_set_get_roundtrip(tmp_path: Path):
    c = JSONCache(tmp_path / "cache")
    key = cache_key("k1")
    assert c.get(key) is None
    c.set(key, {"content": "hi", "prompt_tokens": 3})
    got = c.get(key)
    assert got == {"content": "hi", "prompt_tokens": 3}


def test_cache_corrupt_returns_none(tmp_path: Path):
    c = JSONCache(tmp_path / "cache")
    key = cache_key("bad")
    c.path(key).write_text("not json", encoding="utf-8")
    assert c.get(key) is None


def test_cache_get_returns_none_on_oserror(monkeypatch, tmp_path: Path):
    c = JSONCache(tmp_path / "cache")
    key = cache_key("unreadable")
    c.path(key).write_text('{"ok": true}', encoding="utf-8")

    def unreadable(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Path, "read_text", unreadable)

    assert c.get(key) is None


def test_cache_set_uses_atomic_replace(monkeypatch, tmp_path: Path):
    c = JSONCache(tmp_path / "cache")
    key = cache_key("atomic")
    calls: list[tuple[Path, Path]] = []

    def fake_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr("copy_workflow.cache.os.replace", fake_replace)

    c.set(key, {"content": "hi"})

    assert c.get(key) == {"content": "hi"}
    assert len(calls) == 1
    src, dst = calls[0]
    assert src.parent == tmp_path / "cache"
    assert src.name.startswith(f".{key}.")
    assert dst == c.path(key)


def test_cache_set_swallows_oserror(monkeypatch, tmp_path: Path):
    c = JSONCache(tmp_path / "cache")

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr("copy_workflow.cache.os.replace", fail_replace)

    c.set(cache_key("write-error"), {"content": "hi"})
