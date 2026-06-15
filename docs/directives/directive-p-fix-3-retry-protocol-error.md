# 指令 P-FIX-3：_post_with_retries 补 RemoteProtocolError 重试（provider 断连容错）

> 下发 Codex。前置：P-FIX-1 ✅、P-FIX-2 ✅、PROD-1b ch2 闭环 ✅。
> 触发：PROD-1b ch3 truth 提取连续失败——`httpx.RemoteProtocolError: Server disconnected without sending a response` 穿透 `_post_with_retries()` 的 except 链，直达 `TruthExtractionError`。脚本级重试 3 次全失败。根因：`_post_with_retries()` 只 catch `TimeoutException` 和 `ConnectError`，对同等瞬态的 `RemoteProtocolError` 无重试。

## 背景

### 现状

`llm_service.py:425-471` `_post_with_retries()` 的异常处理：

```python
try:
    async with self._client(timeout=timeout) as client:
        response = await client.post(...)
except httpx.TimeoutException:     # L441 — 直接 raise，不重试
    ...
    raise
except httpx.ConnectError as exc:  # L449 — 包装为 LLMRouteError("connection_failed")，不重试
    ...
    raise LLMRouteError(...)
```

**缺失**：`httpx.RemoteProtocolError`（HTTP/2 或 HTTP/1.1 协议层断连，如 `Server disconnected without sending a response`）不在 catch 链中。

### 实际影响

- PROD-1b ch3 truth 提取连续 3 次触发 `RemoteProtocolError` → 每次都穿透到 `TruthExtractionError` → 脚本级重试重建完整调用链 → 浪费时间且成功率低。
- 火山引擎 ark-code-latest 对长耗时的 truth_extract 请求（400-600s）在网络不稳定时容易触发协议层断连，属于**瞬态错误**，应该 route 内短退避重试。

### Codex 建议（PM 采纳）

> 在 `_post_with_retries()` 中 catch `httpx.RemoteProtocolError`，按 502/503/504 同级重试，最后包装为 `LLMRouteError("server_disconnected", ...)`。

PM 分析：
- `RemoteProtocolError` 与 5xx 同属瞬态服务端错误，重试策略应一致（指数退避 + jitter）。
- `TimeoutException` 不重试是合理的（长请求超时重试大概率再超时）。
- `ConnectError` 不重试也是合理的（连接失败通常是持久的 DNS/网络问题）。
- **但 `RemoteProtocolError` 不同**：连接已建立、请求已发送、服务端在响应过程中断连——这是瞬态的，重试合理。

## 任务

### 1. 修改 `_post_with_retries()`（`src/storyforge3/llm/llm_service.py`）

在 L449 `except httpx.ConnectError` 之后、L456 `self._diag("request response ...)` 之前，增加：

```python
except httpx.RemoteProtocolError as exc:
    self._diag(
        "request protocol_error "
        f"attempt={attempt + 1}/{attempts} format={route.api_format} "
        f"elapsed={time.perf_counter() - request_started:.2f}s"
    )
    if attempt < attempts - 1:
        await self._retry_sleep(attempt, jitter=0.5)
        continue
    raise LLMRouteError("server_disconnected", f"server disconnected: {exc}", route=route) from exc
```

**行为**：
- 非最后一次 attempt：指数退避重试（与 502/503/504 同级 jitter=0.5）
- 最后一次 attempt：包装为 `LLMRouteError("server_disconnected", ...)` 抛出，与既有错误处理链一致

### 2. 补测试（`tests/` 中既有 llm 测试文件）

**测试 1：`RemoteProtocolError` 重试成功**
- mock `client.post` 前两次抛 `httpx.RemoteProtocolError("Server disconnected")`，第三次返回 200 JSON `{"choices": [{"message": {"content": "ok"}}]}`
- 断言最终返回成功 response
- 断言 `_retry_sleep` 被调用 2 次

**测试 2：`RemoteProtocolError` 全部失败**
- mock `client.post` 全部 5 次抛 `httpx.RemoteProtocolError`
- 断言抛 `LLMRouteError` 且 `probe_status == "server_disconnected"`

**测试 3：`TimeoutException` 仍不重试**（回归）
- mock `client.post` 抛 `httpx.TimeoutException("timeout")`
- 断言直接 raise，不调用 `_retry_sleep`

### 3. 不改动的部分（红线）

- **`TimeoutException` 不加重试**——长请求超时重试无意义。
- **`ConnectError` 不加重试**——连接层失败通常是持久的。
- **不改动 retry 次数上限**（保持 5 次，gemini_native 4 次）。
- **不改动 `classify_response_error` 或响应处理逻辑**。
- **不动《别打了》数据**。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| 502/503/504 重试模式 | `llm_service.py:464-466` | **直接复用**（同 `_retry_sleep(attempt, jitter=0.5) + continue`） |
| ConnectError 处理模式 | `llm_service.py:449-455` | **模式复用**（diagnostics + 条件重试/包装 LLMRouteError） |
| `LLMRouteError` 错误类 | `llm_service.py:63-67` | **直接复用**（新 probe_status="server_disconnected"） |
| `_retry_sleep` | `llm_service.py:642-648` | **直接复用** |

**新写比例**：约 **5%**。一个 except 分支 + 2-3 个测试函数。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥597 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
```

手动：
- 确认 `TimeoutException` 仍直接 raise（回归）。
- 确认 `ConnectError` 仍包装为 `LLMRouteError("connection_failed")`（回归）。

## 必须覆盖的测试

- `RemoteProtocolError` 重试成功（前 2 次失败，第 3 次 200）。
- `RemoteProtocolError` 全部失败（5 次，最终抛 `LLMRouteError`，probe_status="server_disconnected"）。
- `TimeoutException` 不重试（回归）。
- `ConnectError` 包装为 `LLMRouteError("connection_failed")`（回归）。

## 红线

- ❌ 不给 `TimeoutException` 加重试——长请求超时重试无意义。
- ❌ 不给 `ConnectError` 加重试——连接层失败通常是持久问题。
- ❌ 不改动重试次数上限。
- ❌ 不改动响应处理逻辑。
- ❌ 不动《别打了》数据。
- ❌ 不做前端改动。

## 回报

- commit hash（建议 `fix(llm): retry RemoteProtocolError in _post_with_retries`）
- pytest + ruff 结果
- 新增测试用例列表

## 后续

P-FIX-3 验收通过后，立即重跑 PROD-1b ch3 closeout（`POST /{n}/approve` → truth 提取 → export）。届时 `_post_with_retries` 内置重试应能覆盖火山 provider 的瞬态断连，ch3 有望一次通过。

## Out of Scope

- ❌ ch3 closeout 重跑（P-FIX-3 验收后单独执行）。
- ❌ ch4 生产（PROD-2，ch3 exported 后启动）。
- ❌ truth 提取 prompt 优化（JSON 格式不稳定是独立问题）。
- ❌ 前端改动。
