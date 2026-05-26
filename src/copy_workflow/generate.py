from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

from loguru import logger
from pydantic import BaseModel

from .config import Config
from .extract import _split_prompt, _slug_from_filename
from .llm import DeepSeekClient, call_with_validation, load_prompt
from .models import Extract, Post, Platform
from .style_seed import build_style_seed, load_style_seed


PROMPT_VERSION_FMT = "generate_{platform}.v1"


class _PostJSON(BaseModel):
    title: str
    body: str


def _emoji_directive(extract: Extract) -> str:
    if extract.emoji_flag and extract.emoji_suggestions:
        return f"use emoji sparingly; appropriate options: {', '.join(extract.emoji_suggestions)}"
    if extract.emoji_flag:
        return "use 1-2 tasteful emoji"
    return "no emoji"


def _date_directive(extract: Extract) -> str:
    return f"include the date {extract.date} naturally" if extract.date else "do not reference any date"


def _format_user(template: str, extract: Extract, style_seed: str, platform: str) -> str:
    key_zh = "\n".join(f"  - {s}" for s in extract.key_sentences_zh)
    key_en = "\n".join(f"  - {s}" for s in extract.key_sentences_en)
    return (
        template.replace("{title_zh}", extract.title_zh)
        .replace("{title_en}", extract.title_en)
        .replace("{date}", extract.date or "n/a")
        .replace("{audience}", extract.audience)
        .replace("{key_sentences_zh}", key_zh or "  - (none)")
        .replace("{key_sentences_en}", key_en or "  - (none)")
        .replace("{emoji_directive}", _emoji_directive(extract))
        .replace("{date_directive}", _date_directive(extract))
        .replace("{style_seed}", style_seed)
    )


def generate_for_extract(
    client: DeepSeekClient,
    cfg: Config,
    extract: Extract,
    style_seed: str,
    platforms: list[Platform],
    variants: int,
) -> list[Post]:
    posts: list[Post] = []
    article_slug = _slug_from_filename(Path(extract.source_path or extract.title_en or "untitled"))

    for platform in platforms:
        prompt_file = f"generate_{platform}.v1.md"
        try:
            system, user_tmpl = _split_prompt(load_prompt(prompt_file))
        except FileNotFoundError:
            logger.warning({"event": "no_prompt_for_platform", "platform": platform})
            continue
        user = _format_user(user_tmpl, extract, style_seed, platform)

        for variant in range(1, variants + 1):
            # vary temperature slightly per variant for diversity
            temp = 0.7 + 0.1 * (variant - 1)
            payload, resp = call_with_validation(
                client,
                system=system,
                user=user,
                model=cfg.models.generate,
                schema=_PostJSON,
                temperature=min(temp, 1.2),
            )
            posts.append(
                Post(
                    article_slug=article_slug,
                    platform=platform,
                    variant=variant,
                    title=payload.title,
                    body=payload.body,
                    model=cfg.models.generate,
                    prompt_version=PROMPT_VERSION_FMT.format(platform=platform),
                    prompt_tokens=resp.prompt_tokens,
                    completion_tokens=resp.completion_tokens,
                )
            )
    return posts


def generate_all(
    cfg: Config,
    extracts: list[Extract],
    *,
    platforms: list[str] | None = None,
    variants: int | None = None,
) -> list[Post]:
    """Run generation for all extracts concurrently. Returns flat list of Posts."""
    client = DeepSeekClient(cfg)

    # build / refresh style seed once
    build_style_seed(cfg.paths.history_dir, cfg.paths.style_seed)
    seed_text = load_style_seed(cfg.paths.style_seed)

    variants = variants or cfg.generation.variants
    requested = platforms or cfg.generation.default_platforms

    all_posts: list[Post] = []

    def _job(ex: Extract) -> list[Post]:
        # intersect requested platforms with what the extractor recommended
        chosen = [p for p in requested if p in ex.platforms] or requested
        chosen = [p for p in chosen if p in {"instagram", "twitter", "linkedin", "facebook", "wechat"}]
        return generate_for_extract(client, cfg, ex, seed_text, chosen, variants)

    with ThreadPoolExecutor(max_workers=cfg.generation.max_workers) as pool:
        futures = [pool.submit(_job, ex) for ex in extracts]
        for fut in as_completed(futures):
            try:
                all_posts.extend(fut.result())
            except Exception as e:
                logger.error({"event": "generate_failed", "error": repr(e)})

    logger.info({"event": "generate_done", "count": len(all_posts)})
    return all_posts
