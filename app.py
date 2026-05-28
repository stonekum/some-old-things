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
import ipaddress
import json
import os
import re
import socket
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

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
  "platforms": ["lowercase platform list, choose from: instagram, twitter, linkedin, facebook, wechat, xiaohongshu"],
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
    "xiaohongshu": (
        "你为高校小红书账号撰写中文图文笔记文案。语气亲切、具体、克制，"
        "不夸张、不编造。只输出 JSON：{\"title\":\"...\",\"body\":\"...\"}。",
        """请基于下面的素材，写一篇适合小红书发布的中文笔记文案。

要求：
- 标题 12-24 个中文字符，具体、有画面感，不标题党。
- 正文 180-280 字，3-5 个短段落，段间空行。
- 开头直接给出场景、人物角色或具体细节。
- 语气自然，适合高校国际传播账号；不要使用夸张营销词。
- 可在文末加入 3-5 个相关话题标签。
- Emoji 规则：{emoji_directive}
- 日期：{date_directive}
- 严格忠于素材，不得新增姓名、奖项、机构、未出现的事实。

风格参考（仅借鉴语感与节奏，不可照抄）：
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

QUALITY_REVIEW_SYSTEM = """\
You are a senior bilingual social media editor for a university communications team.
Review the draft against the source facts and platform norms. Output ONLY a JSON
object. No markdown fences, no prose."""

QUALITY_REVIEW_USER = """\
Review this generated post.

Score it from 0 to 100 using these criteria:
- factuality: no invented names, programs, awards, dates, numbers, or claims.
- platform_fit: matches the conventions and reader expectations of {platform}.
- style_fit: professional university voice; warm, concrete, not hype-heavy.
- clarity: clear, idiomatic, easy to understand.
- engagement: hook, rhythm, specificity, and call-to-action fit the platform.
- constraints: respects length, emoji, hashtag, date, and plain-text rules.

Rules:
1. Be strict about factuality. Any invented fact is a high-severity issue.
2. Prefer concise, actionable comments over broad taste judgments.
3. Mark publishable true only if the post can be used with minor or no edits.
4. Set needs_rewrite true when score is below 80, publishable is false, or any high-severity issue exists.

Article facts:
{article_facts}

Style reference:
{style_seed}

Draft:
Title: {title}

Body:
{body}

Return JSON:
{{
  "score": 0,
  "publishable": false,
  "needs_rewrite": true,
  "issues": [
    {{
      "category": "factuality | platform_fit | style_fit | clarity | engagement | constraints | other",
      "severity": "low | medium | high",
      "message": "specific issue",
      "suggestion": "specific edit direction"
    }}
  ],
  "strengths": ["specific strength"]
}}"""

QUALITY_REVISE_SYSTEM = """\
You are a senior bilingual social media editor for a university communications team.
Revise the draft to address the review while staying strictly faithful to the
source facts. Output ONLY a JSON object: {"title": "...", "body": "..."}."""

QUALITY_REVISE_USER = """\
Revise this {platform} post.

Non-negotiable rules:
1. Do not add names, programs, awards, partnerships, numbers, dates, places, or claims absent from the article facts.
2. Preserve the intended platform format and reader expectations.
3. Keep the university voice concrete, warm, and restrained.
4. Address the review comments directly.
5. Plain text only.

Article facts:
{article_facts}

Style reference:
{style_seed}

Review comments:
{quality_review}

Original draft:
Title: {title}

Body:
{body}

Return JSON: {{"title": "...", "body": "..."}}."""

DEFAULT_API_URL  = "https://api.deepseek.com/v1/chat/completions"
SJTU_API_URL     = "https://models.sjtu.edu.cn/api/v1/chat/completions"
PROMPT_VERSION   = "v1"

# 各提供商的可用模型及说明
PROVIDER_MODELS = {
    "DeepSeek 官方": {
        # 只暴露 V4 新命名；旧 alias deepseek-chat / deepseek-reasoner 2026-07-24 退役，不再列。
        # 思维链由 sidebar 的"启用思维链"checkbox 显式控制。
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default": "deepseek-v4-flash",
        "help": {
            "deepseek-v4-flash": "DeepSeek V4 Flash · 284B 总参 / 13B 激活 · 速度快、费用低 ✅ 推荐",
            "deepseek-v4-pro":   "DeepSeek V4 Pro · 1.6T 总参 / 49B 激活 · 复杂推理 / Agent / 代码任务",
        },
    },
    "交大内网 (SJTU)": {
        # 通过 GET /models 实测确认的后端支持列表（2026-05）
        "models": [
            "deepseek-chat",
            "deepseek-v3.2",
            "deepseek-reasoner",
            "minimax",
            "minimax-m2.7",
            "qwen",
            "qwen3.5-27b",
            "glm",
            "glm-5.1",
            "claw",
        ],
        "default": "deepseek-chat",
        "help": {
            "deepseek-chat":     "DeepSeek V3 · 与官方同款，走交大内网 ✅ 文案首选",
            "deepseek-v3.2":     "DeepSeek V3.2 · 明确指定 V3.2 版本",
            "deepseek-reasoner": "DeepSeek R1 · 深度推理思维链，慢但质量高",
            "minimax":           "MiniMax · 中文口语化出色，适合微信/小红书",
            "minimax-m2.7":      "MiniMax M2.7 · 较新版本",
            "qwen":              "通义千问 · 阿里默认版",
            "qwen3.5-27b":       "Qwen3.5 27B · 通义千问明确版本",
            "glm":               "智谱 GLM · 默认版",
            "glm-5.1":           "智谱 GLM 5.1 · 明确版本",
            "claw":              "Claw · SJTU 内部模型",
        },
    },
}


# ============================================================================
# 2. Pydantic 数据模型
# ============================================================================

Platform = Literal["instagram", "twitter", "linkedin", "facebook", "wechat", "xiaohongshu"]

PLATFORM_LABELS = {
    "instagram": "Instagram 图文",
    "twitter": "X / Twitter 短帖",
    "linkedin": "LinkedIn 长帖",
    "facebook": "Facebook 贴文",
    "wechat": "微信公众号",
    "xiaohongshu": "小红书笔记",
}

# 示例文章：供首次使用者快速试跑，免去自备素材的门槛
SAMPLE_ARTICLE = {
    "name": "示例-上海交大开学典礼",
    "text": (
        "9 月 1 日，上海交通大学举行 2026 级新生开学典礼。校长在致辞中强调，"
        "希望同学们坚守'饮水思源、爱国荣校'的精神，在交大度过的四年既要"
        "夯实专业基础，也要保持对世界的好奇与开放。当天有来自全球 60 多个国家"
        "的国际新生加入交大大家庭。典礼以全体新生齐唱校歌结束，标志着他们"
        "正式开启大学生涯。"
    ),
}


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
        aliases = {"rednote": "xiaohongshu", "小红书": "xiaohongshu"}
        out = [aliases.get(p, p) for p in out]
        allowed = {"instagram", "twitter", "linkedin", "facebook", "wechat", "xiaohongshu"}
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
    # 后端实际服务的模型名 (deepseek-chat alias 可能跑 deepseek-v4-flash)
    served_model: str = ""
    # 实际调用时使用的 API endpoint（用于审计：到底打了哪个提供商）
    api_url: str = ""
    # 本次结果是否来自缓存（True = 没真的调 API）
    from_cache: bool = False
    # deepseek-reasoner 等推理模型返回的思维链；非推理模型为空
    reasoning_content: str = ""
    quality_score: int | None = None
    quality_publishable: bool | None = None
    quality_needs_rewrite: bool | None = None
    quality_issues: list[dict[str, Any]] = Field(default_factory=list)


class _PostJSON(BaseModel):
    title: str
    body: str


class QualityIssue(BaseModel):
    category: Literal[
        "factuality",
        "platform_fit",
        "style_fit",
        "clarity",
        "engagement",
        "constraints",
        "other",
    ]
    severity: Literal["low", "medium", "high"]
    message: str
    suggestion: str = ""


class QualityReview(BaseModel):
    score: int = Field(ge=0, le=100)
    publishable: bool
    needs_rewrite: bool | None = None
    issues: list[QualityIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: Any) -> int:
        try:
            score = int(v)
        except (TypeError, ValueError):
            score = 0
        return max(0, min(score, 100))


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
    # API 实际服务的模型名 (例如选 deepseek-chat 可能实际跑 deepseek-v4-flash)
    served_model: str = ""
    # deepseek-reasoner 等推理模型会在响应里返回思维链
    reasoning_content: str = ""


@dataclass
class LLMConfig:
    api_key: str
    api_url: str = DEFAULT_API_URL
    # 60s 单次 / 重试 2 次 / backoff 4s × attempt —— 总上限 ~2 分钟
    # 之前 180×3+8×n 走完要 10 分钟，前端只看到一直转圈，看着像"卡死"。
    timeout: int = 60
    retries: int = 2
    retry_backoff: int = 4
    # 思维链开关：None 表示按 alias 默认行为（legacy chat/reasoner 用这条路径）
    # True/False 表示显式开/关（新 v4-flash/pro 用这条路径）
    thinking: bool | None = None


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
    # cache key 必须包含 api_url + thinking 状态。
    # - api_url：跨提供商隔离（DeepSeek 官方 vs SJTU 内网）
    # - thinking：同一模型开/关思维链产出不同，必须分桶
    # v4 = 加入 thinking 维度
    key = _cache_key(
        cfg.api_url, system, user, model,
        str(json_mode), f"{temperature:.2f}",
        f"thinking={cfg.thinking}",
        "v4",
    )
    if not no_cache:
        hit = _cache_get(key)
        if hit:
            return LLMResponse(
                content=hit["content"],
                prompt_tokens=hit.get("prompt_tokens", 0),
                completion_tokens=hit.get("completion_tokens", 0),
                cached=True,
                served_model=hit.get("served_model", ""),
                reasoning_content=hit.get("reasoning_content", ""),
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
    # 思维链开关：cfg.thinking 显式为 True/False 时下发，None 让服务端按 alias 默认决定
    # 参考: https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
    if cfg.thinking is not None:
        body["thinking"] = {"type": "enabled" if cfg.thinking else "disabled"}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }

    last_err: Exception | None = None
    json_mode_disabled = False  # 记录是否因为后端不支持 response_format 而降级过
    host = urlparse(cfg.api_url).netloc
    for attempt in range(1, cfg.retries + 1):
        try:
            t0 = time.time()
            print(f"[llm_chat] → {host} model={model} json_mode={'response_format' in body} attempt={attempt}", flush=True)
            r = requests.post(cfg.api_url, json=body, headers=headers, timeout=cfg.timeout)
            print(f"[llm_chat] ← {host} status={r.status_code} elapsed={time.time()-t0:.1f}s", flush=True)
            # 4xx 自动降级：很多代理后端（SJTU/Azure/自建网关）不支持 OpenAI 私有的
            # response_format={"type":"json_object"}，会直接 400。检测到时去掉该字段重试一次，
            # 模型仍会按 prompt 里 "Return JSON only" 的指令吐 JSON，下游 _parse_json_strict 会处理 fence。
            if r.status_code == 400 and "response_format" in body and not json_mode_disabled:
                body.pop("response_format", None)
                json_mode_disabled = True
                continue
            # 4xx/5xx 时把服务端返回的 body 带进异常 —— 默认 raise_for_status() 只丢状态码，
            # 看不到 "unknown model xxx" 之类的真实原因，调 SJTU 这种自定义后端时尤其难排错。
            if r.status_code >= 400:
                body_preview = (r.text or "")[:500].replace("\n", " ")
                raise requests.HTTPError(
                    f"{r.status_code} {r.reason} for {cfg.api_url} · body: {body_preview}",
                    response=r,
                )
            data = r.json()
            msg = data["choices"][0]["message"]
            content = msg["content"]
            # DeepSeek reasoner 系列会返回思维链
            reasoning = msg.get("reasoning_content", "") or ""
            # API 响应里的 model 字段告诉你后端真实跑的是哪个模型
            # (e.g. deepseek-chat alias → deepseek-v4-flash)
            served_model = data.get("model", model) or model
            usage = data.get("usage", {}) or {}
            out = LLMResponse(
                content=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                served_model=served_model,
                reasoning_content=reasoning,
            )
            _cache_set(
                key,
                {
                    "content": out.content,
                    "prompt_tokens": out.prompt_tokens,
                    "completion_tokens": out.completion_tokens,
                    "served_model": out.served_model,
                    "reasoning_content": out.reasoning_content,
                },
            )
            return out
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            print(f"[llm_chat] ✗ {host} attempt={attempt} err={type(e).__name__}: {str(e)[:200]}", flush=True)
            time.sleep(cfg.retry_backoff * attempt)
    raise RuntimeError(f"LLM call failed after {cfg.retries} retries · last_err: {last_err}")


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
    no_cache: bool = False,
) -> tuple[BaseModel, LLMResponse]:
    resp = llm_chat(
        cfg,
        system=system,
        user=user,
        model=model,
        json_mode=True,
        temperature=temperature,
        no_cache=no_cache,
    )
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

def extract_article(cfg: LLMConfig, model: str, text: str, *, no_cache: bool = False) -> Extract:
    if not text.strip():
        raise ValueError("empty input text")
    user = EXTRACT_PROMPT_USER.replace("{source_text}", text[:8000])
    ex, _ = llm_call_validated(
        cfg,
        Extract,
        system=EXTRACT_PROMPT_SYSTEM,
        user=user,
        model=model,
        temperature=0.2,
        no_cache=no_cache,
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
    no_cache: bool = False,
) -> Post:
    sys_prompt, user_tmpl = GEN_PROMPTS[platform]
    user = _format_gen_user(user_tmpl, ex, style_seed)
    payload, resp = llm_call_validated(
        cfg,
        _PostJSON,
        system=sys_prompt,
        user=user,
        model=model,
        temperature=temperature,
        no_cache=no_cache,
    )
    return Post(
        article_slug=article_slug,
        platform=platform,
        variant=variant,
        title=payload.title,
        body=payload.body,
        model=model,
        served_model=resp.served_model,
        api_url=cfg.api_url,
        from_cache=resp.cached,
        reasoning_content=resp.reasoning_content,
        prompt_tokens=resp.prompt_tokens,
        completion_tokens=resp.completion_tokens,
    )


def _quality_facts(ex: Extract) -> str:
    key_zh = "\n".join(f"  - {s}" for s in ex.key_sentences_zh) or "  - (none)"
    key_en = "\n".join(f"  - {s}" for s in ex.key_sentences_en) or "  - (none)"
    return (
        f"- Title (ZH): {ex.title_zh}\n"
        f"- Title (EN): {ex.title_en}\n"
        f"- Date: {ex.date or 'n/a'}\n"
        f"- Audience: {ex.audience}\n"
        f"- Style type: {ex.style_type}\n"
        f"- Emoji allowed: {ex.emoji_flag}\n"
        f"- Emoji suggestions: {', '.join(ex.emoji_suggestions) or 'none'}\n"
        f"- Key points (ZH):\n{key_zh}\n"
        f"- Key points (EN):\n{key_en}"
    )


def _quality_review_text(review: QualityReview) -> str:
    if not review.issues:
        return "No issues."
    return "\n".join(
        f"- [{i.severity}] {i.category}: {i.message}"
        + (f" Suggestion: {i.suggestion}" if i.suggestion else "")
        for i in review.issues
    )


def _post_with_quality(post: Post, review: QualityReview) -> Post:
    post.quality_score = review.score
    post.quality_publishable = review.publishable
    post.quality_needs_rewrite = bool(review.needs_rewrite)
    post.quality_issues = [i.model_dump(mode="json") for i in review.issues]
    return post


def review_post(
    cfg: LLMConfig,
    model: str,
    ex: Extract,
    post: Post,
    *,
    style_seed: str = "",
    no_cache: bool = False,
) -> QualityReview:
    user = (
        QUALITY_REVIEW_USER.replace("{platform}", post.platform)
        .replace("{title}", post.title)
        .replace("{body}", post.body)
        .replace("{article_facts}", _quality_facts(ex))
        .replace("{style_seed}", style_seed or "(no style reference)")
    )
    review, resp = llm_call_validated(
        cfg,
        QualityReview,
        system=QUALITY_REVIEW_SYSTEM,
        user=user,
        model=model,
        temperature=0.2,
        no_cache=no_cache,
    )
    # 累计 review 调用的 token 到 post（之前漏算了）
    post.prompt_tokens += resp.prompt_tokens
    post.completion_tokens += resp.completion_tokens

    has_high_issue = any(i.severity == "high" for i in review.issues)
    if review.needs_rewrite is None or (has_high_issue and not review.needs_rewrite):
        review.needs_rewrite = (not review.publishable) or review.score < 80 or has_high_issue
    return review


def revise_post(
    cfg: LLMConfig,
    model: str,
    ex: Extract,
    post: Post,
    review: QualityReview,
    *,
    style_seed: str = "",
    no_cache: bool = False,
) -> Post:
    user = (
        QUALITY_REVISE_USER.replace("{platform}", post.platform)
        .replace("{title}", post.title)
        .replace("{body}", post.body)
        .replace("{article_facts}", _quality_facts(ex))
        .replace("{style_seed}", style_seed or "(no style reference)")
        .replace("{quality_review}", _quality_review_text(review))
    )
    payload, resp = llm_call_validated(
        cfg,
        _PostJSON,
        system=QUALITY_REVISE_SYSTEM,
        user=user,
        model=model,
        temperature=0.5,
        no_cache=no_cache,
    )
    post.title = payload.title
    post.body = payload.body
    post.prompt_tokens += resp.prompt_tokens
    post.completion_tokens += resp.completion_tokens
    return _post_with_quality(post, review)


def review_and_maybe_revise(
    cfg: LLMConfig,
    model: str,
    ex: Extract,
    post: Post,
    *,
    style_seed: str = "",
    min_score: int = 80,
    no_cache: bool = False,
) -> tuple[Post, QualityReview | None]:
    """Quality 步骤失败时优雅回退到未审稿的 post，不让单条审稿挂掉整篇文章。"""
    try:
        review = review_post(cfg, model, ex, post, style_seed=style_seed, no_cache=no_cache)
    except Exception as e:
        # 通过 session state 收集错误，主循环统一展示
        st.session_state.setdefault("_quality_errors", []).append(
            f"{post.article_slug}/{post.platform} v{post.variant} · review 失败：{e}"
        )
        return post, None

    should_revise = bool(review.needs_rewrite) or review.score < min_score or not review.publishable
    if should_revise:
        try:
            return revise_post(
                cfg,
                model,
                ex,
                post,
                review,
                style_seed=style_seed,
                no_cache=no_cache,
            ), review
        except Exception as e:
            st.session_state.setdefault("_quality_errors", []).append(
                f"{post.article_slug}/{post.platform} v{post.variant} · revise 失败：{e}"
            )
            return _post_with_quality(post, review), review
    return _post_with_quality(post, review), review


# ============================================================================
# 6. 网页抓取：微信公众号 + SJTU 新闻 + 通用（含 SSRF 防护）
# ============================================================================

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_MAX_REDIRECTS = 3
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5MB 防止超大响应 OOM


def _assert_safe_url(url: str) -> None:
    """阻止 SSRF：拒绝非 http(s) 协议、内网/回环/链路本地/保留地址。"""
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"URL 解析失败：{e}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"仅支持 http/https 协议，不支持 {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"无法解析主机 {host!r}：{e}")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"禁止访问内网/保留地址 {addr}（来源主机 {host}）")


def _safe_get(url: str, *, headers: dict | None = None, timeout: int = 30) -> requests.Response:
    """带 SSRF 防护 + redirect 上限 + 响应体大小限制的 GET。"""
    _assert_safe_url(url)
    session = requests.Session()
    session.max_redirects = _MAX_REDIRECTS
    headers = {"User-Agent": _UA, **(headers or {})}
    r = session.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
    # 跟跳后必须重新验证最终落点
    if r.url != url:
        _assert_safe_url(r.url)
    r.raise_for_status()

    # 流式读取，超过上限截断
    content = b""
    for chunk in r.iter_content(chunk_size=64 * 1024):
        content += chunk
        if len(content) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"响应体超过 {_MAX_RESPONSE_BYTES // 1024 // 1024}MB 上限")
    r._content = content  # type: ignore[attr-defined]  # 把流读完的内容塞回 response
    return r


def fetch_wechat(url: str) -> tuple[str, str]:
    """returns (title, body_text)"""
    r = _safe_get(url, headers={"Referer": "https://mp.weixin.qq.com/"})
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
    r = _safe_get(url, headers={"Referer": "https://news.sjtu.edu.cn/"})
    r.encoding = "utf-8"
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
    r = _safe_get(url)
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
        "model_requested": post.model,
        "model_served": post.served_model or post.model,
        "prompt_version": post.prompt_version,
        "generated_at": post.generated_at.isoformat(timespec="seconds"),
        "prompt_tokens": post.prompt_tokens,
        "completion_tokens": post.completion_tokens,
    }
    if post.quality_score is not None:
        fm.update(
            {
                "quality_score": post.quality_score,
                "quality_publishable": post.quality_publishable,
                "quality_needs_rewrite": post.quality_needs_rewrite,
                "quality_issues": post.quality_issues,
            }
        )
    return (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + post.body.strip()
        + "\n"
    )


def _post_body_key(article_name: str, post: Post) -> str:
    return f"body_{article_name}_{post.platform}_{post.variant}"


def _post_with_body(post: Post, body: str) -> Post:
    return post.model_copy(update={"body": body})


def _posts_from_article_state(article: dict[str, Any], state: Any) -> list[Post]:
    posts: list[Post] = []
    for raw in article.get("posts", []):
        post = Post(**raw)
        edited_body = state.get(_post_body_key(article["name"], post), post.body)
        posts.append(_post_with_body(post, edited_body))
    return posts


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


def _get_secret(name: str, default: str = "") -> str:
    """优先从 Streamlit Secrets 读，回落到环境变量。两者都没设返回 default。"""
    try:
        # st.secrets 在没配 secrets.toml 时访问会抛 FileNotFoundError
        if name in st.secrets:
            return str(st.secrets[name])
    except (FileNotFoundError, KeyError, Exception):
        pass
    return os.environ.get(name, default)


def _check_app_password() -> bool:
    """访问密码门禁。未设 APP_PASSWORD 时直接放行（本地开发友好）。"""
    expected = _get_secret("APP_PASSWORD")
    if not expected:
        return True  # 没配密码 → 完全开放
    if st.session_state.get("_authed"):
        return True
    st.title("🔒 访问受限")
    st.caption("此应用受密码保护，请输入访问密码。")
    pw = st.text_input("访问密码", type="password", key="_pw_input")
    if pw:
        if pw == expected:
            st.session_state._authed = True
            st.rerun()
        else:
            st.error("密码错误")
    return False


if not _check_app_password():
    st.stop()


st.title("✍️ 中→英 社交文案生成工作流")
st.caption("一站式：抓取 / 提取双语关键信息 / 按平台批量生成")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ 配置")
    st.subheader("基础设置")

    # ── 提供商选择 ──
    provider = st.radio(
        "API 提供商",
        list(PROVIDER_MODELS.keys()),
        index=0,
        help=(
            "**DeepSeek 官方**：直连 api.deepseek.com，按 token 计费。\n\n"
            "**交大内网 (SJTU)**：走 models.sjtu.edu.cn，"
            "交大账号免费额度大，**校外需开 VPN**。\n"
            "在 my.sjtu.edu.cn → APP → API 处领取 Key。"
        ),
    )
    prov_cfg = PROVIDER_MODELS[provider]

    if provider == "DeepSeek 官方":
        env_name, key_label = "DEEPSEEK_API_KEY", "DeepSeek API Key"
        api_url = DEFAULT_API_URL
    else:
        env_name, key_label = "SJTU_API_KEY", "交大 API Key"
        api_url = SJTU_API_URL

    server_key = _get_secret(env_name)
    if server_key:
        # 服务端已配置 → 完全隐藏输入框，访客拿不到也改不了
        api_key = server_key
        st.success(f"✅ {key_label} 已由服务端配置加载")
    else:
        api_key = st.text_input(key_label, type="password")

    # ── 模型选择 ──
    model_list = prov_cfg["models"]
    model_help = "\n\n".join(f"**{k}**：{v}" for k, v in prov_cfg["help"].items())
    # 用 key 让 Streamlit 在 provider 切换时正确重置（避免选了 SJTU 独有模型后切回官方报错）
    model = st.selectbox(
        "模型",
        model_list,
        index=model_list.index(prov_cfg["default"]),
        key=f"model_select_{provider}",
        help=model_help,
    )

    # ── 思维链开关 ──
    # 新 V4 模型（deepseek-v4-flash / pro）需要显式控制思维链
    # 旧 alias（deepseek-chat / deepseek-reasoner）由 alias 自身决定，UI 不显示开关
    is_legacy_alias = model in {"deepseek-chat", "deepseek-reasoner"}
    if is_legacy_alias:
        thinking_setting: bool | None = None
        if model == "deepseek-reasoner":
            st.caption("🧠 思维链由旧 alias 隐含开启")
        else:
            st.caption("💬 旧 alias 不带思维链")
    else:
        # V4-flash 默认关；V4-pro 也默认关让用户主动开
        thinking_setting = st.checkbox(
            "🧠 启用思维链 (thinking mode)",
            value=False,
            help="开启后模型先输出推理过程再给答案，质量更高但慢 3-5 倍、token 多 2-5 倍",
            key=f"thinking_toggle_{provider}_{model}",
        )

    # ── 诊断工具：列出后端模型 + 测试连接，平时收起避免噪音 ──
    with st.expander("🔧 诊断工具", expanded=False):
        if st.button("📋 列出该后端支持的模型", use_container_width=True, disabled=not api_key):
            # OpenAI 兼容协议：POST /chat/completions 对应 GET /models
            models_url = api_url.rsplit("/chat/completions", 1)[0] + "/models"
            try:
                mr = requests.get(
                    models_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                if mr.status_code >= 400:
                    st.error(f"❌ `{models_url}` 返回 {mr.status_code}\n\n{mr.text[:500]}")
                else:
                    payload = mr.json()
                    ids = [m.get("id") for m in payload.get("data", []) if m.get("id")]
                    if ids:
                        st.success(f"✅ 后端支持 {len(ids)} 个模型：")
                        st.code("\n".join(ids), language="text")
                        st.caption(
                            "把上面任一 model ID 粘到代码里 `PROVIDER_MODELS` 对应 provider 的 `models` 列表里即可。"
                        )
                    else:
                        st.warning(f"返回里没找到 model 列表：{payload}")
            except Exception as e:
                st.error(f"❌ 拉取模型列表失败：`{type(e).__name__}: {e}`")

        # ── 连接测试：发一个最小请求，绕开缓存，直接验证 API 是不是真的能通 ──
        if st.button("🔌 测试 API 连接（绕过缓存）", use_container_width=True, disabled=not api_key):
            with st.spinner(f"正在 ping {urlparse(api_url).netloc} ..."):
                try:
                    test_resp = llm_chat(
                        LLMConfig(api_key=api_key, api_url=api_url, timeout=15, retries=1, thinking=thinking_setting),
                        system="ping",
                        user="reply with the single word: pong",
                        model=model,
                        temperature=0.0,
                        no_cache=True,  # 关键：绕过缓存
                    )
                    # 通过响应里有没有 reasoning_content 判断思维链是否激活
                    thinking_active = bool(test_resp.reasoning_content)
                    expect_thinking = (
                        thinking_setting if thinking_setting is not None
                        else model == "deepseek-reasoner"
                    )
                    if expect_thinking and thinking_active:
                        mode_line = "🧠 思维链 ✅ 已激活"
                    elif expect_thinking and not thinking_active:
                        mode_line = "⚠️ 期望思维链但 reasoning_content 为空（可能后端不支持/未生效）"
                    elif not expect_thinking and thinking_active:
                        mode_line = "ℹ️ 后端意外开启了思维链"
                    else:
                        mode_line = "💬 非思维链模式"
                    st.success(
                        f"✅ 连接成功 · `{urlparse(api_url).netloc}`\n\n"
                        f"{mode_line}\n\n"
                        f"返回：{test_resp.content[:80]}"
                    )
                except Exception as e:
                    st.error(
                        f"❌ 连接失败 · `{urlparse(api_url).netloc}`\n\n"
                        f"错误：`{type(e).__name__}: {e}`\n\n"
                        f"**SJTU 失败**：确认连接了交大 VPN。\n\n"
                        f"**DeepSeek 失败**：检查 Key 是否在 platform.deepseek.com 仍有效。"
                    )

    st.divider()
    platforms_chosen = st.multiselect(
        "目标平台",
        ["instagram", "twitter", "linkedin", "facebook", "wechat", "xiaohongshu"],
        # 默认勾选除微信公众号、小红书以外的全部（这两个用户场景独立性较强，按需开启）
        default=["instagram", "twitter", "linkedin", "facebook"],
        format_func=lambda p: PLATFORM_LABELS.get(p, p),
        help="可多选；不同平台会使用不同长度、语气和格式规则。",
    )
    variants = st.slider("每个平台生成几条变体", 1, 3, 1)
    max_workers = st.slider("并发数", 1, 8, 4, help="LLM 并发调用数（仅 DeepSeek 官方有效；SJTU 强制单线程）")
    temperature = st.slider(
        "创意度 (Temperature)",
        0.0, 1.2, 0.7, 0.1,
        help="越高越发散有创意，越低越保守循规。\n\n0.7 适合大多数文案；0.3 适合事实型；1.0+ 适合广告 / 口号",
    )
    st.divider()
    enable_quality = st.checkbox(
        "发布前自动审稿",
        value=True,
        help=(
            "生成完文案后，让模型扮演主编再审一遍：评分 0-100，找出问题（事实性、平台契合度、"
            "风格、清晰度、互动性、约束），低于 80 分自动重写一次。\n\n"
            "**成本影响**：每条文案多 1-2 次 API 调用（取决于是否需要重写），token ≈ 翻倍。\n"
            "**质量影响**：明显减少空话套话，提高事实准确性。"
        ),
    )
    min_quality_score = st.slider(
        "质量门槛",
        50, 95, 80, 5,
        help=(
            "审稿评分 0-100 低于该值则自动重写一遍。\n\n"
            "**典型分布**：80 是合格线 · 90+ 优秀 · 95+ 罕见。\n\n"
            "设 50 = 只重写明显差的；设 95 = 几乎都会重写"
        ),
        disabled=not enable_quality,
    )
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

estimated_posts = len(ss.articles) * len(platforms_chosen) * variants
ready_checks = {
    "API Key": bool(api_key),
    "素材队列": bool(ss.articles),
    "目标平台": bool(platforms_chosen),
}

status_cols = st.columns([1, 1, 1, 1])
status_cols[0].metric("队列文章", len(ss.articles))
status_cols[1].metric("目标平台", len(platforms_chosen))
status_cols[2].metric("预计文案", estimated_posts)
status_cols[3].metric("审稿", "开启" if enable_quality else "关闭")

missing = [name for name, ok in ready_checks.items() if not ok]
if missing:
    st.warning("开始前还需要：" + "、".join(missing))
else:
    quality_note = "；审稿开启时每条文案会额外调用 1-2 次模型" if enable_quality else ""
    st.info(f"已准备好生成 {estimated_posts} 条文案{quality_note}。")

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
        if st.button("📝 加载示例文章", use_container_width=True, help="无需自备素材即可试跑"):
            ss.articles.append({
                "name": slugify(SAMPLE_ARTICLE["name"]),
                "text": SAMPLE_ARTICLE["text"],
            })
            st.success(f"已加入示例（队列共 {len(ss.articles)} 篇）")
            st.rerun()

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
        f"🚀 开始生成 {estimated_posts or ''} 条文案",
        type="primary",
        use_container_width=True,
        disabled=not (api_key and ss.articles and platforms_chosen),
    ):
        cfg = LLMConfig(api_key=api_key, api_url=api_url, thinking=thinking_setting)
        # SJTU/自建网关常有慢响应，开 4 个并发反而更糟 —— 走 deepseek.com 以外的全部强制单线程
        use_concurrent = "deepseek.com" in api_url and max_workers > 1
        # 估算总步骤数 = 篇数 × (1 extract + 平台数 × 变体数 × (1 generate + 质量审核 0~2 次))
        steps_per_article = 1 + len(platforms_chosen) * variants * (3 if enable_quality else 1)
        total_steps = len(ss.articles) * steps_per_article
        progress = st.progress(0.0, text="准备…")
        log_area = st.empty()

        results: dict[int, tuple[Extract, list[Post]]] = {}
        errors: dict[int, Exception] = {}

        # 单线程路径：每个步骤前后都能更新前端，看得到当前在做什么
        def _run_single_threaded():
            step = 0
            for idx, art in enumerate(ss.articles):
                try:
                    log_area.info(f"📝 第 {idx+1}/{len(ss.articles)} 篇 · extract...")
                    ex = extract_article(cfg, model, art["text"], no_cache=not use_cache)
                    step += 1
                    progress.progress(step / total_steps, text=f"{step}/{total_steps} · 第 {idx+1} 篇 extract 完成")

                    posts: list[Post] = []
                    for plat in platforms_chosen:
                        for v in range(1, variants + 1):
                            t = min(temperature + 0.1 * (v - 1), 1.2)
                            log_area.info(f"✍️ 第 {idx+1}/{len(ss.articles)} 篇 · {plat} v{v} · generate...")
                            post = generate_post(
                                cfg, model, ex, plat,
                                variant=v, style_seed=style_seed_text,
                                article_slug=art["name"], temperature=t,
                                no_cache=not use_cache,
                            )
                            step += 1
                            progress.progress(step / total_steps, text=f"{step}/{total_steps}")
                            if enable_quality:
                                log_area.info(f"🔍 第 {idx+1}/{len(ss.articles)} 篇 · {plat} v{v} · quality review...")
                                post, _ = review_and_maybe_revise(
                                    cfg, model, ex, post,
                                    style_seed=style_seed_text,
                                    min_score=min_quality_score,
                                    no_cache=not use_cache,
                                )
                                step += 2  # review + maybe revise
                                progress.progress(min(step / total_steps, 1.0), text=f"{step}/{total_steps}")
                            posts.append(post)
                    results[idx] = (ex, posts)
                except Exception as e:
                    errors[idx] = e

        def _work_article_threaded(idx_art):
            idx, art = idx_art
            try:
                ex = extract_article(cfg, model, art["text"], no_cache=not use_cache)
                posts: list[Post] = []
                for plat in platforms_chosen:
                    for v in range(1, variants + 1):
                        t = min(temperature + 0.1 * (v - 1), 1.2)
                        post = generate_post(
                            cfg, model, ex, plat,
                            variant=v, style_seed=style_seed_text,
                            article_slug=art["name"], temperature=t,
                            no_cache=not use_cache,
                        )
                        if enable_quality:
                            post, _ = review_and_maybe_revise(
                                cfg, model, ex, post,
                                style_seed=style_seed_text,
                                min_score=min_quality_score,
                                no_cache=not use_cache,
                            )
                        posts.append(post)
                return idx, ex, posts, None
            except Exception as e:
                return idx, None, [], e

        try:
            if use_concurrent:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futs = [pool.submit(_work_article_threaded, (i, a)) for i, a in enumerate(ss.articles)]
                    done = 0
                    for f in as_completed(futs):
                        idx, ex, posts, err = f.result()
                        done += 1
                        progress.progress(done / len(futs), text=f"完成 {done}/{len(futs)}")
                        if err:
                            errors[idx] = err
                        else:
                            results[idx] = (ex, posts)
            else:
                _run_single_threaded()
        except Exception as fatal:
            progress.empty()
            st.exception(fatal)
            st.stop()

        # 写回 session state
        for idx, (ex, posts) in results.items():
            ss.articles[idx]["extract"] = ex.model_dump(mode="json")
            ss.articles[idx]["posts"] = [p.model_dump(mode="json") for p in posts]
        # 先把进度条清掉再显示错误 —— 否则 spinner/progress 会盖住 st.error，让人以为"没反应"
        progress.empty()
        if errors:
            st.error(f"❌ {len(errors)} 篇生成失败（其余 {len(results)} 篇已完成）")
            for idx, e in errors.items():
                with st.expander(f"第 {idx + 1} 篇失败 · {type(e).__name__}", expanded=True):
                    st.code(str(e), language="text")

        # token 统计
        for posts_dump in (ss.articles[i].get("posts", []) for i in results):
            for p in posts_dump:
                ss.total_tokens_in += p["prompt_tokens"]
                ss.total_tokens_out += p["completion_tokens"]
        st.success(f"完成 {len(results)} 篇，{sum(len(p) for _, p in results.values())} 条文案")

        # 展示质量审稿过程中收集的错误（上一版只 print 到 stderr，用户看不到）
        q_errs = st.session_state.pop("_quality_errors", [])
        if q_errs:
            with st.expander(f"⚠️ 质量审稿有 {len(q_errs)} 条警告（不影响正文产出）", expanded=False):
                for line in q_errs:
                    st.text(line)

        st.balloons()


# ---------- 结果区 ----------
with tab_results:
    processed = [a for a in ss.articles if "posts" in a]
    if not processed:
        st.info("还没有结果。请到「输入素材」加入文章并点「开始处理」。")
    else:
        # 顶部下载全部
        all_posts = [p for a in processed for p in _posts_from_article_state(a, st.session_state)]
        st.download_button(
            "📦 下载全部 Markdown（zip）",
            data=zip_posts(all_posts),
            file_name=f"posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True,
        )

        for art in processed:
            ex = Extract(**art["extract"])
            posts = _posts_from_article_state(art, st.session_state)

            with st.expander(f"📰 {art['name']} —— {ex.title_en}", expanded=True):
                # 按平台展示
                if posts:
                    plat_tabs = st.tabs([p.platform + (f" v{p.variant}" if p.variant > 1 else "") for p in posts])
                    for t, post in zip(plat_tabs, posts):
                        with t:
                            st.markdown(f"### {post.title}")
                            body_key = _post_body_key(art["name"], post)
                            edited_body = st.text_area(
                                "正文",
                                value=post.body,
                                height=260,
                                key=body_key,
                            )
                            edited_post = _post_with_body(post, edited_body)
                            cdl, cmeta = st.columns([1, 3])
                            with cdl:
                                st.download_button(
                                    "⬇️ 下载 .md",
                                    data=post_to_markdown(edited_post),
                                    file_name=f"{art['name']}_{post.platform}.md",
                                    mime="text/markdown",
                                    key=f"dl_{art['name']}_{post.platform}_{post.variant}",
                                )
                            with cmeta:
                                quality_bits = ""
                                if post.quality_score is not None:
                                    status = "可发布" if post.quality_publishable else "需编辑"
                                    quality_bits = f" ｜ quality {post.quality_score}/100 · {status}"
                                # 显示模型路由：alias → 实际服务模型
                                if post.served_model and post.served_model != post.model:
                                    model_bits = f"{post.model} → 实际 `{post.served_model}`"
                                else:
                                    model_bits = post.model

                                # 缓存来源 + 实际打到哪个 endpoint（揭穿"切了提供商但其实没切"）
                                cache_bits = "📦 缓存" if post.from_cache else "🌐 新调用"
                                api_host = ""
                                if post.api_url:
                                    try:
                                        api_host = urlparse(post.api_url).netloc or post.api_url
                                    except Exception:
                                        api_host = post.api_url

                                st.caption(
                                    f"模型 {model_bits} ｜ {cache_bits} `{api_host}` ｜ "
                                    f"in {post.prompt_tokens} / out "
                                    f"{post.completion_tokens} tokens{quality_bits} ｜ "
                                    f"{post.generated_at.isoformat(timespec='seconds')}"
                                )
                                if post.quality_issues:
                                    with st.expander("质量反馈"):
                                        for issue in post.quality_issues:
                                            st.markdown(
                                                f"- **{issue.get('severity', 'medium')} / "
                                                f"{issue.get('category', 'other')}**: "
                                                f"{issue.get('message', '')}"
                                            )
                                            if issue.get("suggestion"):
                                                st.caption(issue["suggestion"])
                                if post.reasoning_content:
                                    with st.expander("🧠 思维链（reasoner 模型专属）"):
                                        st.text(post.reasoning_content)

                with st.expander("素材理解", expanded=False):
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

# ---------- 用量 ----------
with tab_logs:
    c1, c2, c3 = st.columns(3)
    c1.metric("累计输入 tokens", ss.total_tokens_in)
    c2.metric("累计输出 tokens", ss.total_tokens_out)
    c3.metric("已处理文章数", sum(1 for a in ss.articles if "posts" in a))
    st.info(f"当前提供商：**{provider}** ｜ 模型：`{model}` ｜ API：`{api_url}`")
    if st.button("🗑 清空所有结果（不删队列）", use_container_width=True):
        # 切换模型后旧 Post 仍残留在 session_state，这个按钮把它们全部清掉
        for a in ss.articles:
            a.pop("extract", None)
            a.pop("posts", None)
        ss.total_tokens_in = 0
        ss.total_tokens_out = 0
        st.success("已清空所有处理结果，下次点「开始处理」会全部重新生成")
        st.rerun()
