# copy_workflow — 中英社交文案生成工作流

一站式工作流：爬取素材 → 双语提取 → 按平台批量生成文案 → 质量审稿/自动修订 → 输出 Markdown

```
爬取  →  提取（中英双语）  →  生成（按平台）  →  审稿/修订  →  Markdown 文件
```

相比原来一堆散乱的 `.py` 脚本，主要改进：

- 提取和翻译合并成一次 API 调用，节省约 50% token
- 线程池并发调用 LLM，速度提升 4-8 倍
- SHA-256 磁盘缓存，重跑不花钱，崩溃后可续跑
- Pydantic 校验 JSON 输出，失败自动修复重试一次
- 每个平台独立 prompt 模板（Instagram / Twitter / LinkedIn / Facebook / 微信）
- 密钥写在 `.env`，路径写在 `config.yaml`，不硬编码

---

## 安装

```bash
cd copy_workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

cp .env.example .env
# 把你的 DeepSeek API Key 填进 .env
```

---

## 方式一：Streamlit 网页版（推荐）

单文件，无需手动管理包：

```bash
pip install -e ".[streamlit]"
streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

- 侧边栏填入 API Key（或设置环境变量 `DEEPSEEK_API_KEY` 自动读取）
- 支持三种输入方式：粘贴文本 / 粘贴 URL（微信公众号 / 交大新闻 / 通用网页） / 上传 `.txt` 文件
- 选好目标平台，点「开始处理」，文案按平台分 tab 展示
- 每条文案可单独下载 `.md`，也可一键打包 `.zip`

**部署到 Streamlit Cloud：**
1. 打开 https://share.streamlit.io/，用 GitHub 登录
2. New App → 选这个仓库 → 入口文件填 `app.py`
3. Advanced settings → Secrets 里加：
   ```
   DEEPSEEK_API_KEY = "sk-你的新key"
   # 如果用交大内网，还可以加：
   SJTU_API_KEY = "你的交大Key"
   # 强烈建议加访问密码，否则陌生人扫到 URL 就能用你的 Key：
   APP_PASSWORD = "一个你自己想的强密码"
   ```
4. 点 Deploy

**安全说明：**
- 一旦 `DEEPSEEK_API_KEY` / `SJTU_API_KEY` 设在 Secrets 里，**Sidebar 的 Key 输入框会完全消失**，访客拿不到也改不了。
- 一旦 `APP_PASSWORD` 设在 Secrets 里，应用启动会先弹密码门禁，错误密码无法进入主界面。
- URL 抓取经过 SSRF 防护：内网/本地/云元数据地址（10/172.16/192.168/127/169.254 等）会被拒绝，redirect 上限 3 跳，响应体上限 5MB。

---

## 模型与提供商

支持两个 API 提供商，侧边栏切换：

- **DeepSeek 官方** · 直连 `api.deepseek.com`，按 token 计费
  - `deepseek-v4-flash`（默认）· 284B / 13B 激活参数 · 速度快、便宜
  - `deepseek-v4-pro` · 1.6T / 49B 激活参数 · 复杂推理 / Agent / 代码任务
  - 旁边的 `🧠 启用思维链` 开关控制是否走 thinking mode
- **交大内网 (SJTU)** · 走 `models.sjtu.edu.cn`，免费额度大，**校外需 VPN**
  - Key 领取：`my.sjtu.edu.cn → APP → API`

旧 `deepseek-chat` / `deepseek-reasoner` alias 已于 2026-07-24 退役，本项目默认列表不再列出。

---

## 方式二：命令行（CLI）

```bash
pip install -e .                    # 安装 copy-workflow 命令
cp .env.example .env && vim .env    # 填入 DEEPSEEK_API_KEY

# 从已爬取的文章中提取双语结构化信息
copy-workflow extract --input ../爬虫文/微信平台

# 按平台生成文案（默认读取 data/extracted 下所有提取结果）
copy-workflow generate --platforms instagram,twitter --variants 1

# 只从指定提取结果生成；可传单个 JSON、目录，或逗号分隔列表
copy-workflow generate --extracts data/extracted/某篇文章.json --platforms instagram,twitter

# 一步到位：提取 + 生成；只会生成本次提取命中的文章，不会把旧 extracts 全部重跑
copy-workflow all --input ../爬虫文/微信平台

# 爬取新文章
copy-workflow crawl wechat        # 读取 config.yaml 里配置的链接文件
copy-workflow crawl sjtu_news
```

输出文件位置：`data/posts/<日期>__<文章名>/<平台>.md`

说明：
- `extract --input` 会递归读取目录下所有 `.txt`，因此可以直接传 `data/raw/sjtu_news`。
- `crawl` 完成后会打印下一步可复制的 `extract --input ...` 命令。
- CLI 生成阶段默认会做质量审稿，低分或不可发布稿会自动修订一次。
- 历史风格参考来自 `config.yaml` 的 `paths.history_dir`；该目录不存在时仍可运行，只是不会注入历史语感。

---

## 怎么新增一个平台

1. 在 `src/copy_workflow/prompts/` 下新建 `generate_<平台名>.v1.md`（参考 Instagram 模板）。
2. 在 `config.yaml` 的 `generation.default_platforms` 里加上这个平台名，或用 `--platforms <平台名>` 临时指定。

## 怎么新增一个爬虫

1. 在 `src/copy_workflow/crawlers/` 下新建 `<来源>.py`，暴露 `crawl(links_file, out_dir)` 函数。
2. 在 `cli.py` 的 `crawl` 子命令里接入。

---

## 项目结构

```
app.py                   Streamlit 单文件应用（含全部功能）
requirements.txt         Streamlit Cloud 部署依赖
config.yaml              路径、模型、平台、并发等配置
src/copy_workflow/
├── config.py            环境变量 + yaml 配置读取
├── llm.py               DeepSeek 客户端（重试、JSON 模式、token 日志）
├── cache.py             SHA-256 磁盘缓存
├── models.py            Pydantic 数据模型
├── extract.py           文本 → 双语 JSON
├── generate.py          JSON → 各平台文案
├── exporters.py         文案 → Markdown 文件
├── style_seed.py        从历史案例提炼风格摘要
├── cli.py               命令行入口
├── crawlers/            wechat.py、sjtu_news.py
└── prompts/             各平台 prompt 模板（版本化 .md 文件）
legacy/                  原始旧脚本归档（仅供参考，密钥已脱敏）
tests/                   单元测试（覆盖缓存、模型校验、JSON 解析、SSRF 防护、平台路由、质量审稿、CLI 流程等）
```

---

## 排错

| 症状 | 原因 / 处理 |
|---|---|
| 点生成后没反应 | API 慢响应。看 streamlit 终端的 `[llm_chat]` 日志确认是否仍在调用 |
| `400 Bad Request` 含 `response_format` | SJTU/自建代理不支持 OpenAI JSON 模式；代码会自动降级重试 |
| ping 通但生成卡住 | VPN 增加延迟，单次 10-25s × N 平台 = 几分钟；关掉质量审核可加速 |
| `ConnectionError` 连 SJTU | 检查是否开了交大 VPN |
| 切换 provider 后吃旧缓存 | v4 缓存 key 已含 api_url + thinking，不再串味；右下角"清空所有结果"可强制刷新 |
| `400` 提示模型不存在 | 用 sidebar 的"🔧 诊断工具 → 📋 列出该后端支持的模型"看真实可用列表 |

