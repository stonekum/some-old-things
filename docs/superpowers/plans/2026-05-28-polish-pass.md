# Polish Pass — UX + Professionalism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the repo to feel like a professional Streamlit app, not a research sketch — fix stale references, sharpen first-run UX, add standard repo hygiene. Zero functional rewrites.

**Architecture:** Three-phase pass. Phase 1 fixes stale data (P0 — wrong defaults / dead aliases / inaccurate docs). Phase 2 polishes first-run UX (sidebar order, jargon labels, sample data, less-overwhelming defaults). Phase 3 adds repo hygiene (LICENSE, CHANGELOG, Streamlit theme, .env coverage, dead dirs).

**Tech Stack:** Streamlit, pydantic, DeepSeek API, pytest. No new deps required.

---

## Self-Review Findings (the basis for this plan)

After three review passes (UX / package / repo polish), the highest-ROI gaps:

### P0 — stale data that misleads users
1. `config.yaml:14-15` defaults `models.extract`/`generate` to `deepseek-chat` — a now-removed legacy alias. CLI users will hit a dead alias.
2. `src/copy_workflow/config.py:41-42` `Models` schema defaults to `deepseek-chat` — same issue.
3. `README.md:39` says `pip install -r requirements.txt` while `pyproject.toml` has `[streamlit]` optional dep — two install paths conflict.
4. `README.md` makes no mention of SJTU 内网 provider, thinking mode toggle, or V4 model names — all shipped.

### P1 — first-session UX friction
5. **Sidebar order is muddled** (`app.py:1198-1334`): the diagnostic buttons `📋 列出该后端支持的模型` and `🔌 测试 API 连接` sit between essential setup and platform selection. They should be tucked into an "advanced" expander.
6. **"Temperature" is dev jargon** (`app.py:1309`) — should be "创意度 / 随机性".
7. **Default 4 platforms** (`app.py:1302`) is overwhelming for first-run — better default 2 (instagram + xiaohongshu, the most common for the target user).
8. **Stale "吃了缓存" warning** in connection-test failure copy (`app.py:1294-1295`) — that bug was fixed in v3 → v4 cache key.
9. **No sample data button** — a new user without their own article can't try the app without first writing/pasting content.
10. **Quality threshold slider label** (`app.py:1322-1325`) "重写阈值" is unclear; should be "质量门槛" with a note on typical scores.
11. **Drift between `app.py` and `src/copy_workflow/llm.py`**: package's `llm.py` lacks the v4 fixes (thinking param, 400 fallback, body in errors, served_model, reasoning_content). Not a P0 only because the CLI path is less-trafficked, but worth flagging for users who try the CLI.

### P1 — repo hygiene
12. No `LICENSE` file.
13. No `CHANGELOG.md` despite shipping V4 upgrade, quality module, SSRF guard.
14. `.env.example` doesn't list `SJTU_API_KEY`, `APP_PASSWORD`.
15. `scripts/` directory exists but is empty.
16. `logs/` directory is in git but in `.gitignore` (oxymoron).
17. `legacy/` has no README explaining its status.

### P2 — nice-to-have
18. No `.streamlit/config.toml` (theme/page defaults).
19. No CI workflow.
20. No ruff/lint config.
21. No screenshots/demo in README.

---

## File Structure

Files this plan touches (CREATE / MODIFY annotated):

```
copy_workflow/
├── README.md                                MODIFY  (P0 stale, P1 SJTU/thinking, P2 troubleshoot)
├── LICENSE                                  CREATE  (P1)
├── CHANGELOG.md                             CREATE  (P1)
├── .env.example                             MODIFY  (P1 add SJTU/APP_PASSWORD)
├── .gitignore                               MODIFY  (P2 unify scripts/logs/data behavior)
├── config.yaml                              MODIFY  (P0 stale default model)
├── app.py                                   MODIFY  (P1 sidebar order, labels, sample data,
│                                                     remove stale text, default-platforms)
├── src/copy_workflow/
│   ├── __init__.py                          MODIFY  (P1 curate public API)
│   └── config.py                            MODIFY  (P0 stale default model)
├── .streamlit/
│   └── config.toml                          CREATE  (P2 theme + suppress telemetry)
├── legacy/
│   └── README.md                            CREATE  (P1 explain deprecation)
└── scripts/ logs/                           DELETE  (P2 dead dirs)
```

---

## Phase 1 — Stale Data Fixes (P0)

### Task 1.1: Fix `config.yaml` default model to v4-flash

**Files:**
- Modify: `config.yaml:13-15`

- [ ] **Step 1: Update model defaults**

```yaml
models:
  extract: deepseek-v4-flash
  generate: deepseek-v4-flash
```

- [ ] **Step 2: Verify CLI still parses config**

Run: `python -m copy_workflow.cli --help`
Expected: shows subcommands without error.

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: 默认模型改为 deepseek-v4-flash (deepseek-chat 已退役)"
```

---

### Task 1.2: Fix package `config.py` schema default

**Files:**
- Modify: `src/copy_workflow/config.py:40-42`

- [ ] **Step 1: Change `Models` defaults**

```python
class Models(BaseModel):
    extract: str = "deepseek-v4-flash"
    generate: str = "deepseek-v4-flash"
```

- [ ] **Step 2: Run tests**

Run: `pytest -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add src/copy_workflow/config.py
git commit -m "config: 同步包内默认模型到 v4-flash"
```

---

### Task 1.3: Update README — install path, V4, SJTU, thinking, troubleshooting

**Files:**
- Modify: `README.md`

Three concrete edits:

- [ ] **Step 1: Unify install command (around line 39)**

Replace the requirements.txt install line with the unified path:

```markdown
### 方式一：Streamlit 网页版（推荐）

```bash
pip install -e ".[streamlit]"
streamlit run app.py
```
```

- [ ] **Step 2: Add SJTU + V4 模型 + 思维链 section (after the deployment block)**

```markdown
### 模型与提供商

支持两个 API 提供商，侧边栏切换：

- **DeepSeek 官方** · 直连 `api.deepseek.com`，按 token 计费
  - `deepseek-v4-flash`（默认）· 284B/13B 激活 · 速度快、便宜
  - `deepseek-v4-pro` · 1.6T/49B 激活 · 复杂推理 / Agent / 代码
  - 旁边的 `🧠 启用思维链` 开关控制是否走 thinking mode
- **交大内网 (SJTU)** · 走 `models.sjtu.edu.cn`，免费额度大，**校外需 VPN**
  - Key 领取：`my.sjtu.edu.cn → APP → API`

旧 `deepseek-chat` / `deepseek-reasoner` alias 已于 2026-07-24 退役，本项目不再列出。
```

- [ ] **Step 3: Add 排错 section at the bottom**

```markdown
## 排错

| 症状 | 原因 / 处理 |
|---|---|
| 点生成后没反应 | API 慢响应。看 streamlit 终端的 `[llm_chat]` 日志确认是否仍在调用 |
| `400 Bad Request` 含 `response_format` | SJTU/自建代理不支持 OpenAI JSON 模式；代码会自动降级重试 |
| ping 通但生成卡住 | VPN 增加延迟，单次 10-25s × N 平台 = 几分钟；关掉质量审核可加速 |
| `ConnectionError` 连 SJTU | 检查是否开了交大 VPN |
| 切换 provider 后吃旧缓存 | v4 缓存 key 已含 api_url+thinking，不再串味；右下角"清空所有结果"可强制刷新 |
```

- [ ] **Step 4: Verify links/anchors don't break**

Run: open `README.md` in your editor, eyeball the section flow.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: 同步 README 到 V4 / SJTU / thinking mode 现状，加排错表"
```

---

### Task 1.4: Remove stale "吃了缓存" copy from connection test error

**Files:**
- Modify: `app.py:1291-1296`

- [ ] **Step 1: Edit the error message**

```python
            except Exception as e:
                st.error(
                    f"❌ 连接失败 · `{urlparse(api_url).netloc}`\n\n"
                    f"错误：`{type(e).__name__}: {e}`\n\n"
                    f"**SJTU 失败**：确认连接了交大 VPN。\n"
                    f"**DeepSeek 失败**：检查 Key 是否在 platform.deepseek.com 仍有效。"
                )
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "ui: 测试连接失败提示去掉 v3 时代'吃了缓存'残留文案"
```

---

## Phase 2 — First-run UX (P1)

### Task 2.1: Move diagnostic buttons into an "advanced" expander

**Files:**
- Modify: `app.py:1222-1296`

- [ ] **Step 1: Wrap the two diagnostic buttons in `st.expander`**

Replace the two top-level button blocks with:

```python
    with st.expander("🔧 诊断工具", expanded=False):
        # 列出后端模型
        if st.button("📋 列出该后端支持的模型", use_container_width=True, disabled=not api_key):
            # ... (existing logic unchanged)
        # 测试连接
        if st.button("🔌 测试 API 连接", use_container_width=True, disabled=not api_key):
            # ... (existing logic unchanged)
```

Keep the inner logic identical. Just move the two `if st.button(...)` blocks into the expander.

- [ ] **Step 2: Smoke-test the app**

Run: `streamlit run app.py` and confirm the expander shows up, both buttons still work.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "ui: 把'列出模型/测试连接'两个诊断按钮收进可折叠区，减少 sidebar 噪音"
```

---

### Task 2.2: Rename "Temperature" → "创意度" and add help

**Files:**
- Modify: `app.py:1309`

- [ ] **Step 1: Update slider label**

```python
    temperature = st.slider(
        "创意度 (Temperature)",
        0.0, 1.2, 0.7, 0.1,
        help="越高输出越发散有创意，越低越保守循规。0.7 适合大多数文案；0.3 适合事实型；1.0+ 适合广告/口号",
    )
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "ui: Temperature 滑条改名'创意度'并加 help"
```

---

### Task 2.3: Reduce default platforms to 2

**Files:**
- Modify: `app.py:1302`

- [ ] **Step 1: Change default**

```python
    platforms_chosen = st.multiselect(
        "目标平台",
        ["instagram", "twitter", "linkedin", "facebook", "wechat", "xiaohongshu"],
        default=["instagram", "xiaohongshu"],
        format_func=lambda p: PLATFORM_LABELS.get(p, p),
        help="可多选；不同平台会使用不同长度、语气和格式规则。",
    )
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "ui: 默认目标平台从 4 个降到 2 个 (instagram+xiaohongshu)，减少首跑负担"
```

---

### Task 2.4: Rename "重写阈值" → "质量门槛"

**Files:**
- Modify: `app.py:1321-1326`

- [ ] **Step 1: Update slider label**

```python
    min_quality_score = st.slider(
        "质量门槛",
        50, 95, 80, 5,
        help=(
            "审稿评分 0-100 低于该值则自动重写一遍。\n\n"
            "**典型分布**：80 是合格线 · 90+ 优秀 · 95+ 罕见。\n"
            "设 50 = 只重写明显差的；设 95 = 几乎都会重写"
        ),
        disabled=not enable_quality,
    )
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "ui: '重写阈值'改名'质量门槛'，help 加典型分数分布"
```

---

### Task 2.5: Add "📝 加载示例文章" button for first-time users

**Files:**
- Modify: `app.py` (after the "方式 A: 粘贴文本" col, before "方式 B: URL 抓取")

Pick a short, ideally bilingual-friendly sample paragraph.

- [ ] **Step 1: Add a constant at top of the file**

Near the existing prompt constants (around line 80), add:

```python
SAMPLE_ARTICLE = {
    "name": "示例-上海交大开学典礼",
    "text": (
        "9 月 1 日，上海交通大学举行 2026 级新生开学典礼。校长在致辞中强调，"
        "希望同学们坚守'饮水思源、爱国荣校'的精神，在交大度过的四年既要"
        "夯实专业基础，也要保持对世界的好奇与开放。当天有来自全球 60 多个国家"
        "的国际新生加入交大大家庭。"
    ),
}
```

- [ ] **Step 2: Insert button after "➕ 加入队列" in col1**

```python
        if st.button("📝 加载示例文章", use_container_width=True):
            ss.articles.append({
                "name": slugify(SAMPLE_ARTICLE["name"]),
                "text": SAMPLE_ARTICLE["text"],
            })
            st.success(f"已加入示例（队列共 {len(ss.articles)} 篇）")
            st.rerun()
```

- [ ] **Step 3: Smoke-test**

Run: `streamlit run app.py`. Click "📝 加载示例文章" — article should appear in queue, status metric should bump to 1.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "ui: 新增'加载示例文章'按钮，首次用户无需自备素材即可试跑"
```

---

## Phase 3 — Repo Hygiene (P1)

### Task 3.1: Add LICENSE (MIT)

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Write MIT license**

```
MIT License

Copyright (c) 2026 stonekum

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Update `pyproject.toml` to declare the license**

Add after the `description` line:

```toml
license = { text = "MIT" }
```

- [ ] **Step 3: Commit**

```bash
git add LICENSE pyproject.toml
git commit -m "chore: 加 MIT LICENSE"
```

---

### Task 3.2: Add CHANGELOG.md backfilling recent shipped features

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write changelog**

```markdown
# Changelog

本文件按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格记录变更。

## [Unreleased]

### UX
- 默认平台从 4 个减到 2 个，避免首跑负担
- 诊断按钮（列出模型 / 测试连接）收进可折叠区
- "Temperature" 改名"创意度"，"重写阈值"改名"质量门槛"
- 新增"加载示例文章"按钮供首次试跑

### Docs
- README 同步到 V4 模型 / SJTU / thinking mode 现状
- 加排错表
- 加 LICENSE (MIT)

## 2026-05-28

### Feat
- 升级到 DeepSeek V4 命名（deepseek-v4-flash / deepseek-v4-pro）
- 思维链由独立 checkbox 显式控制，下发 `thinking={"type":"enabled"|"disabled"}`
- 缓存 key 加入 thinking 维度 (v3 → v4)
- json_mode 4xx 自动降级 (兼容 SJTU 等代理后端)
- 单线程模式下按 LLM 调用粒度更新进度
- 连接测试结果基于 reasoning_content 实际激活情况判断

### Fix
- 缓存跨提供商串味 (cache key 加入 api_url)
- 错误显示被进度条遮挡
- timeout 从 180s/3 retry 收紧到 60s/2 retry

### Security
- API Key 服务端配置时完全隐藏输入框
- APP_PASSWORD 门禁
- SSRF 防护（_assert_safe_url + redirect 上限 + 5MB 响应上限）

### Quality
- Self-Refine 模块：generate → review (0-100 分) → 低于门槛自动重写
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: 加 CHANGELOG.md 回溯近期 V4/quality/security 变更"
```

---

### Task 3.3: Expand `.env.example` to cover all envs

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update**

```dotenv
# ============================================================
# DeepSeek 官方（默认 provider）
# 控制台：https://platform.deepseek.com/api_keys
# ============================================================
DEEPSEEK_API_KEY=sk-replace-me
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions

# ============================================================
# 交大内网（可选，校外需 VPN）
# 领取：my.sjtu.edu.cn → APP → API
# ============================================================
# SJTU_API_KEY=

# ============================================================
# Streamlit 部署密码（强烈建议在公网部署时设置）
# 未设则不启用密码门禁
# ============================================================
# APP_PASSWORD=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: .env.example 覆盖 SJTU_API_KEY / APP_PASSWORD"
```

---

### Task 3.4: Remove dead `scripts/` and `logs/` directories

**Files:**
- Delete: `scripts/`, `logs/`

- [ ] **Step 1: Check directories are empty / safe to delete**

Run: `ls -la scripts/ logs/`

If `logs/` has any actual files, skip its deletion. If `scripts/` is empty, proceed.

- [ ] **Step 2: Remove from git**

```bash
git rm -r scripts/
# logs/ 是在 .gitignore 里的，如果 git ls-files 里有踪迹再删；否则跳过
git ls-files logs/ | xargs -I{} git rm {} 2>/dev/null || true
rmdir scripts/ logs/ 2>/dev/null || true
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: 删空目录 scripts/ logs/，logs 已在 .gitignore"
```

---

### Task 3.5: Add `legacy/README.md` explaining the archive

**Files:**
- Create: `legacy/README.md`

- [ ] **Step 1: Write explainer**

```markdown
# legacy/

这个目录保存的是项目重构前的原始 `.py` 脚本，**仅作历史参考，不再维护、不会运行**。

实际工作流已经全部迁移到：
- `app.py` — Streamlit 单文件应用
- `src/copy_workflow/` — Python 包 + CLI

| 旧脚本 | 等价替代 |
|---|---|
| `文案生成.py` | `src/copy_workflow/generate.py` |
| `重点摘录转csv.py` | `src/copy_workflow/extract.py` |
| `重点翻译英文.py` | 已合并进 `extract.py`（双语提取） |
| `微信公众号爬虫.py` | `src/copy_workflow/crawlers/wechat.py` |
| `校内新闻网爬虫.py` | `src/copy_workflow/crawlers/sjtu_news.py` |

⚠️ 这些文件里的 API Key 已脱敏。如果你 fork 了仓库，确认本目录不含真实密钥。
```

- [ ] **Step 2: Commit**

```bash
git add legacy/README.md
git commit -m "docs: legacy/ 加 README 说明归档身份"
```

---

### Task 3.6: Curate `src/copy_workflow/__init__.py` public API

**Files:**
- Modify: `src/copy_workflow/__init__.py`

- [ ] **Step 1: Add explicit exports**

```python
"""copy_workflow — 中英社交文案生成工作流的 Python 包。

Streamlit 单文件应用 (`app.py`) 不依赖此包；它有自己的实现以保持单文件可部署。
此包为 CLI 路径 (`copy-workflow ...`) 和需要程序化调用的场景提供。
"""

from .models import Extract, Post  # re-exports
from .config import Config, get_config
from .llm import DeepSeekClient, call_with_validation, parse_json_strict

__version__ = "0.2.0"

__all__ = [
    "Config",
    "DeepSeekClient",
    "Extract",
    "Post",
    "call_with_validation",
    "get_config",
    "parse_json_strict",
    "__version__",
]
```

- [ ] **Step 2: Bump version in pyproject.toml**

`pyproject.toml` line 7:

```toml
version = "0.2.0"
```

- [ ] **Step 3: Run tests**

Run: `pytest -q`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add src/copy_workflow/__init__.py pyproject.toml
git commit -m "chore: 包公开 API 显式 __all__，版本升 0.2.0"
```

---

## Phase 4 — Optional Polish (P2)

### Task 4.1: Add `.streamlit/config.toml` (theme + telemetry)

**Files:**
- Create: `.streamlit/config.toml`

- [ ] **Step 1: Write config**

```toml
[theme]
base = "light"
primaryColor = "#E2231A"
font = "sans serif"

[browser]
gatherUsageStats = false

[server]
maxUploadSize = 10
```

- [ ] **Step 2: Commit**

```bash
git add .streamlit/config.toml
git commit -m "chore: .streamlit/config.toml 锁定主题色，关 telemetry"
```

---

### Task 4.2 (deferred / optional): Mark package vs app.py drift in README

Decision deferred to user. Two options:

**Option A** — accept divergence permanently:

Add a note in README under "项目结构":

```markdown
> **app.py 与 src/copy_workflow/ 关系**：app.py 是自包含的单文件 Streamlit 应用，
> 它有自己的 `LLMConfig` / `llm_chat` / 模型定义。Python 包则是 CLI 路径
> (`copy-workflow ...`) 用的。两者刻意分离，便于 Streamlit Cloud 部署只发一份代码。
> 修改 LLM 调用逻辑时如果想同步两边，需要手动镜像。
```

**Option B** — refactor app.py to import from package:
- 1-2 天工作量
- 改动量约 400 行
- 风险：Streamlit 热重载/缓存行为可能因模块拆分而变
- 收益：消除维护两套代码的负担

**Recommendation: A** for now. Reconsider B if drift bites again.

---

## Self-Review (writing-plans checklist)

**1. Spec coverage:** Mapped each P0/P1/P2 finding above to a Task. P0 → Phase 1, UX P1 → Phase 2, hygiene P1 → Phase 3, P2 → Phase 4. ✅

**2. Placeholder scan:** No "TBD"/"appropriate"/"similar to" — every step has concrete code or commands. ✅

**3. Type consistency:** Models/functions referenced are all existing (Extract, Post, DeepSeekClient, call_with_validation, parse_json_strict, get_config) — verified against `src/copy_workflow/`. ✅

---

## Approval Checklist

Send back any of these to control scope:
- **`all`** — execute every task in order
- **`phase 1`** / **`phase 2`** / **`phase 3`** / **`phase 4`** — only that phase
- **`p0 only`** — only the 4 stale-data fixes (Tasks 1.1-1.4)
- **specific task IDs** — e.g. `1.3, 2.2, 2.5, 3.2`
- **`skip X`** — execute all except X
