from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class Secrets(BaseSettings):
    deepseek_api_key: str = Field(..., alias="DEEPSEEK_API_KEY")
    deepseek_api_url: str = Field(
        "https://api.deepseek.com/v1/chat/completions",
        alias="DEEPSEEK_API_URL",
    )

    model_config = SettingsConfigDict(
        env_file=PACKAGE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Paths(BaseModel):
    raw: Path
    extracted: Path
    cache: Path
    posts: Path
    logs: Path
    history_dir: Path
    style_seed: Path


class Models(BaseModel):
    extract: str = "deepseek-v4-flash"
    generate: str = "deepseek-v4-flash"


class Generation(BaseModel):
    max_workers: int = 4
    variants: int = 1
    default_platforms: list[str] = ["instagram", "twitter", "linkedin"]
    request_timeout_sec: int = 180
    retries: int = 3
    retry_backoff_sec: int = 8


class CrawlerCfg(BaseModel):
    links_file: Path
    user_agent: str


class Crawlers(BaseModel):
    wechat: CrawlerCfg
    sjtu_news: CrawlerCfg


class Config(BaseModel):
    paths: Paths
    models: Models
    generation: Generation
    crawlers: Crawlers
    secrets: Secrets

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        load_dotenv(PACKAGE_ROOT / ".env")
        path = config_path or PACKAGE_ROOT / "config.yaml"
        with path.open("r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        # Resolve all paths relative to PACKAGE_ROOT unless absolute.
        def _resolve(p: str) -> Path:
            pp = Path(p)
            return pp if pp.is_absolute() else (PACKAGE_ROOT / pp).resolve()

        raw["paths"] = {k: _resolve(v) for k, v in raw["paths"].items()}
        for name, cfg in raw["crawlers"].items():
            cfg["links_file"] = _resolve(cfg["links_file"])

        raw["secrets"] = Secrets()  # reads from env
        return cls(**raw)

    def ensure_dirs(self) -> None:
        for p in [
            self.paths.raw,
            self.paths.extracted,
            self.paths.cache,
            self.paths.posts,
            self.paths.logs,
        ]:
            p.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_config() -> Config:
    cfg = Config.load()
    cfg.ensure_dirs()
    return cfg
