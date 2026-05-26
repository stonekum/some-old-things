"""
Streamlit 单文件版「中→英 社交文案生成工作流」

依赖（写到 requirements.txt 即可一键部署）:
    streamlit
    requests
    beautifulsoup4
    pydantic>=2
    pyyaml
    striprtf
    python-dotenv

运行: streamlit run app.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import requests
import streamlit as st
import yaml
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError, field_validator


# ============================================================================
# 1. 常量 / Prompt 模板
# ============================================================================

EXTRACT_PROMPT_SYSTEM = """\
You are a precise information extractor for Chinese news / WeChat articles.
Your job is to read the source text and return one JSON object with the schema below.
You output ONLY a JSON object. No prose, no markdown, no code fences."""

EXTRACT_PROMPT_USER = """\
Read the source article and extract the following fields. If a field is missing, use
the empty value indicated in the schema. Do NOT invent names, dates, or events that
are not in the source.

Output schema (strict):
{
  "title_zh": "string — a concise Chinese headline drawn from the source",
  "title_en": "string — the same headline in idiomatic English",
  "date": "YYYY-MM-DD or null if the source does not state a date",
  "key_sentences_zh": ["3-5 complete Chinese sentences that capture the article's core, 15-30 chars each, declarative"],
  "key_sentences_en": ["the same key points in idiomatic English, one per Chinese item, same order"],
  "audience": "string — e.g. 'overseas high school / college students', 'alumni', 'general public'",
  "style_type": "string — short label e.g. 'campus_life', 'student_profile', 'event_recap', 'announcement'",
  "platforms": ["lowercase platform list, choose from: instagram, twitter, linkedin, facebook, wechat"],
  "emoji_flag": true_or_false,
  "emoji_suggestions": ["3-6 emoji that match the topic, only if emoji_flag is true; otherwise []"]
}

Rules:
1. Strip personal names from titles and key sentences. Use the person's role.
2. emoji_flag is true ONLY when the article mentions a country other than China,
   OR is clearly a lighthearted lifestyle / campus-life piece. Otherwise false.
3. key_sentences must be drawn from the source; no paraphrase that changes meaning.
4. Date format YYYY-MM-DD. Vague time ("spring 2025") → null.
5. Pick a sensible platform subset for this content.

SOURCE:
{source_text}
"""


GEN_PROMPTS: dict[str, tuple[str, str]] = {
    "instagram": (
        "You write Instagram captions for an international university audience in "
        "idiomatic English. Output ONLY JSON: {\"title\":\"...\",\"body\":\"...\"}.",
        """Write one Instagram caption.

Constraints:
- Body: 150-220 words, 2-4 short paragraphs separated by blank lines.
- Open with a vivid hook (image, question, or a number).
- Plain text only. No '**', '#', or '>' markdown.
- End with one call-to-action line.
- Emoji policy: {emoji_directive}
- Date: {date_directive}
- Do NOT invent names, programs, or facts.

Style reference (tone only, do not copy):
{style_seed}

Facts:
- Title (EN): {title_en}
- Date: {date}
- Audience: {audience}
- Key points:
{key_sentences_en}

Return JSON: {{"title":"...","body":"..."}}.""",
    ),
    "twitter": (
        "You write Twitter/X posts. Output ONLY JSON: {\"title\":\"...\",\"body\":\"...\"}.",
        """Write one Twitter post.

Constraints:
- Body: STRICTLY under 270 characters total, including hashtags.
- Single paragraph; end with 2-3 CamelCase hashtags.
- Tone: punchy, factual, one strong verb.
- Emoji policy: {emoji_directive}
- Date: {date_directive}

Facts:
- Title (EN): {title_en}
- Date: {date}
- Audience: {audience}
- Key points:
{key_sentences_en}

JSON: {{"title":"...","body":"..."}}.
"title" is filing only — 3-8 words.""",
    ),
    "linkedin": (
        "You write LinkedIn posts: professional, warm, evidence-driven. No marketing hype. "
        "Output ONLY JSON: {\"title\":\"...\",\"body\":\"...\"}.",
        """Write one LinkedIn post.

Constraints:
- Body: 220-320 words, 3-5 short paragraphs.
- Open with a one-sentence hook naming the concrete subject.
- One specific number from the source must appear in the body.
- Plain text; '- ' bullet lists OK.
- End with one reflective question, then 3-5 hashtags on the last line.
- Emoji policy: {emoji_directive} (LinkedIn norms: minimal emoji even when allowed).
- Date: {date_directive}

Style reference:
{style_seed}

Facts:
- Title (EN): {title_en}
- Date: {date}
- Audience: {audience}
- Key points:
{key_sentences_en}

JSON: {{"title":"...","body":"..."}}.""",
    ),
    "facebook": (
        "You write Facebook posts. Output ONLY JSON: {\"title\":\"...\",\"body\":\"...\"}.",
        """Write one Facebook post.

Constraints:
- Body: 180-260 words, 3-4 paragraphs.
- Narrative voice: small story → takeaway.
- End with one open question.
- Emoji policy: {emoji_directive}
- Date: {date_directive}

Facts:
- Title (EN): {title_en}
- Date: {date}
- Audience: {audience}
- Key points:
{key_sentences_en}

JSON: {{"title":"...","body":"..."}}.""",
    ),
    "wechat": (
        "你为高校微信公众号撰写中文社交文案。语气克制、有故事感。"
        "只输出 JSON：{\"title\":\"...\",\"body\":\"...\"}。",
        """请基于素材写一篇微信公众号短文案。

要求：
- 正文 220-320 字，3-4 自然段，段间空行。
- 首段第一句即点题。
- 文末用一句行动号召收尾。
- Emoji 规则：{emoji_directive}
- 日期：{date_directive}
- 严格忠于素材，不得新增姓名、事实。

风格参考（仅借鉴语感）：
{style_seed}

素材：
- 中文标题：{title_zh}
- 日期：{date}
- 受众：{audience}
- 关键点：
{key_sentences_zh}

JSON：{{"title":"...","body":"..."}}。""",
    ),
}

DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
PROMPT_VERSION = "v1"


# ============================================================================
# 2. Pydantic 数据模型
# ============================================================================

Platform = Literal["instagram", "twitter", "linkedin", "facebook", "wechat"]


class Extract(BaseModel):
    title_zh: str = ""
    title_en: str = ""
    date: str | None = None
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
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        if s in {"true", "yes", "1", "t"}:
            return True
        if s in {"false", "no", "0", "f", "flase"}:
            return False
        return False

    @field_validator("date", mode="before")
    @classmethod
    def _norm_date(cls, v: Any) -> str | None:
        if not v:
            return None
        s = str(v).strip()
        if s.lower() in {"无", "none", "null", "n/a"}:
            return None
        return s

    @field_validator("platforms", mode="before")
    @classmethod
    def _lower_platforms(cls, v: Any) -> Any:
        if v is None:
            return ["instagram"]
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",")]
        out = [p.lower() for p in v if p]
        allowed = {"instagram", "twitter", "linkedin", "facebook", "wechat"}
        return [p for p in out if p in allowed] or ["instagram"]


class Post(BaseModel):
    article_slug: str
    platform: Platform
    variant: int = 1
    title: str
    body: str
    model: str
    prompt_version: str = PROMPT_VERSION
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _PostJSON(BaseModel):
    title: str
    body: str


# ============================================================================
# 3. 简单磁盘缓存（按 sha256(content+model+...) 落盘）
# ============================================================================

CACHE_DIR = ".cache_llm"


def _cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{key}.json")


def _cache_get(key: str) -> dict | None:
    p = _cache_path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def _cache_set(key: str, value: dict) -> None:
    with open(_cache_path(key), "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


# ============================================================================
# 4. DeepSeek 客户端
# ============================================================================

@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


@dataclass
class LLMConfig:
    api_key: str
    api_url: str = DEFAULT_API_URL
    timeout: int = 180
    retries: int = 3
    retry_backoff: int = 8


def llm_chat(
    cfg: LLMConfig,
    *,
    system: str,
    user: str,
    model: str,
    json_mode: bool = False,
    temperature: float = 0.7,
    no_cache: bool = False,
) -> LLMResponse:
    key = _cache_key(system, user, model, str(json_mode), f"{temperature:.2f}")
    if not no_cache:
        hit = _cache_get(key)
        if hit:
            return LLMResponse(
                content=hit["content"],
                prompt_tokens=hit.get("prompt_tokens", 0),
                completion_tokens=hit.get("completion_tokens", 0),
                cached=True,
            )

    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    last_err: Exception | None = None
    for attempt in range(1, cfg.retries + 1):
        try:
            r = requests.post(cfg.api_url, json=body, headers=headers, timeout=cfg.timeout)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
            out = LLMResponse(
                content=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
            _cache_set(
                key,
                {
                    "content": out.content,
                    "prompt_tokens": out.prompt_tokens,
                    "completion_tokens": out.completion_tokens,
                },
            )
            return out
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            time.sleep(cfg.retry_backoff * attempt)
    raise RuntimeError(f"LLM call failed after retries: {last_err}")


def _parse_json_strict(text: str) -> dict:
    s = text.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return json.loads(s)


def llm_call_validated(
    cfg: LLMConfig,
    schema: type[BaseModel],
    *,
    system: str,
    user: str,
    model: str,
    temperature: float = 0.7,
) -> tuple[BaseModel, LLMResponse]:
    resp = llm_chat(cfg, system=system, user=user, model=model, json_mode=True, temperature=temperature)
    try:
        return schema.model_validate(_parse_json_strict(resp.content)), resp
    except (json.JSONDecodeError, ValidationError) as e:
        repair_user = (
            f"{user}\n\n---\nPrevious output was rejected:\n{e}\nReturn corrected JSON only."
        )
        resp2 = llm_chat(
            cfg,
            system=system,
            user=repair_user,
            model=model,
            json_mode=True,
            temperature=0.2,
            no_cache=True,
        )
        return schema.model_validate(_parse_json_strict(resp2.content)), resp2


# ============================================================================
# 5. 工作流：提取 + 生成
# ============================================================================

def extract_article(cfg: LLMConfig, model: str, text: str) -> Extract:
    if not text.strip():
        raise ValueError("empty input text")
    user = EXTRACT_PROMPT_USER.replace("{source_text}", text[:8000])
    ex, _ = llm_call_validated(
        cfg, Extract, system=EXTRACT_PROMPT_SYSTEM, user=user, model=model, temperature=0.2
    )
    return ex


def _emoji_directive(ex: Extract) -> str:
    if ex.emoji_flag and ex.emoji_suggestions:
        return f"use emoji sparingly; options: {', '.join(ex.emoji_suggestions)}"
    if ex.emoji_flag:
        return "use 1-2 tasteful emoji"
    return "no emoji"


def _date_directive(ex: Extract) -> str:
    return f"include the date {ex.date} naturally" if ex.date else "do not reference any date"


def _format_gen_user(template: str, ex: Extract, style_seed: str) -> str:
    return (
        template.replace("{title_zh}", ex.title_zh)
        .replace("{title_en}", ex.title_en)
        .replace("{date}", ex.date or "n/a")
        .replace("{audience}", ex.audience)
        .replace("{key_sentences_zh}", "\n".join(f"  - {s}" for s in ex.key_sentences_zh) or "  - (none)")
        .replace("{key_sentences_en}", "\n".join(f"  - {s}" for s in ex.key_sentences_en) or "  - (none)")
        .replace("{emoji_directive}", _emoji_directive(ex))
        .replace("{date_directive}", _date_directive(ex))
        .replace("{style_seed}", style_seed or "(no style reference)")
    )


def generate_post(
    cfg: LLMConfig,
    model: str,
    ex: Extract,
    platform: Platform,
    *,
    variant: int = 1,
    style_seed: str = "",
    article_slug: str = "article",
    temperature: float = 0.7,
) -> Post:
    sys_prompt, user_tmpl = GEN_PROMPTS[platform]
    user = _format_gen_user(user_tmpl, ex, style_seed)
    payload, resp = llm_call_validated(
        cfg, _PostJSON, system=sys_prompt, user=user, model=model, temperature=temperature
    )
    return Post(
        article_slug=article_slug,
        platform=platform,
        variant=variant,
        title=payload.title,
        body=payload.body,
        model=model,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
    )


# ============================================================================
# 6. 网页抓取：微信公众号 + SJTU 新闻 + 通用
# ============================================================================

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_wechat(url: str) -> tuple[str, str]:
    """returns (title, body_text)"""
    r = requests.get(url, headers={"User-Agent": _UA, "Referer": "https://mp.weixin.qq.com/"}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title_tag = soup.find("h1", class_="rich_media_title")
    title = title_tag.get_text(strip=True) if title_tag else "未命名"
    content_div = soup.find("div", id="js_content")
    if not content_div:
        return title, ""
    chunks = []
    for el in content_div.find_all(["p", "section", "h1", "h2", "h3", "li"]):
        t = el.get_text(strip=True)
        if t:
            chunks.append(t)
    return title, "\n\n".join(chunks) or content_div.get_text("\n", strip=True)


def fetch_sjtu_news(url: str) -> tuple[str, str]:
    r = requests.get(url, headers={"User-Agent": _UA, "Referer": "https://news.sjtu.edu.cn/"}, timeout=30)
    r.encoding = "utf-8"
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title_tag = soup.select_one("#ivs_title")
    content_div = soup.select_one(".Article_content")
    date_tag = soup.select_one("#ivs_date.time")
    title = title_tag.get_text(strip=True) if title_tag else "未知标题"
    body_parts = []
    if date_tag:
        body_parts.append(f"日期：{date_tag.get_text(strip=True)}")
    if content_div:
        for el in content_div.find_all(["p", "h1", "h2", "h3", "li"]):
            t = el.get_text(strip=True)
            if t:
                body_parts.append(t)
    return title, "\n\n".join(body_parts)


def fetch_generic(url: str) -> tuple[str, str]:
    r = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else url)[:120]
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    chunks = []
    for el in soup.find_all(["p", "h1", "h2", "h3", "li"]):
        t = el.get_text(strip=True)
        if t:
            chunks.append(t)
    return title, "\n\n".join(chunks)


FETCHERS: dict[str, callable] = {
    "微信公众号": fetch_wechat,
    "SJTU 新闻": fetch_sjtu_news,
    "通用网页": fetch_generic,
}


# ============================================================================
# 7. 输出渲染：markdown frontmatter + zip
# ============================================================================

def slugify(name: str) -> str:
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    safe = re.sub(r"_+", "_", safe)
    return safe[:60] or "article"


def post_to_markdown(post: Post) -> str:
    fm = {
        "platform": post.platform,
        "variant": post.variant,
        "title": post.title,
        "model": post.model,
        "prompt_version": post.prompt_version,
        "generated_at": post.generated_at.isoformat(timespec="seconds"),
        "prompt_tokens": post.prompt_tokens,
        "completion_tokens": post.completion_tokens,
    }
    return (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + post.body.strip()
        + "\n"
    )


def zip_posts(posts: list[Post]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in posts:
            variant_suffix = "" if p.variant == 1 else f".v{p.variant}"
            path = f"{p.article_slug}/{p.platform}{variant_suffix}.md"
            zf.writestr(path, post_to_markdown(p))
    return buf.getvalue()


# ============================================================================
# 8. Streamlit UI
# ============================================================================

st.set_page_config(page_title="LLM 文案生成工作流", page_icon="✍️", layout="wide")
st.title("✍️ 中→英 社交文案生成工作流")
st.caption("一站式：抓取 / 提取双语关键信息 / 按平台批量生成")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ 配置")
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    api_key = st.text_input(
        "DeepSeek API Key",
        value=env_key,
        type="password",
        help="不会写到磁盘；设置 DEEPSEEK_API_KEY 环境变量可自动填充",
    )
    model = st.selectbox(
        "模型",
        ["deepseek-chat", "deepseek-reasoner"],
        index=0,
        help=(
            "deepseek-chat：速度快、费用低，日常文案生成推荐用这个。\n\n"
            "deepseek-reasoner（R1）：深度推理模型，会先「思考」再输出，"
            "逻辑更严谨，但速度慢 3-5 倍、费用高约 10 倍，适合对质量要求极高时使用。"
        ),
    )
    platforms_chosen = st.multiselect(
        "目标平台",
        ["instagram", "twitter", "linkedin", "facebook", "wechat"],
        default=["instagram", "twitter", "linkedin"],
    )
    variants = st.slider("每个平台生成几条变体", 1, 3, 1)
    max_workers = st.slider("并发数", 1, 8, 4, help="LLM 并发调用数")
    temperature = st.slider("Temperature", 0.0, 1.2, 0.7, 0.1)
    st.divider()
    use_cache = st.checkbox("启用磁盘缓存", value=True, help=f"缓存目录：{CACHE_DIR}/")
    style_seed_text = st.text_area(
        "风格参考（可选，仅借鉴语感）",
        value="",
        placeholder="贴一两条过往优秀文案，模型会模仿语感，但不抄袭内容",
        height=120,
    )

# ---------- Session state ----------
ss = st.session_state
ss.setdefault("articles", [])  # list[{name, text, extract?, posts?}]
ss.setdefault("total_tokens_in", 0)
ss.setdefault("total_tokens_out", 0)
ss.setdefault("cache_hits", 0)

# ---------- 输入区 ----------
tab_input, tab_results, tab_logs = st.tabs(["1️⃣ 输入素材", "2️⃣ 结果", "📊 用量"])

with tab_input:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("方式 A：粘贴文本")
        manual_name = st.text_input("文章名（用作文件夹名）", value="manual_input")
        manual_text = st.text_area("文章正文", height=240)
        if st.button("➕ 加入队列", use_container_width=True):
            if manual_text.strip():
                ss.articles.append(
                    {"name": slugify(manual_name) or "manual", "text": manual_text.strip()}
                )
                st.success(f"已加入：{manual_name}（队列共 {len(ss.articles)} 篇）")
            else:
                st.warning("正文为空")

    with col2:
        st.subheader("方式 B：URL 抓取")
        fetch_kind = st.radio("来源类型", list(FETCHERS.keys()), horizontal=True)
        urls_raw = st.text_area("URL（每行一条）", height=120)
        if st.button("🌐 抓取并加入队列", use_container_width=True):
            urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
            with st.spinner(f"抓取 {len(urls)} 条…"):
                ok, fail = 0, 0
                for u in urls:
                    try:
                        title, body = FETCHERS[fetch_kind](u)
                        if body:
                            ss.articles.append({"name": slugify(title), "text": body, "url": u})
                            ok += 1
                        else:
                            fail += 1
                    except Exception as e:
                        st.error(f"❌ {u}: {e}")
                        fail += 1
                st.success(f"成功 {ok} / 失败 {fail}")

    st.subheader("方式 C：上传 .txt 文件")
    uploads = st.file_uploader(
        "可多选；每个文件为一篇文章", type=["txt", "md"], accept_multiple_files=True
    )
    if uploads and st.button("📤 加入队列", use_container_width=True):
        for f in uploads:
            text = f.read().decode("utf-8", errors="ignore")
            ss.articles.append({"name": slugify(os.path.splitext(f.name)[0]), "text": text})
        st.success(f"已加入 {len(uploads)} 篇")

    st.divider()
    st.subheader(f"📚 当前队列（{len(ss.articles)} 篇）")
    if ss.articles:
        for i, art in enumerate(ss.articles):
            with st.expander(f"{i + 1}. {art['name']}（{len(art['text'])} 字）"):
                st.caption(art.get("url", ""))
                st.text(art["text"][:600] + ("…" if len(art["text"]) > 600 else ""))
                if st.button("🗑 删除", key=f"del_{i}"):
                    ss.articles.pop(i)
                    st.rerun()
        if st.button("🧹 清空队列"):
            ss.articles.clear()
            st.rerun()

    st.divider()
    if st.button(
        "🚀 开始处理（提取 + 生成）",
        type="primary",
        use_container_width=True,
        disabled=not (api_key and ss.articles and platforms_chosen),
    ):
        cfg = LLMConfig(api_key=api_key)
        progress = st.progress(0.0, text="启动…")

        def _work_article(idx_art):
            idx, art = idx_art
            try:
                ex = extract_article(cfg, model, art["text"])
                # 直接使用用户勾选的平台，不与模型推荐做交集（避免模型推荐少于用户选择时丢失平台）
                chosen = platforms_chosen
                posts: list[Post] = []
                for plat in chosen:
                    for v in range(1, variants + 1):
                        t = min(temperature + 0.1 * (v - 1), 1.2)
                        posts.append(
                            generate_post(
                                cfg,
                                model,
                                ex,
                                plat,
                                variant=v,
                                style_seed=style_seed_text,
                                article_slug=art["name"],
                                temperature=t,
                            )
                        )
                return idx, ex, posts, None
            except Exception as e:
                return idx, None, [], e

        results: dict[int, tuple[Extract, list[Post]]] = {}
        errors: dict[int, Exception] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = [
                pool.submit(_work_article, (i, a)) for i, a in enumerate(ss.articles)
            ]
            done = 0
            total = len(futs)
            for f in as_completed(futs):
                idx, ex, posts, err = f.result()
                done += 1
                progress.progress(done / total, text=f"完成 {done}/{total}")
                if err:
                    errors[idx] = err
                else:
                    results[idx] = (ex, posts)

        # 写回 session state
        for idx, (ex, posts) in results.items():
            ss.articles[idx]["extract"] = ex.model_dump(mode="json")
            ss.articles[idx]["posts"] = [p.model_dump(mode="json") for p in posts]
        for idx, e in errors.items():
            st.error(f"第 {idx + 1} 篇失败：{e}")

        # token 统计
        for posts_dump in (ss.articles[i].get("posts", []) for i in results):
            for p in posts_dump:
                ss.total_tokens_in += p["prompt_tokens"]
                ss.total_tokens_out += p["completion_tokens"]
        progress.empty()
        st.success(f"完成 {len(results)} 篇，{sum(len(p) for _, p in results.values())} 条文案")
        st.balloons()


# ---------- 结果区 ----------
with tab_results:
    processed = [a for a in ss.articles if "posts" in a]
    if not processed:
        st.info("还没有结果。请到「输入素材」加入文章并点「开始处理」。")
    else:
        # 顶部下载全部
        all_posts = [Post(**p) for a in processed for p in a["posts"]]
        st.download_button(
            "📦 下载全部 Markdown（zip）",
            data=zip_posts(all_posts),
            file_name=f"posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True,
        )

        for art in processed:
            ex = Extract(**art["extract"])
            posts = [Post(**p) for p in art["posts"]]

            with st.expander(f"📰 {art['name']} —— {ex.title_en}", expanded=True):
                with st.container():
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**中文标题**：{ex.title_zh}")
                        st.markdown(f"**英文标题**：{ex.title_en}")
                        st.markdown(f"**日期**：{ex.date or '—'}")
                        st.markdown(f"**受众**：{ex.audience}")
                    with c2:
                        st.markdown(f"**风格**：{ex.style_type}")
                        st.markdown(f"**推荐平台**：{', '.join(ex.platforms)}")
                        st.markdown(f"**是否带 emoji**：{'是' if ex.emoji_flag else '否'}")
                        if ex.emoji_suggestions:
                            st.markdown(f"**推荐 emoji**：{' '.join(ex.emoji_suggestions)}")
                    st.markdown("**关键句（中）**")
                    for s in ex.key_sentences_zh:
                        st.markdown(f"- {s}")
                    st.markdown("**关键句（英）**")
                    for s in ex.key_sentences_en:
                        st.markdown(f"- {s}")

                st.divider()
                # 按平台展示
                if posts:
                    plat_tabs = st.tabs([p.platform + (f" v{p.variant}" if p.variant > 1 else "") for p in posts])
                    for t, post in zip(plat_tabs, posts):
                        with t:
                            st.markdown(f"### {post.title}")
                            st.text_area(
                                "正文",
                                value=post.body,
                                height=260,
                                key=f"body_{art['name']}_{post.platform}_{post.variant}",
                            )
                            cdl, cmeta = st.columns([1, 3])
                            with cdl:
                                st.download_button(
                                    "⬇️ 下载 .md",
                                    data=post_to_markdown(post),
                                    file_name=f"{art['name']}_{post.platform}.md",
                                    mime="text/markdown",
                                    key=f"dl_{art['name']}_{post.platform}_{post.variant}",
                                )
                            with cmeta:
                                st.caption(
                                    f"模型 {post.model} ｜ in {post.prompt_tokens} / out "
                                    f"{post.completion_tokens} tokens ｜ {post.generated_at.isoformat(timespec='seconds')}"
                                )

# ---------- 用量 ----------
with tab_logs:
    c1, c2, c3 = st.columns(3)
    c1.metric("累计输入 tokens", ss.total_tokens_in)
    c2.metric("累计输出 tokens", ss.total_tokens_out)
    c3.metric("已处理文章数", sum(1 for a in ss.articles if "posts" in a))
    st.caption(
        "提示：磁盘缓存按 sha256(prompt+model+...) 命中；如要强制重新生成，去掉左侧「启用磁盘缓存」并重跑。"
    )
    if st.button("🧨 清空磁盘缓存"):
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        st.success(f"已清空 {CACHE_DIR}/")
