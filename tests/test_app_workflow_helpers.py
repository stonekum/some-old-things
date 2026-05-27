import importlib.util
import sys
from datetime import datetime
from pathlib import Path


def _load_app_module():
    spec = importlib.util.spec_from_file_location(
        "_app_workflow_under_test",
        Path(__file__).resolve().parents[1] / "app.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_app_workflow_under_test"] = module
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        pass
    return module


def test_llm_call_validated_can_bypass_cache(monkeypatch):
    app_mod = _load_app_module()
    calls = []

    def fake_llm_chat(*args, **kwargs):
        calls.append(kwargs.get("no_cache"))
        return app_mod.LLMResponse(content='{"title":"Title","body":"Body"}')

    monkeypatch.setattr(app_mod, "llm_chat", fake_llm_chat)

    payload, _ = app_mod.llm_call_validated(
        app_mod.LLMConfig(api_key="test"),
        app_mod._PostJSON,
        system="system",
        user="user",
        model="model",
        no_cache=True,
    )

    assert payload.title == "Title"
    assert calls == [True]


def test_posts_from_article_state_use_edited_body():
    app_mod = _load_app_module()
    post = app_mod.Post(
        article_slug="article",
        platform="instagram",
        variant=1,
        title="Original title",
        body="Original body",
        model="deepseek-chat",
        generated_at=datetime(2026, 1, 1),
    )
    article = {"name": "article", "posts": [post.model_dump(mode="json")]}
    state = {app_mod._post_body_key("article", post): "Edited body"}

    [edited] = app_mod._posts_from_article_state(article, state)

    assert edited.body == "Edited body"
    assert post.body == "Original body"


def test_app_extract_accepts_xiaohongshu_platform_aliases():
    app_mod = _load_app_module()

    extract = app_mod.Extract(
        title_zh="校园故事",
        title_en="Campus Story",
        key_sentences_zh=["学生参加活动。"],
        key_sentences_en=["Students joined the event."],
        platforms=["rednote", "小红书"],
    )

    assert extract.platforms == ["xiaohongshu", "xiaohongshu"]
    assert "xiaohongshu" in app_mod.GEN_PROMPTS
