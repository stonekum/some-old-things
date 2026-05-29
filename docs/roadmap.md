# Roadmap

可能的未来方向，按"想做就来看"组织——不是 TODO 列表，是**决策档案**。

---

## 🤔 Agent 化（暂缓 · 2026-05-28 评估）

把 copy_workflow 从 Streamlit 单一前端，升级成多前端 agent（参考 [kuan-er/sjtu-agent](https://github.com/kuan-er/sjtu-agent)）。

### 当时为什么没做

- 受众是校内小规模组织，Streamlit URL 直接传递够用
- 工作量 5-10 天，性价比不高
- 没有"Streamlit 解决不了的具体痛点"

### 什么时候应该重新评估

满足下列**至少一个**条件再回来看：

- [ ] MAU 突破 ~50 人，开始有"能不能手机原生用"的需求
- [ ] 校内 sjtu-agent 装机率高，MCP 集成能立刻覆盖大盘
- [ ] 想做更多工具（翻译 / 总结 / 排版 / 发布调度），需要 agent 架构作为地基
- [ ] 想把它当简历项目 / 学习 agent 架构

### 已设计好的 MVP 方案（来日可直接执行）

参考 sjtu-agent 架构，MVP = 4 个模块，约 2.5 天：

| 模块 | 工作量 |
|---|---|
| 核心 agent loop（tool registry + LLM tool calling） | 1-1.5 天 |
| Setup 向导（首次配置） | 0.5 天 |
| Terminal chat（最薄前端，开发自测用） | 0.5 天 |
| MCP server (HTTP，给 sjtu-agent / Claude Desktop / Cursor 调用) | 0.5 天 |

第二期：WeChat (企业微信) bot · Streamlit 接入新架构 · daemon 安装。

### 折中方案

如果完整 agent 觉得太重，但又想试水：**只做 MCP server，1 天**。Streamlit 完全不动，sjtu-agent 用户原地可用。

### 关键参考

- [kuan-er/sjtu-agent](https://github.com/kuan-er/sjtu-agent)（架构模板）
- 你跑 Claw 后端的 SJTU 模型支持列表（参见 CHANGELOG 2026-05-28）
- [MCP 官方文档](https://modelcontextprotocol.io)
- [Anthropic Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)

---

## 🎨 前端框架选型（已定 · 2026-05-29 评估）

**结论：留在 Streamlit，不迁移。** 当时刚做完"活字工坊"编辑式 UI 重设计，证明 Streamlit
在合理设计下视觉上限远比想象高，框架不是设计差的根本原因。

### 评估时的对比矩阵

| 方案 | 适合度 | 设计上限 | 工作量 | 备注 |
|---|---|---|---|---|
| **Streamlit（现状）** | ⭐⭐⭐⭐ | ⭐⭐⭐ | 0 | 控件基因仍透出，但够用；维护成本最低 |
| Gradio | ⭐⭐ | ⭐⭐⭐ | 3-5 天 | 同一档，迁移收益小 |
| Reflex | ⭐⭐⭐ | ⭐⭐⭐⭐ | 1 周 | 纯 Python → React，学习曲线陡 |
| **FastAPI + HTMX + Jinja2 + Tailwind** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 5-7 天 | **如果真要迁移，选这个** |
| FastAPI + Next.js / Astro | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 2-3 周 | 双仓库、需 Node 生态，过度工程 |
| SvelteKit + FastAPI | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 2-3 周 | 比 Next.js 简洁，但社区小 |

### 什么时候应该重新评估

满足下列**至少一个**条件再回来看（审美**不算**理由）：

- [ ] Streamlit 在移动端真的不好用，且移动端是主要场景
- [ ] 想做用户登录 + 历史归档，Streamlit 的 session_state 模型扛不动
- [ ] 同时在线人数 > 20，Streamlit 的单进程并发模型扛不动
- [ ] 想加复杂前端交互（拖拽编辑、富文本、实时协作）

### 如果重新评估，推荐路径

**FastAPI + HTMX + Jinja2 + Tailwind**——理由：

- 复用现有 `src/copy_workflow/` Python 包（业务逻辑零改动）
- 服务端渲染，无需 Node.js / 构建管线
- HTMX 一个 JS 文件搞定"按钮 → 后端 → 局部替换 HTML"的整套交互模型
- Tailwind 给到完整 CSS 自由度
- 单 Python 进程部署，仍然 Streamlit Cloud 不行就换 Fly.io / Cloud Run
- 总工作量 5-7 天，对比迁 React 至少 2-3 周

### 关键教训（不要忘）

> **审美问题不是框架问题。** 同一个 Streamlit，可以做出政务红条样板间，也可以做出
> "活字工坊"编辑式版头。差别在于**有没有先想清楚"这工具是什么"**。

类比：换框架就像换钢琴。差的演奏者换施坦威也弹不出好曲子；好的演奏者用立式琴也能动人。
设计方向 > 框架能力。

---

## 💡 其他想法（未排期）

- [ ] 用户帐号 + 历史记录：让用户登录后能看到自己历史生成的稿件
- [ ] 自动多语言扩展：除中→英外加日 / 韩 / 西
- [ ] 平台数据反馈闭环：让用户回填"哪条文案发布效果好"，进 prompt 微调
- [ ] 视频 / 音频转脚本（VLog → 各平台文案）—— `feat/video-input` 分支 tracer bullet
      完成后**暂停**（2026-05-29）。SJTU Claw 全模型确认无 ASR 能力
      （Qwen3.5-27B 仅图像 + 文本）；剩余路径都需付费 API 或自建服务器。
      详见分支上的 `docs/video-input-status.md`
- [ ] Telegram 单独跑 bot（如果有海外用户需求）
