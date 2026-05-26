import pytest

from copy_workflow.models import Extract


def _minimal(**overrides):
    base = {
        "title_zh": "标题",
        "title_en": "Title",
        "key_sentences_zh": ["一句话。"],
        "key_sentences_en": ["one sentence."],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FLASE", False),  # legacy typo from old pipeline
        ("yes", True),
        ("no", False),
        ("", False),
        (None, False),
        (1, True),
        (0, False),
    ],
)
def test_emoji_flag_parsing(value, expected):
    e = Extract.model_validate(_minimal(emoji_flag=value))
    assert e.emoji_flag is expected


def test_date_normalization_to_none():
    for raw in ["无", "None", "", None]:
        e = Extract.model_validate(_minimal(date=raw))
        assert e.date is None


def test_date_kept_when_valid():
    e = Extract.model_validate(_minimal(date="2025-03-01"))
    assert e.date == "2025-03-01"


def test_platforms_lowercased_and_split():
    e = Extract.model_validate(_minimal(platforms="INSTAGRAM, TWITTER"))
    assert e.platforms == ["instagram", "twitter"]


def test_platforms_list_lowercased():
    e = Extract.model_validate(_minimal(platforms=["LinkedIn", "Facebook"]))
    assert e.platforms == ["linkedin", "facebook"]


def test_unknown_platform_rejected():
    with pytest.raises(Exception):
        Extract.model_validate(_minimal(platforms=["myspace"]))
