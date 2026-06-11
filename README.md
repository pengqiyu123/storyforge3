# StoryForge3

中文网文全流程创作引擎。从空白页创建书籍，生成世界观、角色、卷纲和章节，再经过 AI 起草、36 条机械审计、LLM 审计、多模式修订、truth 提取和多格式导出，最终产出可发布章节。

## 快速开始

以下命令以 Windows PowerShell 为准。新用户按顺序执行，通常 10 分钟内可以启动本地 API 和 Web 写作工作台。

### 环境要求

- Python >= 3.11
- Node.js >= 18
- pnpm
- CC-Switch 可选，用于导入 AI provider；也可以手动写 `.storyforge3/providers.json`

验证：

```powershell
python --version
node --version
pnpm --version
```

### 后端启动

```powershell
cd D:\python\Novel\storyforge3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\storyforge3.exe serve --port 8000
```

另开一个 PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

成功时会返回 `ok = True`，并在 `data.status` 中看到 `ok`。

### 前端启动

```powershell
cd D:\python\Novel\storyforge3\web
pnpm install
pnpm dev
```

打开浏览器：

```text
http://localhost:5173
```

验证 API 代理：

```powershell
Invoke-RestMethod http://localhost:5173/api/health
```

### 配置 AI 提供商

方式一：在 Web 的 Provider 页面从 CC-Switch 导入。

方式二：手动创建 `.storyforge3/providers.json`。下面是最小可运行结构，替换 `api_key`、`base_url` 和 `model_id`：

```json
{
  "active_provider_key": "local-openai-compatible",
  "providers": [
    {
      "id": "manual-openai-compatible",
      "provider_key": "local-openai-compatible",
      "label": "本地 OpenAI 兼容 Provider",
      "base_url": "https://api.example.com/v1",
      "api_key": "<YOUR_API_KEY>",
      "model_id": "gpt-5.5",
      "enabled": true,
      "source": "manual",
      "cc_app_type": "codex",
      "cc_api_format": "openai_responses",
      "cc_is_full_url": false,
      "cc_endpoint_auto_select": true,
      "cc_endpoint_candidates": [],
      "cc_base_url_raw": "https://api.example.com",
      "cc_usage_base_url": "https://api.example.com/v1",
      "cc_last_verified_endpoint": null,
      "cc_last_verified_format": null,
      "cc_last_verified_model": null
    }
  ]
}
```

验证 provider 是否能连通：

```powershell
.\.venv\Scripts\storyforge3.exe health
```

### 第一个章节

在 Web UI 中按这个顺序操作：

1. 进入“我的小说”，创建书籍：都市 / 番茄 / 10 章 / 每章 2500 字。
2. 打开书籍详情，进入“世界观”，输入种子并构建世界观。
3. 进入“角色”，创建主角和关键配角。
4. 进入“章节”，对第 1 章执行 `plan -> draft -> audit`。
5. 如果审计未通过，执行 `revise` 后重新审计。
6. 审计通过后导出章节或整本书。

验证书籍已创建：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/books
```

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 长篇章节管线 | `plan -> draft -> normalize -> audit -> revise -> truth -> export` |
| 机械审计 | 36 条规则，覆盖结构、风格、平台格式和元信息 |
| 修订模式 | 5 种模式：polish、spot_fix、anti_detect、surgical、rework |
| Truth 系统 | SQLite + JSON 备份，追踪跨章事实、角色变化和伏笔 |
| 导出格式 | 番茄 TXT、Markdown、EPUB、起点 TXT |
| 短篇管线 | 独立 5 步短篇流程：plan、draft、audit、revise、export |
| 同人模式 | 导入 canon，注入角色语音、世界规则和审计上下文 |
| MCP Server | 15 个 tool，供外部 AI 代理调用创作流程 |
| Web 工作台 | 书籍管理、章节管线、审计定位、修订 diff、truth、快照、导出预览 |

## 目录结构

```text
storyforge3/
├── src/storyforge3/       # Python 引擎、FastAPI、服务层、审计、导出
├── web/                   # React + Vite 写作工作台
├── src-tauri/             # 桌面壳工程
├── scripts/               # E2E、诊断、sidecar 构建脚本
├── docs/                  # 路线图、指令、调研、使用文档
├── tests/                 # 后端与 API 测试
├── books/                 # 本地书籍数据，默认不入库
└── .storyforge3/          # 本地 provider 配置，默认不入库
```

## 开发

```powershell
# 后端测试
.\.venv\Scripts\python.exe -m pytest tests\ -q

# Python lint
.\.venv\Scripts\python.exe -m ruff check .

# 前端测试与构建
pnpm --dir web test
pnpm --dir web build

# 启动 MCP Server
.\.venv\Scripts\python.exe -m storyforge3.mcp
```

MCP 注册说明见 `docs/mcp-registration.md`。

## 许可

MIT
