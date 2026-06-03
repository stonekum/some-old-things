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


def test_rewrite_presets_have_stable_actions():
    app_mod = _load_app_module()

    assert list(app_mod.REWRITE_PRESETS) == ["shorter", "natural", "platform_fit", "less_ai"]
    assert app_mod.REWRITE_PRESETS["shorter"].label == "更短一点"
    assert app_mod.REWRITE_PRESETS["natural"].label == "更自然"
    assert app_mod.REWRITE_PRESETS["platform_fit"].label == "更适合平台"
    assert app_mod.REWRITE_PRESETS["less_ai"].label == "降低 AI 味"


def test_available_rewrite_presets_adds_quality_only_when_issues_exist():
    app_mod = _load_app_module()
    post = app_mod.Post(
        article_slug="article",
        platform="instagram",
        variant=1,
        title="Title",
        body="Body",
        model="deepseek-chat",
        generated_at=datetime(2026, 1, 1),
    )

    assert "quality_feedback" not in [key for key, _label in app_mod._available_rewrite_presets(post)]

    post.quality_issues = [
        {
            "category": "style_fit",
            "severity": "medium",
            "message": "Too generic",
            "suggestion": "Use concrete nouns",
        }
    ]

    assert [key for key, _label in app_mod._available_rewrite_presets(post)][-1] == "quality_feedback"


def test_rewrite_post_body_uses_current_edited_body(monkeypatch):
    app_mod = _load_app_module()
    captured = {}

    def fake_llm_call_validated(cfg, schema, **kwargs):
        captured["user"] = kwargs["user"]
        captured["temperature"] = kwargs["temperature"]
        return (
            app_mod._PostJSON(title="Rewritten title", body="Human edited body, tightened."),
            app_mod.LLMResponse(content="{}", prompt_tokens=7, completion_tokens=11, served_model="served"),
        )

    monkeypatch.setattr(app_mod, "llm_call_validated", fake_llm_call_validated)

    post = app_mod.Post(
        article_slug="article",
        platform="instagram",
        variant=1,
        title="Original title",
        body="Original body that should not be rewritten",
        model="deepseek-chat",
        generated_at=datetime(2026, 1, 1),
        prompt_tokens=2,
        completion_tokens=3,
    )
    extract = app_mod.Extract(
        title_zh="校园故事",
        title_en="Campus Story",
        key_sentences_zh=["学生参加活动。"],
        key_sentences_en=["Students joined the event."],
    )

    rewritten = app_mod.rewrite_post_body(
        app_mod.LLMConfig(api_key="test"),
        "deepseek-chat",
        extract,
        post,
        current_body="Human edited body",
        preset="shorter",
        temperature=0.6,
        no_cache=True,
    )

    assert "Current draft body:\nHuman edited body" in captured["user"]
    assert "Original body that should not be rewritten" not in captured["user"]
    assert captured["temperature"] == 0.6
    assert rewritten.title == "Rewritten title"
    assert rewritten.body == "Human edited body, tightened"
    assert rewritten.prompt_tokens == 9
    assert rewritten.completion_tokens == 14
    assert post.body == "Original body that should not be rewritten"


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


def test_strip_trailing_periods_basic():
    app_mod = _load_app_module()
    fn = app_mod._strip_trailing_periods
    assert fn("hello world.") == "hello world"
    assert fn("一段话。") == "一段话"
    assert fn("a.\n\nb。\n\nc") == "a\n\nb\n\nc"
    # 多个连续句号也清掉
    assert fn("really...") == "really"
    assert fn("真的呢。。。") == "真的呢"


def test_strip_trailing_periods_preserves_questions_and_midline():
    app_mod = _load_app_module()
    fn = app_mod._strip_trailing_periods
    # 问号、感叹号、中间句号、行末空格
    assert fn("Really?") == "Really?"
    assert fn("Wow!") == "Wow!"
    assert fn("Open this URL https://x.y/z.html") == "Open this URL https://x.y/z.html"
    # 段内的句号保留（不是行末）
    assert fn("Dr. Smith arrived today.") == "Dr. Smith arrived today"


def test_strip_trailing_periods_skips_hashtag_lines():
    app_mod = _load_app_module()
    fn = app_mod._strip_trailing_periods
    out = fn("Body line.\n\n#Foo #Bar #Baz")
    assert out == "Body line\n\n#Foo #Bar #Baz"


def test_post_to_docx_is_valid_zip_with_times_new_roman():
    app_mod = _load_app_module()
    Post = app_mod.Post
    post = Post(
        article_slug="x",
        platform="instagram",
        variant=1,
        title="Hello",
        body="paragraph one\n\nparagraph two",
        model="m",
        served_model="m",
        api_url="https://x",
        from_cache=False,
        prompt_tokens=0,
        completion_tokens=0,
        generated_at=datetime.now(),
        prompt_version="v1",
    )
    blob = app_mod.post_to_docx(post)
    # .docx 是 zip；前两字节是 PK
    assert blob[:2] == b"PK"
    # Times New Roman 必须出现在 document.xml 里
    import zipfile, io
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        assert "Times New Roman" in doc_xml
