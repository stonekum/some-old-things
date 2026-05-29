# 视频输入功能 · 当前状态

> Branch: `feat/video-input` · 启用 2026-05-29
>
> 当前位于 **tracer bullet 阶段** —— UI + pipeline 接通，ASR 后端是 stub 占位。

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
| **SJTU Claw 多模态** | ❓ | 免费（如果有）| 0.5 天 | **不确定是否有 audio endpoint** |
| **DeepSeek 多模态** | — | — | — | ❌ 当前 API 无 audio 端点 |

## 下一步选型决策（等做）

按照"先验证 → 再选 → 再做"的顺序：

1. **验证 SJTU 是否有 ASR**
   - 用 Streamlit sidebar 的「📋 列出该后端支持的模型」按钮
   - 如果列表里看到 `whisper-*` / `paraformer-*` / `audio-*` 字样 → 优先用 SJTU
   - 看不到就直接跳到步骤 2

2. **二选一**：
   - 用爱发电：本地 faster-whisper（需另起机器跑）
   - 用现成的：OpenAI Whisper（最稳，成本低）

3. **写对应的 Transcriber 类**
   - 在 `video_input.py` 加 `SJTUTranscriber` 或 `OpenAIWhisperTranscriber`
   - 改 `get_default_transcriber()` 读取 env / config 切换
   - 更新此文档

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
