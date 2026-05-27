from datetime import datetime
from pathlib import Path

import yaml

from copy_workflow.exporters import write_markdown
from copy_workflow.models import Extract, Post
from copy_workflow.quality import (
    QualityIssue,
    QualityReview,
    review_and_maybe_revise,
    validate_hard_rules,
)


class _FakeConfig:
    class Models:
        generate = "deepseek-chat"

    models = Models()


class _FakeClient:
    def __init__(self, review_payload, revise_payload=None):
        self.review_payload = review_payload
        self.revise_payload = revise_payload or {"title": "Revised", "body": "Revised body"}
        self.calls = []

    def chat(self, *, system, user, model, json_mode=False, temperature=0.7, no_cache=False):
        from copy_workflow.llm import LLMResponse

        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "temperature": temperature,
            }
        )
        payload = self.review_payload if len(self.calls) == 1 else self.revise_payload
        return LLMResponse(
            content=__import__("json").dumps(payload),
            raw={},
            prompt_tokens=10,
            completion_tokens=5,
        )


def _extract():
    return Extract(
        title_zh="校园活动",
        title_en="Campus Event",
        key_sentences_zh=["学生参加活动。"],
        key_sentences_en=["Students joined the event."],
        platforms=["instagram"],
    )


def _post():
    return Post(
        article_slug="campus-event",
        platform="instagram",
        variant=1,
        title="Campus Event",
        body="Students joined the event. Tap the link in bio.",
        model="deepseek-chat",
        prompt_version="generate_instagram.v1",
        generated_at=datetime(2026, 1, 1),
    )


def test_quality_review_clamps_score_and_derives_rewrite_flag():
    review = QualityReview(
        score=135,
        publishable=True,
        issues=[QualityIssue(category="clarity", severity="low", message="A little flat.")],
    )

    assert review.score == 100
    assert review.needs_rewrite is False


def test_quality_review_high_severity_issue_forces_rewrite():
    review = QualityReview(
        score=88,
        publishable=True,
        needs_rewrite=False,
        issues=[
            QualityIssue(
                category="factuality",
                severity="high",
                message="Invented an award.",
            )
        ],
    )

    assert review.needs_rewrite is True


def test_review_and_maybe_revise_keeps_high_scoring_post():
    client = _FakeClient(
        {
            "score": 91,
            "publishable": True,
            "needs_rewrite": False,
            "issues": [],
            "strengths": ["Clear and platform appropriate."],
        }
    )

    post, review = review_and_maybe_revise(client, _FakeConfig(), _extract(), _post())

    assert post.title == "Campus Event"
    assert post.quality_score == 91
    assert post.quality_publishable is True
    assert post.quality_needs_rewrite is False
    assert review.score == 91
    assert len(client.calls) == 1


def test_review_and_maybe_revise_rewrites_low_scoring_post_once():
    client = _FakeClient(
        {
            "score": 62,
            "publishable": False,
            "needs_rewrite": True,
            "issues": [
                {
                    "category": "platform_fit",
                    "severity": "high",
                    "message": "The caption is too generic.",
                    "suggestion": "Use a stronger campus-life hook.",
                }
            ],
        },
        {
            "title": "A Campus Moment",
            "body": "A sharper campus-life caption with a concrete hook.",
        },
    )

    post, review = review_and_maybe_revise(client, _FakeConfig(), _extract(), _post(), min_score=80)

    assert post.title == "A Campus Moment"
    assert post.body == "A sharper campus-life caption with a concrete hook."
    assert post.quality_score == 62
    assert post.quality_needs_rewrite is True
    assert review.issues[0].category == "platform_fit"
    assert len(client.calls) == 2


def test_write_markdown_includes_quality_frontmatter(tmp_path: Path):
    class _Cfg:
        class Paths:
            posts = tmp_path

        paths = Paths()

    post = _post()
    post.quality_score = 84
    post.quality_publishable = True
    post.quality_needs_rewrite = False
    post.quality_issues = [
        {
            "category": "engagement",
            "severity": "low",
            "message": "CTA could be more specific.",
            "suggestion": "Name the desired action.",
        }
    ]

    out = write_markdown(_Cfg(), post)
    frontmatter = out.read_text(encoding="utf-8").split("---", 2)[1]
    data = yaml.safe_load(frontmatter)

    assert data["quality_score"] == 84
    assert data["quality_publishable"] is True
    assert data["quality_issues"][0]["category"] == "engagement"


def test_hard_rules_flag_twitter_length_hashtags_and_markdown():
    post = Post(
        article_slug="campus-event",
        platform="twitter",
        variant=1,
        title="Campus Event",
        body=("**Big campus update** " * 20) + "#lowercase #TooMany #Tags #Here",
        model="deepseek-chat",
        prompt_version="generate_twitter.v1",
        generated_at=datetime(2026, 1, 1),
    )

    review = validate_hard_rules(post)

    messages = [issue.message for issue in review.issues]
    assert review.publishable is False
    assert any("270 characters" in message for message in messages)
    assert any("2-3 hashtags" in message for message in messages)
    assert any("CamelCase" in message for message in messages)
    assert any("markdown" in message.lower() for message in messages)


def test_hard_rules_flag_wechat_word_range_and_paragraphs():
    post = Post(
        article_slug="campus-event",
        platform="wechat",
        variant=1,
        title="校园活动",
        body="太短了。",
        model="deepseek-chat",
        prompt_version="generate_wechat.v1",
        generated_at=datetime(2026, 1, 1),
    )

    review = validate_hard_rules(post)

    assert review.publishable is False
    assert any("220-320" in issue.message for issue in review.issues)
    assert any("3-4" in issue.message for issue in review.issues)


def test_review_failure_marks_post_not_publishable():
    class _FailingClient:
        def chat(self, **kwargs):
            raise RuntimeError("review unavailable")

    post, review = review_and_maybe_revise(_FailingClient(), _FakeConfig(), _extract(), _post())

    assert review is None
    assert post.quality_publishable is False
    assert post.quality_needs_rewrite is True
    assert post.quality_score == 0
    assert post.quality_issues[0]["category"] == "constraints"
