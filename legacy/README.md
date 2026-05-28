# legacy/

> ⚠️ **不再维护、不会运行**：本目录保存的是项目重构前的原始脚本，仅作历史参考。
> 实际工作流见 `app.py`（Streamlit 单文件）和 `src/copy_workflow/`（Python 包 + CLI）。

The original loose scripts from the previous workflow, kept for reference.
The functionality in these files is now provided by the `copy_workflow` package
(see the parent `README.md`).

- `微信公众号爬虫.py` → `src/copy_workflow/crawlers/wechat.py`
- `校内新闻网爬虫.py`, `交大新闻网下载.py` → `src/copy_workflow/crawlers/sjtu_news.py`
- `重点摘录转csv.py` (extraction) + `重点翻译英文.py` (translation) → merged into `src/copy_workflow/extract.py`
- `文案生成.py` → `src/copy_workflow/generate.py` + `src/copy_workflow/exporters.py`
- `网页视频下载.py`, `untitled2.py`, `untitled4.py` → utility / scratch files, no replacement needed.

**Note:** the API key originally embedded in these files has been redacted to
`sk-REDACTED-rotate-me`. The original key was leaked and should be rotated in
the DeepSeek console before reusing the new pipeline.
