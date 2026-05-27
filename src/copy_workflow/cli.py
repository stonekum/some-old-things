from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from .config import get_config
from .crawlers import sjtu_news, wechat
from .exporters import export_all
from .extract import extract_dir, load_extracts
from .generate import generate_all


def _parse_platforms(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def _parse_extract_paths(raw: str | None) -> list[Path] | None:
    if not raw:
        return None
    paths: list[Path] = []
    for item in [p.strip() for p in raw.split(",") if p.strip()]:
        p = Path(item).resolve()
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.json")))
        else:
            paths.append(p)
    return paths


def _generate_from_extract_paths(
    cfg,
    args: argparse.Namespace,
    extract_paths: list[Path] | None = None,
) -> int:
    extracts = load_extracts(cfg, paths=extract_paths)
    scope = "selected" if extract_paths is not None else "all"
    if not extracts:
        print("no extracts found; run `extract` first", file=sys.stderr)
        return 1
    print(f"generating from {len(extracts)} {scope} extracts")
    posts = generate_all(
        cfg,
        extracts,
        platforms=_parse_platforms(args.platforms),
        variants=args.variants,
    )
    paths = export_all(cfg, posts)
    print(f"wrote {len(paths)} markdown files under {cfg.paths.posts}")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    cfg = get_config()
    if args.source == "wechat":
        n = wechat.crawl(cfg)
        next_input = cfg.paths.raw / "wechat"
    elif args.source == "sjtu_news":
        n = sjtu_news.crawl(cfg)
        next_input = cfg.paths.raw / "sjtu_news"
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2
    print(f"crawled {n} articles into {cfg.paths.raw}")
    print(f"next: copy-workflow extract --input {next_input}")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    cfg = get_config()
    input_dir = Path(args.input).resolve()
    if not input_dir.exists():
        print(f"input dir does not exist: {input_dir}", file=sys.stderr)
        return 2
    written = extract_dir(cfg, input_dir, limit=args.limit, no_cache=args.no_cache)
    print(f"extracted {len(written)} articles to {cfg.paths.extracted}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = get_config()
    return _generate_from_extract_paths(cfg, args, _parse_extract_paths(getattr(args, "extracts", None)))


def cmd_all(args: argparse.Namespace) -> int:
    cfg = get_config()
    input_dir = Path(args.input).resolve()
    if not input_dir.exists():
        print(f"input dir does not exist: {input_dir}", file=sys.stderr)
        return 2
    written = extract_dir(cfg, input_dir, limit=args.limit, no_cache=args.no_cache)
    print(f"extracted {len(written)} articles to {cfg.paths.extracted}")
    return _generate_from_extract_paths(cfg, args, written)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copy-workflow")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_crawl = sub.add_parser("crawl", help="fetch source articles")
    p_crawl.add_argument("source", choices=["wechat", "sjtu_news"])
    p_crawl.set_defaults(func=cmd_crawl)

    p_extract = sub.add_parser("extract", help="extract bilingual JSON from raw .txt")
    p_extract.add_argument("--input", required=True, help="directory of .txt sources")
    p_extract.add_argument("--limit", type=int, default=None)
    p_extract.add_argument("--no-cache", action="store_true")
    p_extract.set_defaults(func=cmd_extract)

    p_gen = sub.add_parser("generate", help="generate per-platform markdown posts")
    p_gen.add_argument("--extracts", default=None, help="JSON file/dir or comma list; defaults to all extracts")
    p_gen.add_argument("--platforms", default=None, help="comma list, e.g. instagram,twitter")
    p_gen.add_argument("--variants", type=int, default=None)
    p_gen.set_defaults(func=cmd_generate)

    p_all = sub.add_parser("all", help="extract then generate")
    p_all.add_argument("--input", required=True)
    p_all.add_argument("--limit", type=int, default=None)
    p_all.add_argument("--no-cache", action="store_true")
    p_all.add_argument("--platforms", default=None)
    p_all.add_argument("--variants", type=int, default=None)
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
