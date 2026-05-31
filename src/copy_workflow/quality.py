from __future__ import annotations

import re
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


def _paragraph_count(body: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()])


def _plain_text_issues(post: Post) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if re.search(r"(\*\*|__|`|\[[^\]]+\]\([^)]+\)|^#{1,6}\s|^\s*> )", post.body, re.MULTILINE):
        issues.append(
            QualityIssue(
                category="constraints",
                severity="high",
                message="Post body contains markdown, but platform prompts require plain text.",
                suggestion="Remove markdown formatting and keep plain text only.",
            )
        )
    return issues


def _hashtag_issues(
    post: Post,
    *,
    min_count: int,
    max_count: int,
    require_camel_case: bool,
    platform_label: str,
) -> list[QualityIssue]:
    hashtags = re.findall(r"(?<!\w)#([A-Za-z][A-Za-z0-9]*)", post.body)
    issues: list[QualityIssue] = []
    if not min_count <= len(hashtags) <= max_count:
        issues.append(
            QualityIssue(
                category="constraints",
                severity="high",
                message=f"{platform_label} posts must end with {min_count}-{max_count} hashtags.",
                suggestion=f"Use {min_count}-{max_count} concise hashtags at the end.",
            )
        )
    if require_camel_case:
        bad = [tag for tag in hashtags if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", tag)]
        if bad:
            issues.append(
                QualityIssue(
                    category="constraints",
                    severity="medium",
                    message=f"{platform_label} hashtags must use CamelCase.",
                    suggestion="Rewrite hashtags like #CampusLife or #ShanghaiJiaoTong.",
                )
            )
    return issues


def validate_hard_rules(post: Post) -> QualityReview:
    issues = _plain_text_issues(post)
    paragraphs = _paragraph_count(post.body)

    if post.platform == "twitter":
        if len(post.body) > 270:
            issues.append(
                QualityIssue(
                    category="constraints",
                    severity="high",
                    message="Twitter post exceeds 270 characters.",
                    suggestion="Shorten the body, including hashtags.",
                )
            )
        if paragraphs != 1:
            issues.append(
                QualityIssue(
                    category="constraints",
                    severity="medium",
                    message="Twitter posts must use one paragraph.",
                    suggestion="Remove paragraph breaks from the tweet body.",
                )
            )
        issues.extend(
            _hashtag_issues(
                post,
                min_count=2,
                max_count=3,
                require_camel_case=True,
                platform_label="Twitter",
            )
        )
    elif post.platform == "linkedin":
        # LinkedIn prompt mandates 3-5 hashtags on the last line. CamelCase
        # isn't required on LinkedIn (lowercase tags are normal there).
        issues.extend(
            _hashtag_issues(
                post,
                min_count=3,
                max_count=5,
                require_camel_case=False,
                platform_label="LinkedIn",
            )
        )
    elif post.platform == "wechat":
        zh_len = len(re.findall(r"[\u4e00-\u9fff]", post.body))
        if not 220 <= zh_len <= 320:
            issues.append(
                QualityIssue(
                    category="constraints",
                    severity="high",
                    message="WeChat body should be roughly 220-320 Chinese characters.",
                    suggestion="Adjust the copy to fit the configured short-form range.",
                )
            )
        if not 3 <= paragraphs <= 4:
            issues.append(
                QualityIssue(
                    category="constraints",
                    severity="medium",
                    message="WeChat body should use 3-4 natural paragraphs.",
                    suggestion="Split the body into 3 or 4 short paragraphs.",
                )
            )

    publishable = not any(issue.severity == "high" for issue in issues)
    return QualityReview(
        score=100 if publishable else 0,
        publishable=publishable,
        needs_rewrite=not publishable or bool(issues),
        issues=issues,
        strengths=[],
    )


def _merge_reviews(hard: QualityReview, llm: QualityReview) -> QualityReview:
    publishable = hard.publishable and llm.publishable
    issues = [*hard.issues, *llm.issues]
    score = min(hard.score, llm.score)
    return QualityReview(
        score=score,
        publishable=publishable,
        needs_rewrite=(not publishable) or score < 80 or any(i.severity == "high" for i in issues),
        issues=issues,
        strengths=llm.strengths,
    )


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
    hard_review = validate_hard_rules(post)
    try:
        llm_review, in_tok, out_tok = review_post(client, cfg, extract, post, style_seed=style_seed)
        review = _merge_reviews(hard_review, llm_review)
    except Exception as e:
        from loguru import logger
        logger.warning({"event": "quality_review_failed", "error": repr(e), "slug": post.article_slug})
        failed = QualityReview(
            score=0,
            publishable=False,
            needs_rewrite=True,
            issues=[
                *hard_review.issues,
                QualityIssue(
                    category="constraints",
                    severity="high",
                    message="Quality review failed; post must not be treated as publishable.",
                    suggestion="Run quality review again before publishing.",
                ),
            ],
        )
        return _with_quality(post, failed), None

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
