from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger

from .config import Config
from .llm import DeepSeekClient, call_with_validation, load_prompt
from .models import Extract


PROMPT_VERSION = "extract.v1"


def _split_prompt(template: str) -> tuple[str, str]:
    # Templates are formatted as:  SYSTEM: ...  USER: ...
    m = re.match(r"\s*SYSTEM:\s*(.*?)\n\s*USER:\s*(.*)\Z", template, re.DOTALL)
    if not m:
        raise ValueError("Prompt template missing SYSTEM:/USER: markers")
    return m.group(1).strip(), m.group(2).strip()


def _slug_from_filename(path: Path) -> str:
    stem = path.stem
    # legacy filenames carry a timestamp suffix _YYYYMMDDhhmmss — strip it for the slug
    stem = re.sub(r"_\d{14}$", "", stem)
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", stem)
    return safe[:80].strip("_") or "untitled"


def extract_one(client: DeepSeekClient, cfg: Config, source_path: Path) -> Extract:
    text = source_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"empty source: {source_path}")

    system, user_tmpl = _split_prompt(load_prompt("extract.v1.md"))
    user = user_tmpl.replace("{source_text}", text[:8000])  # generous source budget

    extract, _ = call_with_validation(
        client,
        system=system,
        user=user,
        model=cfg.models.extract,
        schema=Extract,
        temperature=0.2,
    )
    extract.source_path = str(source_path)
    return extract


def extract_dir(
    cfg: Config,
    input_dir: Path,
    *,
    limit: int | None = None,
    no_cache: bool = False,
) -> list[Path]:
    """Run extraction on every .txt in input_dir; write JSON files. Returns paths written."""
    client = DeepSeekClient(cfg)
    files = sorted(p for p in input_dir.rglob("*.txt") if p.is_file())
    if limit:
        files = files[:limit]

    written: list[Path] = []

    def _job(p: Path) -> Path | None:
        slug = _slug_from_filename(p)
        out = cfg.paths.extracted / f"{slug}.json"
        if out.exists() and not no_cache:
            logger.info({"event": "extract_skip_existing", "out": str(out)})
            return out
        try:
            ex = extract_one(client, cfg, p)
            out.write_text(ex.model_dump_json(indent=2), encoding="utf-8")
            return out
        except Exception as e:
            logger.error({"event": "extract_failed", "source": str(p), "error": repr(e)})
            return None

    with ThreadPoolExecutor(max_workers=cfg.generation.max_workers) as pool:
        for fut in as_completed(pool.submit(_job, f) for f in files):
            r = fut.result()
            if r:
                written.append(r)

    logger.info({"event": "extract_done", "count": len(written), "input_dir": str(input_dir)})
    return written


def load_extracts(cfg: Config, paths: list[Path] | None = None) -> list[Extract]:
    out: list[Extract] = []
    extract_paths = paths if paths is not None else sorted(cfg.paths.extracted.glob("*.json"))
    for p in extract_paths:
        try:
            out.append(Extract.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception as e:
            logger.warning({"event": "extract_load_failed", "path": str(p), "error": repr(e)})
    return out
