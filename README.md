# copy_workflow

A Chinese-to-English social-media copywriting pipeline.

```
crawl  →  extract (bilingual)  →  generate (per-platform)  →  markdown
```

Built to replace a loose collection of `.py` scripts. Key improvements over the
legacy code:

- One bilingual extraction call (no separate translation pass) → ~50% fewer API calls
- Thread-pool concurrency for LLM calls (configurable)
- Content-hash disk cache so reruns are free and crashes resume cleanly
- Pydantic-validated JSON outputs with one auto-repair retry
- Per-platform prompt templates (Instagram / Twitter / LinkedIn / Facebook / WeChat)
- Secrets in `.env`, paths in `config.yaml`
- Single `copy-workflow` CLI entrypoint

## Setup

```bash
cd copy_workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env
# put your rotated DeepSeek key into .env
```

## Run as a Streamlit web app (recommended)

Self-contained single file — no need to install the package.

```bash
pip install -r requirements.txt   # streamlit + deps
streamlit run app.py
```

Then open http://localhost:8501. The sidebar takes your DeepSeek API key
(or reads `DEEPSEEK_API_KEY` from the environment). Paste text, drop in
URLs, or upload `.txt` files; pick platforms; hit **开始处理**. Drafts are
viewable per platform and downloadable as `.md` or a `.zip`.

Deploy to Streamlit Cloud: point it at this repo, set `app.py` as the entry,
and add `DEEPSEEK_API_KEY` in the secrets panel.

## Run as a CLI

```bash
pip install -e .                   # installs the `copy-workflow` command
cp .env.example .env && edit .env  # put DEEPSEEK_API_KEY here

# extract structured JSON from already-crawled articles
copy-workflow extract --input ../爬虫文/微信平台

# generate per-platform markdown drafts
copy-workflow generate --platforms instagram,twitter --variants 1

# or do everything in one go
copy-workflow all --input ../爬虫文/微信平台

# crawl new articles
copy-workflow crawl wechat            # uses links file from config.yaml
copy-workflow crawl sjtu_news
```

Outputs land in `data/posts/<YYYY-MM-DD>__<slug>/<platform>.md`.

## How to add a new platform

1. Add `src/copy_workflow/prompts/generate_<name>.v1.md` (use Instagram as a template).
2. Add `<name>` to `generation.default_platforms` in `config.yaml`, or pass `--platforms <name>` on the CLI.

## How to add a new crawler

1. Add `src/copy_workflow/crawlers/<source>.py` exposing a `crawl(links_file, out_dir)` function.
2. Wire it into `cli.py` under the `crawl` subcommand.

## Layout

```
src/copy_workflow/
├── config.py        env + yaml settings
├── llm.py           DeepSeek client (retry, JSON mode, token logging)
├── cache.py         sha256 disk cache
├── models.py        pydantic schemas
├── extract.py       text → bilingual JSON
├── generate.py      JSON → platform-specific posts
├── exporters.py     posts → markdown files
├── style_seed.py    distill 历史案例 into a style summary
├── cli.py           argparse entrypoint
├── crawlers/        wechat.py, sjtu_news.py
└── prompts/         versioned .md templates
```
