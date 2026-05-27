from __future__ import annotations

from typing import TypeAlias


Platform: TypeAlias = str

CANONICAL_PLATFORMS: tuple[Platform, ...] = (
    "instagram",
    "twitter",
    "linkedin",
    "facebook",
    "wechat",
    "xiaohongshu",
)

ALIASES: dict[str, Platform] = {
    "ig": "instagram",
    "x": "twitter",
    "twitter/x": "twitter",
    "rednote": "xiaohongshu",
    "red note": "xiaohongshu",
    "little red book": "xiaohongshu",
    "小红书": "xiaohongshu",
}

PROMPT_FILES: dict[Platform, str] = {
    platform: f"generate_{platform}.v1.md" for platform in CANONICAL_PLATFORMS
}


def normalize_platform(value: str) -> Platform:
    key = value.strip().lower()
    platform = ALIASES.get(key, key)
    if platform not in CANONICAL_PLATFORMS:
        raise ValueError(f"Unsupported platform: {value}")
    return platform


def valid_platforms(values: list[str] | tuple[str, ...]) -> list[Platform]:
    platforms: list[Platform] = []
    for value in values:
        try:
            platforms.append(normalize_platform(value))
        except ValueError:
            continue
    return platforms
