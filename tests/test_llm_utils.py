from copy_workflow.llm import parse_json_strict


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
