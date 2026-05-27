from pathlib import Path

from copy_workflow import cli
from copy_workflow.extract import extract_dir


class _Cfg:
    class Generation:
        max_workers = 2

    generation = Generation()

    class Paths:
        extracted: Path

    paths = Paths()


def test_extract_dir_finds_nested_txt_when_extract_already_exists(tmp_path):
    cfg = _Cfg()
    cfg.paths.extracted = tmp_path / "extracted"
    cfg.paths.posts = tmp_path / "posts"
    cfg.paths.cache = tmp_path / "cache"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.extracted.mkdir()
    nested = tmp_path / "raw" / "sjtu_news" / "2026-05-28"
    nested.mkdir(parents=True)
    (nested / "story.txt").write_text("source", encoding="utf-8")
    expected = cfg.paths.extracted / "story.json"
    expected.write_text('{"title_zh":"旧","title_en":"Old"}', encoding="utf-8")

    written = extract_dir(cfg, tmp_path / "raw")

    assert written == [expected]


def test_all_generates_only_extracts_from_current_run(monkeypatch, tmp_path):
    current_extract = tmp_path / "current.json"
    seen = {}

    cfg = _Cfg()
    cfg.paths.extracted = tmp_path / "extracted"
    monkeypatch.setattr(cli, "get_config", lambda: cfg)
    monkeypatch.setattr(cli, "extract_dir", lambda *args, **kwargs: [current_extract])

    def fake_load_extracts(cfg, paths=None):
        seen["paths"] = paths
        return ["current-extract"]

    monkeypatch.setattr(cli, "load_extracts", fake_load_extracts)
    monkeypatch.setattr(cli, "generate_all", lambda cfg, extracts, platforms=None, variants=None: ["post"])
    monkeypatch.setattr(cli, "export_all", lambda cfg, posts: [tmp_path / "post.md"])

    args = type(
        "Args",
        (),
        {
            "input": str(tmp_path),
            "limit": None,
            "no_cache": False,
            "platforms": None,
            "variants": None,
        },
    )()

    assert cli.cmd_all(args) == 0
    assert seen["paths"] == [current_extract]
