from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import Config
from .extract import _split_prompt
from .llm import DeepSeekClient, call_with_validation, load_prompt
from .models import Extract, Post


class QualityIssue(BaseModel):
    category: Literal[
        "factuality",
        "platform_fit",
        "style_fit",
        "clarity",
        "engagement",
        "constraints",
        "other",
    ]
    severity: Literal["low", "medium", "high"]
    message: str
    suggestion: str = ""


class QualityReview(BaseModel):
    score: int = Field(ge=0, le=100)
    publishable: bool
    needs_rewrite: bool | None = None
    issues: list[QualityIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, value: object) -> int:
        try:
            score = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            score = 0
        return max(0, min(score, 100))

    @model_validator(mode="after")
    def _derive_rewrite_flag(self) -> "QualityReview":
        has_high_issue = any(issue.severity == "high" for issue in self.issues)
        if self.needs_rewrite is None or (has_high_issue and not self.needs_rewrite):
            self.needs_rewrite = (not self.publishable) or self.score < 80 or has_high_issue
        return self


class _PostJSON(BaseModel):
    title: str
    body: str


def _format_facts(extract: Extract) -> str:
    key_zh = "\n".join(f"  - {s}" for s in extract.key_sentences_zh) or "  - (none)"
    key_en = "\n".join(f"  - {s}" for s in extract.key_sentences_en) or "  - (none)"
    return (
        f"- Title (ZH): {extract.title_zh}\n"
        f"- Title (EN): {extract.title_en}\n"
        f"- Date: {extract.date or 'n/a'}\n"
        f"- Audience: {extract.audience}\n"
        f"- Style type: {extract.style_type}\n"
        f"- Emoji allowed: {extract.emoji_flag}\n"
        f"- Emoji suggestions: {', '.join(extract.emoji_suggestions) or 'none'}\n"
        f"- Key points (ZH):\n{key_zh}\n"
        f"- Key points (EN):\n{key_en}"
    )


def _format_review(review: QualityReview) -> str:
    if not review.issues:
        return "No issues."
    return "\n".join(
        f"- [{issue.severity}] {issue.category}: {issue.message}"
        + (f" Suggestion: {issue.suggestion}" if issue.suggestion else "")
        for issue in review.issues
    )


def _with_quality(post: Post, review: QualityReview) -> Post:
    updated = post.model_copy(deep=True)
    updated.quality_score = review.score
    updated.quality_publishable = review.publishable
    updated.quality_needs_rewrite = bool(review.needs_rewrite)
    updated.quality_issues = [issue.model_dump(mode="json") for issue in review.issues]
    return updated


def review_post(
    client: DeepSeekClient,
    cfg: Config,
    extract: Extract,
    post: Post,
    *,
    style_seed: str = "",
) -> tuple[QualityReview, int, int]:
    """Returns (review, prompt_tokens, completion_tokens) — caller accumulates tokens."""
    system, user_tmpl = _split_prompt(load_prompt("review_post.v1.md"))
    user = (
        user_tmpl.replace("{platform}", post.platform)
        .replace("{title}", post.title)
        .replace("{body}", post.body)
        .replace("{article_facts}", _format_facts(extract))
        .replace("{style_seed}", style_seed or "(no style reference)")
    )
    review, resp = call_with_validation(
        client,
        system=system,
        user=user,
        model=cfg.models.generate,
        schema=QualityReview,
        temperature=0.2,
    )
    return review, resp.prompt_tokens, resp.completion_tokens  # type: ignore[return-value]


def revise_post(
    client: DeepSeekClient,
    cfg: Config,
    extract: Extract,
    post: Post,
    review: QualityReview,
    *,
    style_seed: str = "",
) -> Post:
    system, user_tmpl = _split_prompt(load_prompt("revise_post.v1.md"))
    user = (
        user_tmpl.replace("{platform}", post.platform)
        .replace("{title}", post.title)
        .replace("{body}", post.body)
        .replace("{article_facts}", _format_facts(extract))
        .replace("{style_seed}", style_seed or "(no style reference)")
        .replace("{quality_review}", _format_review(review))
    )
    payload, resp = call_with_validation(
        client,
        system=system,
        user=user,
        model=cfg.models.generate,
        schema=_PostJSON,
        temperature=0.5,
    )
    revised = post.model_copy(
        update={
            "title": payload.title,
            "body": payload.body,
            "prompt_tokens": post.prompt_tokens + resp.prompt_tokens,
            "completion_tokens": post.completion_tokens + resp.completion_tokens,
        }
    )
    return _with_quality(revised, review)


def review_and_maybe_revise(
    client: DeepSeekClient,
    cfg: Config,
    extract: Extract,
    post: Post,
    *,
    style_seed: str = "",
    min_score: int = 80,
) -> tuple[Post, QualityReview | None]:
    """Review the post; revise if needed. Failures are graceful — returns the
    original post with review=None if any LLM call in the quality step fails."""
    try:
        review, in_tok, out_tok = review_post(client, cfg, extract, post, style_seed=style_seed)
    except Exception as e:
        from loguru import logger
        logger.warning({"event": "quality_review_failed", "error": repr(e), "slug": post.article_slug})
        return post, None

    # accumulate review tokens into post (was lost before)
    post = post.model_copy(update={
        "prompt_tokens": post.prompt_tokens + in_tok,
        "completion_tokens": post.completion_tokens + out_tok,
    })

    should_revise = bool(review.needs_rewrite) or review.score < min_score or not review.publishable
    if should_revise:
        try:
            return revise_post(client, cfg, extract, post, review, style_seed=style_seed), review
        except Exception as e:
            from loguru import logger
            logger.warning({"event": "quality_revise_failed", "error": repr(e), "slug": post.article_slug})
            return _with_quality(post, review), review
    return _with_quality(post, review), review
