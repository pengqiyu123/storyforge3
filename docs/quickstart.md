# 快速开始

这份文档是 README 的展开版，目标是让新用户从零启动 StoryForge3 本地 Web 工作台，并完成第一章的基础流程。

## 1. 环境准备

### 1.1 安装工具

需要：

- Python 3.11 或更新版本
- Node.js 18 或更新版本
- pnpm

验证命令：

```powershell
python --version
node --version
pnpm --version
```

如果 `pnpm` 不存在：

```powershell
corepack enable
corepack prepare pnpm@latest --activate
pnpm --version
```

### 1.2 安装后端

```powershell
cd D:\python\Novel\storyforge3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

验证：

```powershell
.\.venv\Scripts\python.exe -c "import storyforge3; print(storyforge3.__file__)"
.\.venv\Scripts\storyforge3.exe --help
```

### 1.3 启动后端

```powershell
cd D:\python\Novel\storyforge3
.\.venv\Scripts\storyforge3.exe serve --port 8000
```

另开终端验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

预期：响应中 `ok` 为 `True`，`data.status` 为 `ok`。

### 1.4 启动前端

```powershell
cd D:\python\Novel\storyforge3\web
pnpm install
pnpm dev
```

打开：

```text
http://localhost:5173
```

验证前端代理：

```powershell
Invoke-RestMethod http://localhost:5173/api/health
```

## 2. 配置 AI 提供商

StoryForge3 默认从 `.storyforge3/providers.json` 读取已导入的 provider。你可以从 CC-Switch 导入，也可以手动创建配置。

### 2.1 使用 CC-Switch 导入

1. 先在 CC-Switch 中配置并启用一个 provider。
2. 启动 StoryForge3 后端和前端。
3. 在 Web UI 的 Provider 页面查看可导入 provider。
4. 导入后设置为 active provider。
5. 使用健康检查验证。

验证：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/providers
.\.venv\Scripts\storyforge3.exe health
```

### 2.2 手动创建 providers.json

创建目录：

```powershell
cd D:\python\Novel\storyforge3
New-Item -ItemType Directory -Force .storyforge3 | Out-Null
notepad .storyforge3\providers.json
```

填入：

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

字段说明：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `active_provider_key` | 是 | 当前启用的 provider key |
| `providers[].provider_key` | 是 | provider 的稳定 key |
| `providers[].label` | 是 | UI 展示名 |
| `providers[].base_url` | 是 | API 基础地址，OpenAI 兼容通常以 `/v1` 结尾 |
| `providers[].api_key` | 是 | API key，不要提交到 Git |
| `providers[].model_id` | 是 | 默认模型 |
| `providers[].enabled` | 是 | 是否允许使用 |
| `providers[].cc_api_format` | 建议 | `openai_responses`、`openai_chat`、`anthropic` 或 `gemini_native` |
| `providers[].cc_endpoint_auto_select` | 建议 | `true` 时允许 SF3 自动选择兼容路由 |

验证 JSON：

```powershell
.\.venv\Scripts\python.exe -m json.tool .storyforge3\providers.json
.\.venv\Scripts\storyforge3.exe health
```

## 3. 环境变量

StoryForge3 使用 `pydantic-settings` 读取环境变量和 `.env`。字段名可直接用大写环境变量覆盖。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PROVIDERS_CONFIG_DIR` | `.storyforge3` | provider 配置目录 |
| `LLM_TIMEOUT_SECONDS` | `120` | 普通 LLM 请求超时 |
| `LLM_DRAFT_TIMEOUT_SECONDS` | `300` | 起草/修订等长生成超时 |
| `LLM_SHORT_TIMEOUT_SECONDS` | `60` | 短请求超时 |
| `HEALTH_CHECK_ON_STARTUP` | `true` | 启动时是否做健康检查 |
| `DEFAULT_MODEL` | `gpt-4o` | 默认模型；通常由 provider 的 `model_id` 覆盖 |
| `WRITER_MODEL` | 空 | 写作任务模型覆盖 |
| `AUDITOR_MODEL` | 空 | 审计任务模型覆盖 |
| `TRUTH_EXTRACTOR_MODEL` | 空 | truth 提取模型覆盖 |
| `ARCHITECT_MODEL` | 空 | 世界观/角色构建模型覆盖 |
| `PLANNER_MODEL` | 空 | 章节规划模型覆盖 |
| `BOOKS_DIR` | `books` | 本地书籍目录 |
| `SNAPSHOT_ENABLED` | `true` | 导出前是否创建快照 |
| `SNAPSHOT_MAX_COUNT` | `5` | 每本书保留快照数量 |

示例 `.env`：

```env
PROVIDERS_CONFIG_DIR=.storyforge3
BOOKS_DIR=books
WRITER_MODEL=gpt-5.5
AUDITOR_MODEL=gpt-5.5
LLM_DRAFT_TIMEOUT_SECONDS=300
```

验证配置：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## 4. 从零到第一章

### 4.1 创建书籍

Web UI 操作：

1. 打开 `http://localhost:5173`
2. 进入“我的小说”
3. 点击创建按钮
4. 填写：书名、题材、平台、目标章节数、每章字数
5. 提交后进入书籍详情页

API 验证：

```powershell
$body = @{
  title = "我是路人甲"
  genre = "都市"
  platform = "tomato"
  target_chapters = 10
  chapter_word_count = 2500
} | ConvertTo-Json

Invoke-RestMethod http://127.0.0.1:8000/api/books -Method Post -Body $body -ContentType "application/json"
Invoke-RestMethod http://127.0.0.1:8000/api/books
```

### 4.2 构建世界观

Web UI 操作：

1. 进入书籍详情
2. 打开“世界观”Tab
3. 输入种子：“都市校园 + 超能力觉醒”
4. 点击构建

需要 LLM provider 连通。

### 4.3 创建角色

Web UI 操作：

1. 打开“角色”Tab
2. 输入：“主角，18 岁，高中生，性格沉稳”
3. 点击创建

### 4.4 运行章节管线

Web UI 操作：

1. 打开“章节”Tab
2. 选择第 1 章
3. 依次执行 `plan`、`draft`、`audit`
4. 如果有阻断问题，执行 `revise`，再 `audit`
5. 审计通过后导出

CLI 验证：

```powershell
.\.venv\Scripts\storyforge3.exe chapter status <book_id> 1
```

## 5. 常见问题

### 后端命令找不到

现象：`storyforge3` 不是可识别命令。

处理：

```powershell
cd D:\python\Novel\storyforge3
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\storyforge3.exe --help
```

验证：看到 `serve`、`book`、`chapter` 等子命令。

### 端口 8000 被占用

现象：启动时报地址已占用。

处理：

```powershell
.\.venv\Scripts\storyforge3.exe serve --port 8010
```

同时修改 `web/vite.config.ts` 的 proxy target，或临时直接访问后端 API 验证。

### 健康检查可用，但生成失败

现象：`/api/health` 正常，`plan` 或 `draft` 报 provider 不可达。

处理：

```powershell
.\.venv\Scripts\storyforge3.exe health
Get-Content .storyforge3\providers.json
```

确认 `active_provider_key` 能匹配某个 `provider_key`，且 `api_key`、`base_url`、`model_id` 真实可用。

### 前端页面打开但 API 报错

现象：Web UI 能打开，但列表为空或 toast 报网络错误。

处理：

```powershell
Invoke-RestMethod http://localhost:5173/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果第二条成功、第一条失败，检查 Vite dev server 是否在 `web/` 目录启动。

### LLM 请求很慢

现象：起草或修订需要数分钟。

处理：这是中转 provider 和长文本生成的常见情况。等待当前任务完成，不要重复点击同一按钮。必要时提高：

```env
LLM_DRAFT_TIMEOUT_SECONDS=420
```

### 书籍数据在哪里

默认在：

```text
books/
```

可用环境变量修改：

```powershell
$env:BOOKS_DIR="D:\StoryForge3Books"
.\.venv\Scripts\storyforge3.exe serve --port 8000
```

## 6. 下一步

- MCP 集成：见 `docs/mcp-registration.md`
- Dogfood 测试：见 `docs/dogfood-protocol.md`
- 发布与桌面打包：见 `docs/release-setup.md`
