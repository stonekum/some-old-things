from types import SimpleNamespace

from copy_workflow.llm import DeepSeekClient, parse_json_strict


def test_parse_json_plain():
    assert parse_json_strict('{"a": 1}') == {"a": 1}


def test_parse_json_with_fence():
    raw = """```json
{"title": "hi", "body": "world"}
```"""
    assert parse_json_strict(raw) == {"title": "hi", "body": "world"}


def test_parse_json_with_bare_fence():
    raw = """```
{"x": 2}
```"""
    assert parse_json_strict(raw) == {"x": 2}


def _client(tmp_path, api_url: str) -> DeepSeekClient:
    cfg = SimpleNamespace(
        paths=SimpleNamespace(cache=tmp_path / "cache", logs=tmp_path / "logs"),
        secrets=SimpleNamespace(deepseek_api_url=api_url, deepseek_api_key="test-key"),
        generation=SimpleNamespace(retries=1, request_timeout_sec=1, retry_backoff_sec=0),
    )
    cfg.paths.logs.mkdir(parents=True, exist_ok=True)
    return DeepSeekClient(cfg)


def test_deepseek_cache_key_includes_api_url_and_schema_version(tmp_path):
    first = _client(tmp_path / "a", "https://api.deepseek.com/v1/chat/completions")
    second = _client(tmp_path / "b", "https://api.other.example/v1/chat/completions")

    first_key = first._cache_key(
        system="sys",
        user="user",
        model="deepseek-chat",
        json_mode=True,
        temperature=0.2,
    )
    second_key = second._cache_key(
        system="sys",
        user="user",
        model="deepseek-chat",
        json_mode=True,
        temperature=0.2,
    )

    assert first_key != second_key
    assert first_key == first._cache_key(
        system="sys",
        user="user",
        model="deepseek-chat",
        json_mode=True,
        temperature=0.2,
    )
