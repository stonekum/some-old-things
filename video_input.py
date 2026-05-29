"""视频 / 音频 → 文本（ASR 适配层）

设计原则：UI 和 pipeline 不应该知道是哪家 ASR 在干活。所有 backend 都实现
`Transcriber` 协议，调用方只调 `.transcribe(file_bytes, filename, mime) -> str`。

当前状态（tracer bullet 阶段）：
- StubTranscriber 是默认实现，返回一段占位文本 + 提示用户去切换真后端。
- 真后端候选见 docs/video-input-status.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# 允许的文件格式（白名单）+ 上限大小（MB）
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
ALLOWED_AUDIO_EXTS = {".mp3", ".wav", ".m4a"}
ALLOWED_EXTS = ALLOWED_VIDEO_EXTS | ALLOWED_AUDIO_EXTS
MAX_UPLOAD_MB = 50  # Streamlit Cloud 默认 200MB，自身限 10MB 已在 .streamlit/config.toml 改成 10
                    # 这里再叠一层业务上限，ASR 后端通常有自己的限制


@dataclass
class TranscriptionResult:
    """ASR 调用的统一返回。"""

    text: str
    backend: str
    notes: str = ""           # 给用户的额外提示（占位 / 警告 / 模型名等）
    is_placeholder: bool = False  # True 表示这不是真 ASR 结果，调用方应当显眼提示


class Transcriber(Protocol):
    """所有 ASR 后端实现这个协议。"""

    name: str

    def transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        mime: str | None = None,
    ) -> TranscriptionResult: ...


# ── Stub 实现 ────────────────────────────────────────────────────────────────
# 这次只上 stub。等 SJTU 或 OpenAI ASR 选定后，新增一个类即可，UI/pipeline 不动。

_STUB_TRANSCRIPT_TEMPLATE = """\
[此为 ASR 占位输出 · 当前未接入真实语音转文本服务]

上传文件信息：
- 文件名：{filename}
- 大小：{size_kb} KB
- MIME：{mime}

请按下列任一选项接入真实 ASR：
1. SJTU Claw 平台若有音频模型，更新 video_input.py 加 SJTUTranscriber 类
2. 添加 OPENAI_API_KEY 环境变量 + 实现 OpenAIWhisperTranscriber（推荐，中文质量高）
3. 本地部署 faster-whisper（适合长期免费但不适合 Streamlit Cloud）

——— 以下为示例文本，仅用于验证下游流程能否走通 ———

5 月 28 日，上海交通大学举行学生科技创新成果展。今年共有来自 12 个学院的 86 个项目参展，
涵盖人工智能、新能源、生物医药等方向。校长在开幕式上表示，希望同学们把论文写在祖国大地上。
现场还设置了路演环节，参展学生与企业代表进行了深入交流。
"""


class StubTranscriber:
    """占位 ASR：不调网络、不解码音频。只回示例字符 + 显眼警告。

    目的是让 UI + 既有 extract/generate pipeline 能在没接 ASR 的情况下端到端跑通。
    """

    name = "stub"

    def transcribe(
        self,
        file_bytes: bytes,
        filename: str,
        mime: str | None = None,
    ) -> TranscriptionResult:
        text = _STUB_TRANSCRIPT_TEMPLATE.format(
            filename=filename,
            size_kb=len(file_bytes) // 1024,
            mime=mime or "unknown",
        )
        return TranscriptionResult(
            text=text,
            backend=self.name,
            notes="⚠️ 这是占位文本，不是真实视频内容。请接入 ASR 后端。",
            is_placeholder=True,
        )


# ── 默认实例 + 工厂 ─────────────────────────────────────────────────────────

def get_default_transcriber() -> Transcriber:
    """工厂函数：默认返回 stub。日后可加 ENV 变量切换后端。"""
    return StubTranscriber()


# ── 校验工具 ────────────────────────────────────────────────────────────────

def validate_upload(filename: str, size_bytes: int) -> tuple[bool, str]:
    """返回 (是否合法, 错误信息)。Streamlit 上传前的轻量预检。"""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return False, f"不支持的格式 {ext!r}；当前接受：{sorted(ALLOWED_EXTS)}"
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return False, f"文件 {size_mb:.1f}MB 超过 {MAX_UPLOAD_MB}MB 上限"
    return True, ""
