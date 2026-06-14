# Trae：CC-Switch 模型中转站导入失败差异分析报告

> 对比对象：`D:\python\Novel\storyforge3` 与 `D:\python\Auto-news2\auto-news-studio`  
> 评估重点：依赖包版本、目录结构、配置文件、模型导入路径、相关代码实现、系统环境变量  
> 评估结论：导入失败更可能由 StoryForge3 的配置落盘路径、环境变量无效、API 响应结构差异和火山 `/api/coding` 路由处理差异导致，而不是 CC-Switch 数据库不可用。

---

## 1. 结论摘要

当前 StoryForge3 与 Auto-news2 的 CC-Switch 导入方案虽然同源，但两者在配置持久化、接口响应、运行时 LLM 调用和路由处理上已经出现明显差异。

最可能导致 StoryForge3 导入失败的关键因素如下：

1. **StoryForge3 的 provider 配置默认写入相对路径 `.storyforge3/providers.json`，强依赖后端启动目录。**  
   如果服务从不同 cwd 启动，导入结果可能写到错误位置，运行时读不到 active provider。

2. **StoryForge3 的 `.env.example` 中存在 `CCSWITCH_DB_PATH` 等配置项，但实际 `StoryForge3Config` 不包含这些字段。**  
   这些环境变量会被 `extra="ignore"` 忽略，导致用户以为配置生效，实际仍读默认路径。

3. **Auto-news2 与 StoryForge3 的 API 返回结构不同。**  
   Auto-news2 返回 raw object，StoryForge3 返回统一 envelope：`{ ok, data, error }`。如果复用 Auto-news2 前端逻辑，会出现列表为空或导入失败。

4. **Auto-news2 的旧路由逻辑会剥离 `/api/coding`，这会破坏火山 Coding Plan。**  
   StoryForge3 当前已特意修正为不剥离 `/api/coding`。如果旧方案照搬 Auto-news2，会导致 endpoint 构造错误。

5. **当前环境中未发现 StoryForge3 的 `.storyforge3/providers.json`。**  
   这说明导入结果可能未落盘、落盘位置错误，或当前运行环境未执行过成功导入。

---

## 2. 当前环境核查

### 2.1 CC-Switch 数据库存在

本机检测到 CC-Switch SQLite 数据库：

```text
C:\Users\pengq\.cc-switch\cc-switch.db
```

数据库表结构存在：

- `providers`
- `provider_endpoints`
- `provider_health`

数据统计：

```text
providers: 19
provider_endpoints: 10
provider_health: 4
app_types:
- claude: 11
- claude-desktop: 1
- codex: 6
- gemini: 1
```

因此，失败原因不是 CC-Switch 数据库不存在。

### 2.2 当前系统环境变量未设置

检测到以下变量均未设置：

```text
CCSWITCH_DB_PATH=NOT_SET
CCSWITCH_SETTINGS_PATH=NOT_SET
CCSWITCH_APP_TYPE=NOT_SET
OPENAI_API_KEY=NOT_SET
ANTHROPIC_BASE_URL=NOT_SET
ANTHROPIC_AUTH_TOKEN=NOT_SET
ANTHROPIC_API_KEY=NOT_SET
ANTHROPIC_MODEL=NOT_SET
GOOGLE_GEMINI_BASE_URL=NOT_SET
GEMINI_API_KEY=NOT_SET
GEMINI_MODEL=NOT_SET
DEFAULT_MODEL=NOT_SET
WRITER_MODEL=NOT_SET
AUDITOR_MODEL=NOT_SET
TRUTH_EXTRACTOR_MODEL=NOT_SET
PROVIDERS_CONFIG_DIR=NOT_SET
BOOKS_DIR=NOT_SET
```

这不一定阻止导入，因为导入主要读取 CC-Switch SQLite 中的 key。但如果 StoryForge3 依赖环境变量覆盖配置路径，目前环境并没有提供。

---

## 3. 依赖包差异

### 3.1 Auto-news2

`D:\python\Auto-news2\auto-news-studio\pyproject.toml` 只声明：

```toml
jieba
scikit-learn
networkx
```

但其 LLM 服务实际使用 `openai` SDK：

```python
from openai import OpenAI, ...
```

说明 Auto-news2 的实际运行依赖可能来自外部环境，而非完整写入项目依赖文件。

### 3.2 StoryForge3

StoryForge3 的依赖声明包含：

```toml
pydantic
pydantic-settings
httpx
ebooklib
fastapi
uvicorn
sse-starlette
mcp
```

StoryForge3 的 LLM 服务主要使用 `httpx` 自定义请求，不依赖 OpenAI SDK。

### 3.3 影响

| 项目 | LLM 调用方式 | 影响 |
|---|---|---|
| Auto-news2 | OpenAI SDK + urllib | SDK 自动处理部分 OpenAI 兼容细节 |
| StoryForge3 | httpx 自定义请求 | endpoint、headers、body、响应解析都由项目负责 |

结论：Auto-news2 能跑通的中转站，不代表 StoryForge3 一定能跑通。StoryForge3 对 `endpoint`、`api_format`、`model_id` 的解析更敏感。

---

## 4. 目录结构与配置持久化差异

### 4.1 Auto-news2 配置路径稳定

Auto-news2 基于源码文件推导项目根目录：

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "user-settings.json"
```

特点：

- 配置路径基于项目根目录；
- 不依赖进程启动 cwd；
- 导入结果进入统一 state/config；
- 后端重启后仍能稳定读取。

### 4.2 StoryForge3 配置路径依赖 cwd

StoryForge3 默认配置：

```python
providers_config_dir: str = ".storyforge3"
```

Provider 配置文件：

```text
.storyforge3/providers.json
```

这是相对路径。如果后端从不同目录启动，实际写入位置不同：

| 启动 cwd | 实际 providers.json 路径 |
|---|---|
| `D:\python\Novel\storyforge3` | `D:\python\Novel\storyforge3\.storyforge3\providers.json` |
| `D:\python\Novel` | `D:\python\Novel\.storyforge3\providers.json` |
| Tauri sidecar 目录 | 取决于 sidecar cwd |

当前未发现以下文件：

```text
D:\python\Novel\.storyforge3\providers.json
D:\python\Novel\storyforge3\.storyforge3\providers.json
```

### 4.3 判断

这是最可能的失败根因之一：

```text
导入接口可能执行了，但 providers.json 没写到运行时读取的位置。
```

或：

```text
前端显示导入成功，但 create_llm_service() 重启后读不到 active provider。
```

---

## 5. CC-Switch 数据读取差异

### 5.1 Auto-news2

Auto-news2 的读取逻辑：

- 默认读取 `Path.home() / ".cc-switch" / "cc-switch.db"`；
- 支持 `claude`、`codex`、`gemini`；
- 不支持的 app_type 跳过；
- 无 api_key 的 provider 跳过。

实测读取：

```text
auto_news_count = 15
```

### 5.2 StoryForge3

StoryForge3 的读取逻辑：

- 同样读取 CC-Switch SQLite；
- 支持 `claude`、`codex`、`gemini`；
- 对未知 app_type 会返回空配置 fallback；
- 保留 `has_api_key`、`cc_health`、`cc_endpoint_candidates` 等字段。

实测读取：

```text
storyforge_count = 19
```

StoryForge3 多出的主要是：

- official 空 key provider；
- `claude-desktop` 等非标准 app_type；
- 无 key 配置。

### 5.3 影响

StoryForge3 的导入列表更完整，但也更容易显示不可用 provider。若前端没有禁用 `has_api_key=false` 条目，用户可能选中无法启用的配置。

建议：

- UI 默认隐藏无 key provider；
- 或显示但禁用导入；
- 若导入结果没有任何 keyed provider，应明确报错。

---

## 6. 环境变量与配置文件差异

### 6.1 Auto-news2

Auto-news2 的 `.env.example` 不配置 CC-Switch 路径，而是代码固定读取：

```python
Path.home() / ".cc-switch" / "cc-switch.db"
```

### 6.2 StoryForge3

StoryForge3 的 `.env.example` 写了：

```env
CCSWITCH_SETTINGS_PATH=C:/Users/<you>/.cc-switch/settings.json
CCSWITCH_DB_PATH=C:/Users/<you>/.cc-switch/cc-switch.db
CCSWITCH_APP_TYPE=codex
```

但实际 `StoryForge3Config` 没有：

```python
ccswitch_settings_path
ccswitch_db_path
ccswitch_app_type
```

且配置类使用：

```python
extra="ignore"
```

因此这些变量会被忽略。

### 6.3 判断

如果失败方案依赖 `.env` 中的 `CCSWITCH_DB_PATH` 指定路径，则该方案在当前 StoryForge3 中不会生效。

建议二选一：

1. 删除 `.env.example` 中无效的 CC-Switch 字段；
2. 或正式把 `ccswitch_db_path` 加入 `StoryForge3Config`，并传入 `ProviderConfigManager`。

---

## 7. API 路由与响应结构差异

### 7.1 Auto-news2

API 路由：

```http
GET  /api/admin/llm/cc-switch/providers
POST /api/admin/llm/cc-switch/import
```

返回结构：

```json
{
  "providers": [],
  "db_available": true
}
```

导入返回：

```json
{
  "item": { ...LLMConfig }
}
```

### 7.2 StoryForge3

API 路由：

```http
GET  /providers/available
POST /providers/import
```

返回统一 envelope：

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

### 7.3 影响

如果前端或脚本照搬 Auto-news2，会错误读取：

| Auto-news2 读取 | StoryForge3 应读取 |
|---|---|
| `response.providers` | `response.data.providers` |
| `response.db_available` | `response.data.db_available` |
| `response.item` | `response.data.imported` / `response.data.active_provider_key` |

这会导致：

- provider 列表为空；
- 导入按钮无效；
- active provider 未显示；
- 误判后端失败。

---

## 8. 模型导入路径与运行时使用差异

### 8.1 Auto-news2

导入路径：

```text
CC-Switch DB
 -> read_cc_switch_providers()
 -> import_cc_switch_profiles()
 -> state/config
 -> LLM runtime
```

### 8.2 StoryForge3

导入路径：

```text
CC-Switch DB
 -> CCSwitchDBReader
 -> ProviderConfigManager.import_providers()
 -> .storyforge3/providers.json
 -> create_llm_service()
 -> LLMService
```

如果 `providers.json` 不存在或 active provider 为空，`create_llm_service()` 会创建空 provider 的 LLMService。

### 8.3 判断

StoryForge3 是两段式：

1. 从 CC-Switch 导入到项目本地；
2. 运行时从项目本地配置读取 active provider。

因此导入失败的关键不只是“能否读取 CC-Switch DB”，还包括：

- 是否写入 `providers.json`；
- 写入路径是否和运行时读取路径一致；
- active provider 是否被设置；
- provider 是否 `enabled=true`；
- api_key 是否未被错误脱敏覆盖。

---

## 9. 火山 Coding Plan 路由差异

### 9.1 Auto-news2 旧逻辑

Auto-news2 会把以下路径当作兼容后缀剥离：

```text
/api/coding
/coding
```

### 9.2 StoryForge3 当前逻辑

StoryForge3 明确注释：

```python
# "/api/coding" and "/coding" intentionally NOT stripped
# Volcano Engine Coding Plan uses /api/coding as a real path prefix
```

### 9.3 判断

如果旧方案照搬 Auto-news2，则火山 endpoint 可能从：

```text
https://ark.cn-beijing.volces.com/api/coding
```

被错误剥离为：

```text
https://ark.cn-beijing.volces.com
```

最终构造出错误接口：

```text
https://ark.cn-beijing.volces.com/v1/messages
```

而正确路径应保留：

```text
https://ark.cn-beijing.volces.com/api/coding/v1/messages
```

这很可能是早期方案失败的关键因素之一。

---

## 10. 废弃 reader 的误导风险

StoryForge3 仍保留一个废弃文件：

```text
src/storyforge3/llm/ccswitch_reader.py
```

其注释说明：

```python
Deprecated settings.json reader retained for compatibility.
New code uses CCSwitchDBReader plus project-local providers.json instead.
```

但该旧 reader 中仍然出现：

```python
ccswitch_settings_path
ccswitch_db_path
ccswitch_app_type
```

如果实现方案误参考该旧 reader，就会与当前新架构不一致。

当前应以以下文件为准：

- `ccswitch_db_reader.py`
- `provider_config.py`
- `api/routes/providers.py`
- `llm/factory.py`
- `llm/llm_service.py`

---

## 11. 关键失败因素优先级

### P0：Provider 本地配置未落盘或落到错误目录

证据：当前未发现 `.storyforge3/providers.json`。

影响：

```text
导入成功但运行时读不到 active provider。
```

建议：

- 将 `providers_config_dir` 改成项目根目录下的绝对路径；
- 在设置页显示当前 provider 配置绝对路径；
- 启动日志打印 resolved providers.json path。

---

### P0：`.env.example` 与实际配置不一致

证据：`.env.example` 写了 `CCSWITCH_DB_PATH`，但配置类没有字段。

影响：

```text
用户以为配置了 CC-Switch DB 路径，实际被忽略。
```

建议：

- 增加 `ccswitch_db_path` 配置字段；
- 或删除无效配置项，统一说明只读默认 home 路径。

---

### P0：前端响应结构不匹配

证据：Auto-news2 raw response，StoryForge3 envelope response。

影响：

```text
前端列表为空 / 导入无反馈 / active provider 不显示。
```

建议：

- 检查前端是否统一读取 `response.data`；
- 增加 `available -> import -> list -> active -> verify` 集成测试。

---

### P1：火山 `/api/coding` 被错误剥离

影响：

```text
导入成功但 verify/generate 访问错误 endpoint。
```

建议：

- 保留 StoryForge3 当前不剥离 `/api/coding` 的实现；
- 增加火山 Coding Plan 路由测试。

---

### P1：无 key provider 被显示或导入

影响：

```text
用户选中 official/empty provider，导入后无法启用。
```

建议：

- UI 禁用 `has_api_key=false`；
- import 后如果没有 keyed provider，应返回明确错误。

---

## 12. 建议排查步骤

### Step 1：确认 provider 配置实际路径

检查：

```text
D:\python\Novel\.storyforge3\providers.json
D:\python\Novel\storyforge3\.storyforge3\providers.json
Tauri sidecar 工作目录下的 .storyforge3\providers.json
```

### Step 2：打印启动环境

后端启动时打印：

```text
cwd
providers_config_dir
resolved providers.json path
ccswitch db path
```

### Step 3：调用 API 链路

依次验证：

```http
GET /providers/available
POST /providers/import
GET /providers
PUT /providers/active
POST /providers/{provider_key}/verify
GET /providers/health
```

### Step 4：检查本地 providers.json

重点字段：

```json
{
  "active_provider_key": "...",
  "providers": [
    {
      "provider_key": "...",
      "enabled": true,
      "api_key": "真实 key，不应是 ****",
      "cc_api_format": "...",
      "cc_endpoint_candidates": [],
      "cc_last_verified_endpoint": "...",
      "cc_last_verified_format": "...",
      "cc_last_verified_model": "..."
    }
  ]
}
```

### Step 5：重点验证火山 endpoint

确认最终请求路径保留：

```text
/api/coding
```

正确示例：

```text
https://ark.cn-beijing.volces.com/api/coding/v1/messages
```

---

## 13. 修复建议

### 13.1 配置路径收口

建议将 provider 配置路径从相对 cwd 改为明确路径。

优先方案：

```text
storyforge3/.storyforge3/providers.json
```

或用户目录：

```text
%APPDATA%/StoryForge3/providers.json
```

至少应在 UI 和日志中显示最终路径。

### 13.2 配置字段收口

新增：

```python
ccswitch_db_path: str = ""
```

传入：

```python
ProviderConfigManager(..., ccswitch_db_path=Path(config.ccswitch_db_path))
```

若不打算支持自定义路径，则删除 `.env.example` 中相关字段。

### 13.3 前端协议收口

统一封装 StoryForge3 API envelope：

```ts
const data = response.data
```

不要复用 Auto-news2 的 raw response 读取方式。

### 13.4 路由测试补强

增加测试：

- 火山 `/api/coding` 不被剥离；
- `anthropic` 拼接 `/v1/messages`；
- `openai_responses` 拼接 `/v1/responses`；
- `isFullUrl=true` 时不拼接；
- verified endpoint 优先。

### 13.5 导入后自动验证

导入成功后建议自动触发 verify，或至少提示用户必须验证。

verify 成功后写回：

```text
cc_last_verified_endpoint
cc_last_verified_format
cc_last_verified_model
cc_probe_status=verified
```

---

## 14. 最终判断

Auto-news2 的 CC-Switch 方案不能原样迁移到 StoryForge3。两者最大差异在于：

```text
Auto-news2 = 固定项目 state/config + OpenAI SDK
StoryForge3 = 本地 providers.json + 自定义 httpx 多协议路由
```

当前导入失败最可能由以下组合导致：

1. `providers.json` 路径不稳定或未生成；
2. `.env.example` 中的 CC-Switch 路径配置实际无效；
3. 前端响应结构未适配 StoryForge3 envelope；
4. 旧路由规则错误剥离火山 `/api/coding`；
5. 导入了无 key provider 或导入后未设置 active provider。

最终建议：

> 先固定 provider 配置路径和调试信息，再核对前端 envelope 读取，最后验证火山 `/api/coding` endpoint。不要继续按 Auto-news2 的旧方案直接套用。StoryForge3 当前架构更强，但配置路径与环境变量收口不足，是导入失败的最核心风险。
