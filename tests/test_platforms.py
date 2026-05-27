from copy_workflow.platforms import (
    CANONICAL_PLATFORMS,
    PROMPT_FILES,
    normalize_platform,
    valid_platforms,
)


def _extract():
    from copy_workflow.models import Extract

    return Extract(
        source_path="campus.txt",
        title_zh="校园活动",
        title_en="Campus Event",
        key_sentences_zh=["学生参加活动。"],
        key_sentences_en=["Students joined the event."],
        platforms=["xiaohongshu"],
    )


def test_platform_registry_includes_required_platforms_and_prompt_files():
    assert set(CANONICAL_PLATFORMS) >= {
        "instagram",
        "twitter",
        "linkedin",
        "facebook",
        "wechat",
        "xiaohongshu",
    }
    assert PROMPT_FILES["xiaohongshu"] == "generate_xiaohongshu.v1.md"


def test_platform_aliases_normalize_to_canonical_names():
    assert normalize_platform("X") == "twitter"
    assert normalize_platform("rednote") == "xiaohongshu"
    assert normalize_platform("小红书") == "xiaohongshu"


def test_valid_platforms_filters_unknown_values_and_preserves_order():
    assert valid_platforms(["Instagram", "rednote", "myspace", "X"]) == [
        "instagram",
        "xiaohongshu",
        "twitter",
    ]


def test_generate_for_extract_uses_prompt_registry_for_xiaohongshu(monkeypatch):
    from copy_workflow import generate

    loaded = []

    def fake_load_prompt(filename):
        loaded.append(filename)
        return (
            "SYSTEM:\nSystem text.\n\n"
            "USER:\nWrite {title_zh} {title_en} {key_sentences_zh} {key_sentences_en}."
        )

    class Resp:
        prompt_tokens = 1
        completion_tokens = 2

    def fake_call_with_validation(*args, schema, **kwargs):
        return schema(title="小红书标题", body="第一段。\n\n第二段。\n\n第三段。"), Resp()

    def fake_review_and_maybe_revise(client, cfg, extract, post, *, style_seed=""):
        return post, None

    class Cfg:
        class Models:
            generate = "deepseek-chat"

        models = Models()

    monkeypatch.setattr(generate, "load_prompt", fake_load_prompt)
    monkeypatch.setattr(generate, "call_with_validation", fake_call_with_validation)
    monkeypatch.setattr(generate, "review_and_maybe_revise", fake_review_and_maybe_revise)

    posts = generate.generate_for_extract(
        client=object(),
        cfg=Cfg(),
        extract=_extract(),
        style_seed="",
        platforms=["rednote"],
        variants=1,
    )

    assert loaded == ["generate_xiaohongshu.v1.md"]
    assert posts[0].platform == "xiaohongshu"
    assert posts[0].prompt_version == "generate_xiaohongshu.v1"
