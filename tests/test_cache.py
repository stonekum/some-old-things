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
