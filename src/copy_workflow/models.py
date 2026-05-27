from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .platforms import Platform, normalize_platform


class Extract(BaseModel):
    """Bilingual structured extraction from a source article."""

    source_path: str = ""
    title_zh: str
    title_en: str
    date: str | None = None  # YYYY-MM-DD or None

    key_sentences_zh: list[str] = Field(default_factory=list)
    key_sentences_en: list[str] = Field(default_factory=list)

    audience: str = "general"
    style_type: str = "campus"
    platforms: list[Platform] = Field(default_factory=lambda: ["instagram"])
    emoji_flag: bool = False
    emoji_suggestions: list[str] = Field(default_factory=list)

    @field_validator("emoji_flag", mode="before")
    @classmethod
    def _parse_emoji_flag(cls, v: Any) -> bool:
        # Tolerate the legacy "FLASE"/"TRUE" string garbage.
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        if s in {"true", "yes", "1", "t"}:
            return True
        if s in {"false", "no", "0", "f", "flase"}:  # 'flase' is the legacy typo
            return False
        return False

    @field_validator("date", mode="before")
    @classmethod
    def _normalise_date(cls, v: Any) -> str | None:
        if not v:
            return None
        s = str(v).strip()
        if s.lower() in {"无", "none", "null"}:
            return None
        return s

    @field_validator("platforms", mode="before")
    @classmethod
    def _lower_platforms(cls, v: Any) -> Any:
        if v is None:
            return ["instagram"]
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",")]
        return [normalize_platform(str(p)) for p in v if p]


class Post(BaseModel):
    """A single generated post for one (article, platform, variant)."""

    article_slug: str
    platform: Platform
    variant: int = 1
    title: str
    body: str
    model: str
    prompt_version: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    quality_score: int | None = None
    quality_publishable: bool | None = None
    quality_needs_rewrite: bool | None = None
    quality_issues: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("platform", mode="before")
    @classmethod
    def _normalise_platform(cls, v: Any) -> Platform:
        return normalize_platform(str(v))
