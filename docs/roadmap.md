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

## 💡 其他想法（未排期）

- [ ] 用户帐号 + 历史记录：让用户登录后能看到自己历史生成的稿件
- [ ] 自动多语言扩展：除中→英外加日 / 韩 / 西
- [ ] 平台数据反馈闭环：让用户回填"哪条文案发布效果好"，进 prompt 微调
- [ ] 视频 / 音频转脚本（VLog → 各平台文案）
- [ ] Telegram 单独跑 bot（如果有海外用户需求）
