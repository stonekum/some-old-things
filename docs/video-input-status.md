# 视频输入功能 · 当前状态

> Branch: `feat/video-input` · 启用 2026-05-29
>
> **🛑 状态：暂停（2026-05-29）。** UI + pipeline tracer bullet 已完成，
> 但因 ASR 后端没有零成本可用方案，主动暂停推进。本分支保留在 GitHub，
> 等愿意接入付费 ASR（OpenAI / 火山引擎）或自建 whisper 服务器时可以直接续做。

## 为什么暂停（关键发现）

调查了 SJTU OpenClaw 官方 API 文档（<https://claw.sjtu.edu.cn/guide/sjtu-api/>），
**确认 SJTU 当前 5 个模型里没有任何 ASR 能力**：

| 模型 | 模式 |
|---|---|
| DeepSeek V3.2 (chat) | 通用文本 |
| DeepSeek V3.2 (reasoner) | 文本深度推理 |
| MiniMax-M2.7 | 文本生成 / 智能体 |
| GLM-5.1 | 文本生成 / 代码 |
| **Qwen3.5-27B** | **多模态：视觉 + 文本**（**不含音频**） |

Qwen3.5-27B 虽然标注"多模态"，但官方示例只接受 `image_url` 字段——**是 VLM，
不是 audio 模型**。全文搜 `audio` / `whisper` / `语音` / `音频` / `转录` 零结果。

结论：**SJTU 这条路（曾经唯一的"免费"路径）走不通**。剩下的选项都需要付费 API
或自建机器。在校内小规模、实验性功能的场景下，"投资 ASR 基础设施"性价比不够，
所以暂停。

## 已完成（这次 commit）

- `video_input.py`：Transcriber 协议 + `StubTranscriber` 占位实现 + 上传校验
- `app.py`：「方式 D：上传视频 / 音频」上传区，转录后塞进既有 queue
- `tests/test_video_input.py`：5 个单元测试覆盖 stub 与 validator
- `.streamlit/config.toml` 已经把 `maxUploadSize=10` —— 后续若启用真 ASR 可调高
- 业务上限 `MAX_UPLOAD_MB = 50`（叠在 Streamlit 上限之上）

走通的链路：
```
上传 .mp4/.mov  →  StubTranscriber  →  示例文本  →  加入 queue  →  既有 extract  →  既有 generate
```

UI 上 stub 返回会显眼标记 ⚠️ 占位，避免被误以为真 ASR 在工作。

## ASR 后端选项对比

| 选项 | 中文 ASR 质量 | 成本 | 实现工作量 | 风险 |
|---|---|---|---|---|
| **OpenAI Whisper API** | ⭐⭐⭐⭐ | $0.006/分钟（≈ ¥0.04） | 0.5 天 | 需要 `OPENAI_API_KEY`；走国外网络 |
| **本地 faster-whisper** | ⭐⭐⭐⭐ | 0 | 1 天 | Streamlit Cloud 免费档 CPU 扣不动；需要本机或自建服务器 |
| **火山引擎 ASR** | ⭐⭐⭐⭐⭐ | ¥0.012/分钟 | 1 天 | 需注册火山引擎账号 + 实名 |
| **阿里云 ASR** | ⭐⭐⭐⭐⭐ | ¥0.0145/分钟 | 1 天 | 需阿里云账号 |
| ~~**SJTU Claw 多模态**~~ | ❌ | — | — | **2026-05-29 已验证：无 ASR；Qwen3.5-27B 仅支持图像** |
| **DeepSeek 多模态** | — | — | — | ❌ 当前 API 无 audio 端点 |
| **Qwen3.5-27B VLM 替代方案** | ⭐⭐（只看画面） | 免费 | 1.5 天 | 抽帧 → 视觉描述。**会丢讲话内容**，适合风光片不适合演讲 |

## 续作时的决策路径

恢复推进时，按下面这个顺序选：

1. **OpenAI Whisper API**（推荐）
   - 注册 OpenAI 账号 + 充值（$5 起，约 ¥36）
   - Streamlit Secrets 加 `OPENAI_API_KEY`
   - 在 `video_input.py` 加 `OpenAIWhisperTranscriber` 类
   - 改 `get_default_transcriber()`：有 OPENAI_API_KEY → 用 Whisper；否则保留 stub
   - 测试一个 1-2 分钟视频确认中文转录质量
   - 约 0.5 天工作量

2. **本地 faster-whisper**（如果坚持自建 / 隐私要求高）
   - 需要另起一台机器跑（Streamlit Cloud 免费档不行）
   - 装 `faster-whisper` + 下载模型（约 1-2GB）
   - 在 `video_input.py` 加 `LocalWhisperTranscriber`
   - 约 1 天工作量 + 1 台服务器持续运维

3. **Qwen3.5-27B VLM 视觉路径**（场景特殊时）
   - 仅适合"风光延时 / 校园活动剪影"这种**信息在画面**的视频
   - 用 moviepy 抽帧（如每 5 秒 1 帧）
   - 拼成 image_url 数组 → Qwen 描述每帧 → 用 LLM 总结成叙事
   - 完全免费（用 SJTU Qwen 额度）
   - 工作量 1.5 天

## 风险 & 边界条件（已经想过的）

- **大视频文件**：50MB 上限挡掉；后续若启用 OpenAI Whisper 还有 25MB 单次上限
- **长视频转录费用**：1 小时视频 ≈ ¥2.4（OpenAI）/ ¥0.7（火山）—— 单次校园用尚可接受
- **隐私**：上传到第三方 ASR 意味着视频被传出去；自建 faster-whisper 是唯一隐私安全方案
- **听错人名**：所有 ASR 对人名 / 专有名词都有错率。UI 已经把转录结果塞进 queue，
  用户在「队列预览」处可以编辑后再生成

## 不打算做的

- ❌ 视觉理解（看画面里有什么）—— 用户已明确只要音频内容
- ❌ 字幕文件解析（.srt / .ass）—— 等真有需求再说
- ❌ 视频 URL（B站 / YouTube）抓取 —— 当前只接受本地上传
