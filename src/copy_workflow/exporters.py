from __future__ import annotations

from pathlib import Path

import yaml
from loguru import logger

from .config import Config
from .models import Post


def write_markdown(cfg: Config, post: Post) -> Path:
    out_dir = cfg.paths.posts / post.article_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    variant_suffix = "" if post.variant == 1 else f".v{post.variant}"
    out = out_dir / f"{post.platform}{variant_suffix}.md"

    frontmatter = {
        "platform": post.platform,
        "variant": post.variant,
        "title": post.title,
        "model": post.model,
        "prompt_version": post.prompt_version,
        "generated_at": post.generated_at.isoformat(timespec="seconds"),
        "prompt_tokens": post.prompt_tokens,
        "completion_tokens": post.completion_tokens,
    }
    if post.quality_score is not None:
        frontmatter.update(
            {
                "quality_score": post.quality_score,
                "quality_publishable": post.quality_publishable,
                "quality_needs_rewrite": post.quality_needs_rewrite,
                "quality_issues": post.quality_issues,
            }
        )

    content = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + post.body.strip()
        + "\n"
    )
    out.write_text(content, encoding="utf-8")
    return out


def export_all(cfg: Config, posts: list[Post]) -> list[Path]:
    written = []
    for post in posts:
        p = write_markdown(cfg, post)
        written.append(p)
    logger.info({"event": "export_done", "count": len(written)})
    return written
