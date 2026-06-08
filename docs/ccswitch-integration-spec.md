# CC-Switch 中转站集成 — LLM 多端点多协议容错调用 功能规格

> 此文档是给 Codex 的完整实现规格，无需参考源码即可实现。

## 一、背景

CC-Switch 是一个本地桌面应用，用于管理多个 LLM API 中转站（Relay/Proxy）配置。它的数据存储在 SQLite 文件 `~/.cc-switch/cc-switch.db` 中。我们的项目需要从这个数据库读取中转站配置，然后在调用 LLM 时自动在多个端点、多种协议格式之间容错切换。

**核心原则：CC-Switch 是只读配置源，项目永远不修改 CC-Switch 的任何文件（settings.json / cc-switch.db）。项目内自行管理 provider 选择。**

## 二、核心概念

| 概念 | 含义 |
|------|------|
| Provider（服务商） | 一个 LLM 配置单元，包含 base_url、api_key、model_id |
| Endpoint（端点） | 一个完整的 API URL，如 `https://relay.example.com/v1/chat/completions` |
| Endpoint Candidate（端点候选） | 一个 Provider 可能有多个可用的中转 URL，组成候选列表 |
| API Format（协议格式） | 四种：openai_chat、openai_responses、anthropic、gemini_native |
| Route（路由） | 一个 `(endpoint, api_format, model_id)` 三元组，代表一次具体的调用方式 |
| Auto Select（自动探测） | 为 true 时，对同一个端点 URL 尝试多种协议格式 |

## 三、模块划分

共三个模块，按依赖顺序：模块 A → 模块 B → 模块 C

---

### 模块 A：CC-Switch 数据库读取器

**职责**：从 `~/.cc-switch/cc-switch.db`（SQLite）读取 provider 配置并标准化。

#### 数据库表结构（只读，不写入）

```sql
-- 服务商主表
providers (
  id TEXT,
  app_type TEXT,          -- 'claude' | 'codex' | 'gemini'
  name TEXT,
  settings_config TEXT,   -- JSON 字符串
  category TEXT,
  meta TEXT,              -- JSON 字符串
  is_current INTEGER,
  sort_index INTEGER,
  created_at TEXT
)

-- 中转端点表
provider_endpoints (
  id INTEGER,
  provider_id TEXT,
  app_type TEXT,
  url TEXT,
  added_at TEXT
)

-- 健康状态表
provider_health (
  provider_id TEXT,
  app_type TEXT,
  is_healthy INTEGER,
  consecutive_failures INTEGER,
  last_error TEXT
)
```

#### 按 app_type 提取配置的规则

**claude 类型**：从 `settings_config.env` 中读：
- `ANTHROPIC_BASE_URL` → base_url
- `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_API_KEY` → api_key
- `ANTHROPIC_MODEL` → model_id
- 默认协议格式：`anthropic`

**codex 类型**：从 `settings_config` 中读：
- `settings_config.auth.OPENAI_API_KEY` → api_key
- `settings_config.config` 是 TOML 文本，解析后取 `base_url` 和 `model`
- TOML 中如果有 `model_providers` 段，检查 `wire_api`：`"responses"` → `openai_responses`，`"chat"` → `openai_chat`
- 默认协议格式：`openai_responses`

**gemini 类型**：从 `settings_config.env` 中读：
- `GOOGLE_GEMINI_BASE_URL` → base_url
- `GEMINI_API_KEY` → api_key
- `GEMINI_MODEL` → model_id
- 默认协议格式：`gemini_native`

#### 端点候选列表的构建（去重保序）

```
endpoint_candidates = provider_endpoints 表中该 provider 的 url 列表
                     + [base_url]（如果不为空）
                     + [usage_base_url]（从 meta.usage_script.baseUrl 取，如果不为空）
```

#### meta JSON 中与中转相关的字段

```json
{
  "apiFormat": "openai_chat | openai_responses | anthropic | gemini_native | null",
  "isFullUrl": true | false,
  "endpointAutoSelect": true | false
}
```

#### 输出格式（每个 provider 一个 dict）

```python
{
    "id": "cc-{provider.id}",           # 加 cc- 前缀
    "label": provider.name,
    "provider_key": "cc-{provider.id}",
    "base_url": "提取到的 base_url",
    "api_key": "提取到的 api_key",
    "model_id": "提取到的 model_id",
    "enabled": False,                    # 默认不启用，需要用户手动导入
    "source": "cc-switch",

    # 中转站核心字段
    "cc_app_type": "claude | codex | gemini",
    "cc_api_format": "推断出的协议格式",
    "cc_is_full_url": bool | None,
    "cc_endpoint_auto_select": bool | None,
    "cc_endpoint_candidates": ["url1", "url2", ...],
    "cc_base_url_raw": "原始 base_url",
    "cc_usage_base_url": "usage 跟踪端点 | None",

    # 验证状态（初始为空，测试连接后填充）
    "cc_last_verified_endpoint": None,
    "cc_last_verified_format": None,
    "cc_last_verified_model": None,
    "cc_probe_status": None,
    "cc_probe_message": None,

    # 健康状态
    "cc_health": {
        "is_healthy": True/False,
        "consecutive_failures": 0,
        "last_error": None
    } | None
}
```

#### 连接 SQLite 的注意事项

- 使用只读模式：`sqlite3.connect(f"file:{db_path}?mode=ro&nolock=1", uri=True)`
- 用 `sqlite3.Row` 作为 `row_factory` 方便按列名访问
- 异常时返回空列表 `[]`，不抛错

---

### 模块 B：配置管理

**职责**：将 CC-Switch 读取的 provider 列表导入到项目的持久化配置中，并在运行时构建 LLMService 所需的 provider/tasks 配置。

#### 导入逻辑

1. 用户从前端选择要导入的 provider ID 列表
2. 从 CC-Switch 数据库读取完整 provider 列表
3. 按 ID 过滤出选中的 provider
4. 与项目中已有的 profile 列表合并：
   - 已存在的 profile（按 id 匹配）：用新值覆盖，但保护已有 api_key（如果新值是脱敏的 `"****..."` 则保留旧值）
   - 不存在的新 profile：直接加入
5. 有 api_key 的 profile 标记 `enabled=True`
6. 自动选择第一个有 key 的 profile 作为当前活跃 profile
7. 持久化写入项目配置文件

#### 构建运行时 provider 的函数（profile → provider）

```python
def build_provider_from_profile(profile: dict) -> dict:
    return {
        "key": profile["provider_key"],
        "label": profile["label"],
        "base_url": profile["base_url"],
        "api_key": profile["api_key"],
        "model_id": profile["model_id"],
        "enabled": bool(profile.get("enabled") and profile.get("api_key")),
        "source": profile.get("source"),

        # 以下 cc_* 字段必须原样透传
        "cc_app_type": profile.get("cc_app_type"),
        "cc_api_format": profile.get("cc_api_format"),
        "cc_is_full_url": profile.get("cc_is_full_url"),
        "cc_endpoint_auto_select": profile.get("cc_endpoint_auto_select"),
        "cc_endpoint_candidates": list(profile.get("cc_endpoint_candidates", [])),
        "cc_base_url_raw": profile.get("cc_base_url_raw"),
        "cc_usage_base_url": profile.get("cc_usage_base_url"),
        "cc_last_verified_endpoint": profile.get("cc_last_verified_endpoint"),
        "cc_last_verified_format": profile.get("cc_last_verified_format"),
        "cc_last_verified_model": profile.get("cc_last_verified_model"),
    }
```

#### 测试连接后的状态回写

测试成功后，将验证结果写回 profile 持久化：

```python
profile["cc_last_verified_endpoint"] = result["resolved_endpoint"]
profile["cc_last_verified_format"] = result["resolved_format"]
profile["cc_last_verified_model"] = result["resolved_model"]
profile["cc_probe_status"] = "verified"
profile["cc_probe_message"] = "已验证，可用于稿件生成"
```

---

### 模块 C：LLM 服务 — 多端点多协议容错调用（核心）

**职责**：接收一组 provider 配置，构建所有可能的路由候选，按优先级逐个尝试调用，直到成功或全部失败。

#### C1. 端点 URL 拼接规则

已知需要去除的后缀（兼容性后缀，中转站特有）：

```
/api/claudecode, /api/anthropic, /apps/anthropic, /api/coding,
/claudecode, /anthropic, /step_plan, /coding, /claude
```

已知 API 终端路径：

```
/v1/chat/completions, /chat/completions,
/v1/responses, /responses,
/v1/messages, /messages
```

按协议拼接完整端点 URL：

| 协议 | 拼接规则 |
|------|----------|
| openai_chat | base + `/v1/chat/completions`（如果 base 已以 `/v1` 结尾则直接加 `/chat/completions`） |
| openai_responses | base + `/v1/responses`（同理） |
| anthropic | base + `/v1/messages`（同理） |
| gemini_native | base + `/v1beta/models/{model}:generateContent` |
| is_full_url=true | 直接使用 base_url，不再拼接 |

#### C2. 路由候选构建 — `_build_route_candidates()`

输入：一个 provider dict（含 `cc_*` 字段）

```
1. 确定 declared_format = cc_api_format（或根据 app_type 推断默认值）
2. 确定 verified_endpoint = cc_last_verified_endpoint（如果有）

3. 收集原始端点候选（去重保序）：
   cc_endpoint_candidates 列表中的每一个
   + cc_base_url_raw
   + cc_usage_base_url
   + base_url

4. 确定要尝试的协议格式列表：
   如果 cc_endpoint_auto_select != False 且不是 gemini_native：
     formats = [declared_format] + [其他三种非 gemini 格式]
   否则：
     formats = [declared_format]

5. 构建路由列表：
   a. 如果有 verified_endpoint 且本次优先验证过的：
      添加 (verified_endpoint, verified_format, verified_model) → 标记 verified=True
   b. 对每个原始端点候选 × 每种协议格式：
      调用拼接函数生成完整 endpoint
      添加 (endpoint, format, model_id) → 标记 verified=False

6. 去重（按 endpoint+format+model 三元组去重）

7. 返回有序路由列表
```

**关键**：verified 路由排最前面，确保上次成功过的端点优先使用。

#### C3. 容错调用循环 — `_try_provider_routes()`

```python
last_error = None
for route in _build_route_candidates(provider, prefer_verified=True):
    try:
        result = _invoke_route(provider, route, messages, ...)
        return result       # 成功立即返回
    except LLMRouteError as e:
        last_error = e
        log.warning("路由失败: format=%s endpoint=%s reason=%s", ...)
        continue            # 失败，尝试下一个路由

# 全部失败
raise last_error or "未找到可用的请求端点"
```

#### C4. 四种协议的具体调用方式

**openai_chat**：使用 OpenAI SDK

```python
client = OpenAI(base_url=从endpoint提取的base, api_key=api_key, timeout=timeout)
response = client.chat.completions.create(
    model=model_id, messages=messages,
    temperature=temperature, max_tokens=max_tokens
)
content = response.choices[0].message.content
```

**openai_responses**：使用 OpenAI SDK

```python
client = OpenAI(base_url=从endpoint提取的base, api_key=api_key, timeout=timeout)
response = client.responses.create(
    model=model_id, input=input_text,
    instructions=system_text,
    temperature=temperature, max_output_tokens=max_tokens
)
content = response.output_text  # 或从 response.output[].content[].text 拼接
```

**anthropic**：原生 HTTP POST

```python
POST endpoint_url
Headers:
  x-api-key: api_key
  Authorization: Bearer api_key
  anthropic-version: 2023-06-01
Body:
  {"model": model_id, "max_tokens": ..., "messages": [...], "system": "..."}

content = response["content"][0]["text"]
```

**gemini_native**：原生 HTTP POST

```python
POST endpoint_url + "?key=" + url_encode(api_key)
Body:
  {"contents": [{"parts": [{"text": prompt}]}],
   "generationConfig": {"temperature": ..., "maxOutputTokens": ...}}

content = response["candidates"][0]["content"]["parts"][0]["text"]
```

#### C5. 模型 ID 的回退策略

如果 provider 没有指定 model_id：

1. 先尝试用 `"default"` 作为模型 ID 发请求
2. 如果失败（模型不存在），尝试调用 `{base}/v1/models` 获取可用模型列表
3. 对获取到的模型列表按规则打分排序（优先级：Claude 4.x > GPT-5 > Gemini 2.5 > GLM-5 > DeepSeek > 其他）
4. 取打分最高的模型依次尝试

#### C6. 错误分类

每次失败都需要分类（`probe_status`），用于前端展示和后续决策：

| probe_status | 含义 | 重试价值 |
|-------------|------|----------|
| verified | 调用成功 | — |
| html_homepage | 返回了 HTML 网页，不是 API | 无，跳到下一个端点 |
| auth_failed | HTTP 401/403，认证失败 | 无，跳到下一个端点 |
| protocol_mismatch | HTTP 404/405 或响应不是 JSON | 无，跳到下一个端点 |
| model_missing | 模型不存在 | 尝试其他模型 |
| connection_failed | 网络不通/超时 | 可重试 |
| rate_limited | HTTP 429 限流 | 可重试 |
| request_failed | 其他错误 | 视情况 |

判断返回的是 HTML 而非 API 响应的方法：检查响应文本前 200 字符是否以 `<!doctype html` 或 `<html` 开头。

#### C7. Provider 级别的 Fallback

在路由级容错之上，还有一层 Provider 级容错：

```python
try:
    result = _try_provider_routes(primary_provider, ...)
except LLMRouteError:
    if fallback_provider:
        result = _try_provider_routes(fallback_provider, ...)
    else:
        raise
```

## 四、从 OpenAI SDK 端点提取 base_url

OpenAI SDK 需要的是 base_url（不含终端路径），但我们的路由中 endpoint 是完整 URL。需要反向截断：

```python
# openai_chat: /v1/chat/completions 或 /chat/completions → 去掉后缀
# openai_responses: /v1/responses 或 /responses → 去掉后缀
```

## 五、实现要点总结

1. 所有 `cc_*` 字段在 profile → provider → LLMService 全链路透传，不能丢失
2. 路由构建的优先级：verified 端点 > endpoint_candidates 列表 > base_url
3. Auto select 开关：true 时同一端点尝试多种协议，false 时只用声明的协议
4. HTML 检测：中转站经常返回网页首页而非 JSON，必须检测
5. 去重保序：端点列表用 set 去重但保持插入顺序
6. API Key 安全：返回给前端时脱敏（`abcd****efgh`），写入时如果新值是脱敏的则保留旧值
7. provider health 字段目前只读不写，仅供前端展示
8. 连接 CC-Switch 数据库只用只读模式，`?mode=ro&nolock=1`
9. **永远不修改 CC-Switch 的 settings.json 或 cc-switch.db**
