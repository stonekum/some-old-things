# Changelog

本文件按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格记录变更。

## [Unreleased]

### UX
- 默认目标平台改为除微信公众号、小红书以外全部勾选（instagram / twitter / linkedin / facebook）
- 诊断按钮（列出模型 / 测试连接）收进可折叠的 `🔧 诊断工具`
- `Temperature` → `创意度 (Temperature)`，加 help 说明典型数值
- `重写阈值` → `质量门槛`，help 加典型分数分布说明
- 并发数 slider 标注 "SJTU 强制单线程" 避免混淆
- 新增 `📝 加载示例文章` 按钮，首次用户无需自备素材即可试跑

### Docs
- README 同步到 V4 / SJTU / thinking mode 现状，统一安装命令为 `pip install -e ".[streamlit]"`
- README 新增"模型与提供商"章节和"排错"表
- 新增 `LICENSE` (MIT) 与 `CHANGELOG.md`
- `legacy/` 加 README 说明归档身份
- `.env.example` 补充 `SJTU_API_KEY` / `APP_PASSWORD`
- `.streamlit/config.toml` 锁定主题色 + 关 telemetry
- 包 `__init__.py` 显式声明 `__all__`，包版本升 0.2.0

### Fix
- `config.yaml` / `src/copy_workflow/config.py` 默认模型 `deepseek-chat` → `deepseek-v4-flash`
  （旧 alias 已于 2026-07-24 退役）
- 测试连接失败提示去掉 v3 时代的"吃了缓存"残留文案

## 2026-05-28

### Feat
- 升级到 DeepSeek V4 命名（`deepseek-v4-flash` / `deepseek-v4-pro`），下拉只暴露 V4 新模型
- 思维链由独立 checkbox 显式控制，下发 `thinking={"type": "enabled"|"disabled"}`
- 缓存 key 加入 thinking 维度（v3 → v4）
- json_mode 4xx 自动降级（兼容 SJTU 等代理后端）
- 单线程模式下按 LLM 调用粒度更新进度
- 连接测试结果基于 `reasoning_content` 实际激活情况判断
- SJTU 模型列表对齐后端 GET /models 实测结果

### Fix
- 缓存跨提供商串味（cache key 加入 api_url，v2 → v3）
- 错误显示被进度条遮挡
- timeout 从 180s × 3 retry 收紧到 60s × 2 retry

### Security
- API Key 服务端配置时完全隐藏输入框
- `APP_PASSWORD` 门禁
- SSRF 防护（`_assert_safe_url` + redirect 上限 3 跳 + 5MB 响应上限）

### Quality
- Self-Refine 模块：generate → review (0-100 分) → 低于门槛自动重写
