# Codex 指令：Phase 10A-2 — LLM 流式输出 + SSE 进度推送（后端）

> 发出日期：2026-06-11（v1.1 — 补充 dogfood 发现的管线级问题）
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 10A-1 完成（文档治理完成，覆盖率基线已记录）
> 战略来源：`docs/research/project-strategy.md` Phase A-2
> Dogfood 基线：《别打了》第 1 章，487 tests，ruff clean

## 任务概述

### 当前状态

- LLM 服务只支持非流式请求：`generate_text()` 用 `await client.post()` 等完整响应（`llm_service.py:276-281`）
- SSE 基础设施已存在：`SSEManager` + 5 种事件类型（`sse.py:12-21`），前端已有 `usePipelineEvents` hook
- `ChunkedGenerator`（`chunked_generator.py`）将长文分为多段生成，但全程静默，无进度信号
- 章节路由（`api/routes/chapters.py`）直接调用 `ChapterService` 方法，无进度回调
- 起草 2500 字章节需 2-5 分钟，用户只看到 loading 按钮，无任何反馈

### 🐕 Dogfood 发现的管线级问题（v1.1 新增）

Codex 首次真实 dogfood（《别打了》第 1 章）暴露了两个本指令必须覆盖的问题：

**问题 D1：ChunkedGenerator 在真实 Provider 下不可靠**
- `draft_chunk_plan` 超时后整个起草失败，Codex 被迫回退到单步 `ChapterService.draft()`
- 本书 target 2500 字 > 800 字阈值，必然触发 ChunkedGenerator
- 根因：`chunked_generator.py:19-33` 的 chunk_plan 调用使用默认超时，provider 延迟高时必超时
- **修复**：ChunkedGenerator 的 chunk_plan 调用需要独立超时控制 + 自动降级策略

**问题 D2：Truth 提取环节可被跳过**
- Dogfood 结果：`truth/` 目录为空，但状态已标记 `exported`
- `ChapterStateMachine` 允许 `force` 推进到任意状态，绕过 truth 提取
- 第 2 章起草时将没有任何前文事实检索，连续性无法保证
- **修复**：`run_full_pipeline()` 必须确保 truth 提取成功后才推进到 `exported`

### 本阶段交付

**为长耗时操作添加实时进度反馈 + 修复 dogfood 暴露的管线缺陷。** 五个核心改动：

1. **`LLMService.generate_text_stream()`**：新增流式生成方法，逐 token 返回
2. **`ChunkedGenerator` 进度回调 + 降级策略**：每完成一段推送进度；chunk_plan 超时时自动降级为单步生成
3. **章节路由进度推送**：draft/revise 操作期间通过 SSE 发布进度事件
4. **Truth 提取保障**：`run_full_pipeline()` 不允许跳过 truth 提取
5. **测试覆盖**：覆盖降级路径和 truth 保障路径

## 核心决策

### 为什么新增方法而非修改现有方法

`generate_text()` 被 14 个 Service 调用（world、character、volume、chapter、audit、truth、fanfic、short_story 等）。修改它的返回类型会导致全系统崩溃。新增 `generate_text_stream()` 让需要流式的调用方主动选择，不影响的调用方继续用原方法。

### 为什么只支持 openai_chat 和 openai_responses

当前活跃 provider 使用 OpenAI 兼容协议。Anthropic 和 Gemini 的 SSE 格式完全不同（`event: content_block_delta` vs `data: {"choices":[...]}`），实现成本高且当前无真实用户使用。后续按需添加。

### 为什么 ChunkedGenerator 用回调而非直接返回 AsyncIterator

ChunkedGenerator 的调用方（`ChapterService.draft()`）需要完整的最终文本，不需要逐段消费。回调模式让 ChunkedGenerator 内部循环不变，只在每个 chunk 完成时通知外部。比改为 AsyncIterator 的侵入性小得多。

## Part 1：LLM 流式输出

### 1.1 新增 `generate_text_stream()` 方法

在 `src/storyforge3/llm/llm_service.py` 的 `LLMService` 类中新增：

```python
from collections.abc import AsyncIterator

async def generate_text_stream(
    self,
    task_name: str,
    system_prompt: str,
    user_payload: dict,
    *,
    model: str | None = None,
    timeout: int | None = None,
    **kwargs,
) -> AsyncIterator[str]:
    """Stream text tokens from the LLM provider.

    Only supports openai_chat and openai_responses API formats.
    For other formats, falls back to non-streaming generate_text().
    Yields text chunks as they arrive.
    """
```

**实现要点**：

1. **构建 payload**：复用现有 `_payload()` 方法构建请求体
2. **选择 provider + route**：复用现有 `_try_with_provider_fallback` 逻辑中的 provider 选择，但只选择 `openai_chat` 或 `openai_responses` 格式的 route
3. **流式请求**：使用 `httpx.AsyncClient.stream("POST", ...)` 替代 `client.post()`
4. **解析 SSE 响应**：按 `\n\n` 分割，提取 `data: {...}` 行，解析 JSON，从 `choices[0].delta.content`（openai_chat）或 `output[*].content[*].text`（openai_responses）中提取文本
5. **错误处理**：
   - `httpx.TimeoutException` → 抛出 `LLMTimeoutError`
   - `httpx.ConnectError` → 抛出 `ProviderUnavailableError`
   - HTTP 429/502/503/504 → 回退到非流式 `generate_text()`（流式重试复杂，退化为非流式更可靠）
   - 无可用流式 route → 直接回退到非流式
6. **统计记录**：完成后调用 `_record_call()` 记录本次调用

**body 构建**：在 `_body_for_route()` 的基础上添加 `"stream": True`：

```python
def _streaming_body_for_route(self, route: Route, payload: dict) -> dict:
    body = self._body_for_route(route, payload)
    if route.api_format == "openai_chat":
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    elif route.api_format == "openai_responses":
        body["stream"] = True
    return body
```

### 1.2 流式响应解析

新增内部方法 `_parse_stream_chunks()`：

```python
async def _stream_response(
    self,
    provider: dict,
    route: Route,
    payload: dict,
    *,
    timeout: int | None,
) -> AsyncIterator[str]:
    """Yield text chunks from a streaming HTTP response."""
    body = self._streaming_body_for_route(route, payload)
    async with self._client(timeout=timeout) as client:
        async with client.stream(
            "POST",
            self._request_url(provider, route),
            headers=self._headers(provider, route),
            json=body,
        ) as response:
            if response.status_code != 200:
                # 非流式回退：读取完整响应并抛出常规错误
                await response.aread()
                ...
            buffer = ""
            async for raw_chunk in response.aiter_text():
                buffer += raw_chunk
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    text = self._extract_stream_delta(route.api_format, event_text)
                    if text is not None:
                        yield text
```

新增 `_extract_stream_delta()` 静态方法：

```python
@staticmethod
def _extract_stream_delta(api_format: str, event_text: str) -> str | None:
    """Extract text delta from a single SSE event."""
    for line in event_text.splitlines():
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str.strip() == "[DONE]":
            return None
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if api_format == "openai_chat":
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                content = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(content, str):
                    return content
        elif api_format == "openai_responses":
            # OpenAI Responses streaming format
            event_type = data.get("type")
            if event_type == "response.output_text.delta":
                delta = data.get("delta")
                if isinstance(delta, str):
                    return delta
    return None
```

### 1.3 保持向后兼容

- `generate_text()` **完全不改**，包括签名、行为、错误处理
- `generate_json()` **完全不改**
- `_post_with_retries()` **完全不改**
- 只有需要流式的调用方（目前只有 `ChapterService.draft()`）才使用新方法

## Part 2：ChunkedGenerator 进度回调

### 2.1 添加进度回调参数

修改 `src/storyforge3/llm/chunked_generator.py`：

```python
from collections.abc import Awaitable, Callable

class ChunkedGenerator:
    def __init__(
        self,
        service: Any,
        *,
        chunk_target_chars: int = 500,
        max_chunks: int = 6,
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> None:
        self.service = service
        self.chunk_target_chars = chunk_target_chars
        self.max_chunks = max_chunks
        self.on_progress = on_progress
```

### 2.2 在每段完成后触发回调

在 `generate()` 方法的循环中（当前第 36-56 行），在 `chunks.append(chunk.strip())` 之后添加：

```python
for index, scene in enumerate(scenes, start=1):
    chunk = await self.service.generate_text(...)
    if chunk.strip():
        chunks.append(chunk.strip())
        if self.on_progress:
            await self.on_progress(len(chunks), len(scenes))
```

### 2.3 向后兼容

- `on_progress` 参数默认 `None`，不传就不触发
- 现有所有调用方（只有 `ChapterService.draft()` 第 106-111 行）不传 `on_progress`，行为不变

### 2.4 🐕 ChunkedGenerator 降级策略（Dogfood D1 修复）

**问题**：`chunked_generator.py:19-33` 的 chunk_plan 调用在 provider 延迟高时超时，导致整个起草失败。Codex 在 dogfood 中被迫手动回退到单步 `generate_text()`。

**修复方案**：在 `generate()` 方法中为 chunk_plan 调用添加超时控制 + 自动降级：

```python
async def generate(self, task_name: str, system_prompt: str, outline: str, context: dict) -> str:
    target_chars = _positive_int(context.get("target_chars"), self.chunk_target_chars)
    chunk_count = max(1, min(self.max_chunks, math.floor((target_chars + self.chunk_target_chars / 2) / self.chunk_target_chars)))

    # 尝试 chunk_plan，超时时降级为单步生成
    try:
        plan = await self.service.generate_text(
            f"{task_name}_chunk_plan",
            system_prompt,
            {..., "task": "生成本章分段计划...",},
            model=context.get("model"),
            prompt_version=context.get("prompt_version"),
            max_output_tokens=800,
            timeout=60,  # chunk_plan 用独立短超时
        )
        scenes = _extract_scenes(plan, fallback=outline, limit=chunk_count)
    except (LLMTimeoutError, LLMProviderError):
        # chunk_plan 失败 → 降级为按 outline 直接分段生成
        scenes = _extract_scenes(outline, fallback=outline, limit=chunk_count)

    chunks: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        chunk = await self.service.generate_text(...)
        if chunk.strip():
            chunks.append(chunk.strip())
            if self.on_progress:
                await self.on_progress(len(chunks), len(scenes))
    return "\n\n".join(chunks)
```

**关键行为变更**：
- `chunk_plan` 调用设置 `timeout=60`（独立短超时，不影响后续 chunk 生成）
- `chunk_plan` 超时或 provider 错误时，降级为用 outline 直接分段，不报错
- chunk 生成本身仍然使用正常超时（由 LLMService 的 draft_timeout 控制）
- 降级事件通过 `on_progress` 发布（`message` 标注"分段计划超时，已降级为直接生成"）

## Part 3：SSE 进度事件扩展

### 3.1 扩展 PipelineEvent 事件类型

修改 `src/storyforge3/api/sse.py` 的 `PipelineEvent.type` 字面量：

```python
class PipelineEvent(BaseModel):
    type: Literal[
        "pipeline:start",
        "pipeline:progress",
        "pipeline:complete",
        "pipeline:error",
        "audit:complete",
        "llm:chunk",        # 新增：LLM 逐 token 文本块
        "llm:progress",     # 新增：ChunkedGenerator 段落进度
    ]
    book_id: str
    chapter_no: int
    stage: str | None = None
    message: str | None = None
    detail: dict | None = None
```

### 3.2 新增辅助函数

在 `sse.py` 中新增便捷构造函数：

```python
def make_chunk_event(book_id: str, chapter_no: int, text: str) -> PipelineEvent:
    """Create an llm:chunk event for streaming text."""
    return PipelineEvent(
        type="llm:chunk",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        detail={"text": text},
    )

def make_progress_event(book_id: str, chapter_no: int, completed: int, total: int) -> PipelineEvent:
    """Create an llm:progress event for chunk progress."""
    return PipelineEvent(
        type="llm:progress",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        message=f"正在生成第 {completed}/{total} 段",
        detail={"completed": completed, "total": total},
    )
```

## Part 4：章节路由集成

### 4.1 修改章节起草路由

修改 `src/storyforge3/api/routes/chapters.py` 的 draft 端点，在调用 `chapter_service.draft()` 前后发布 SSE 事件：

```python
from storyforge3.api.sse import sse_manager, make_progress_event

@router.post("/books/{book_id}/chapters/{chapter_no}/draft")
async def draft_chapter(book_id: str, chapter_no: int):
    await sse_manager.publish(PipelineEvent(
        type="pipeline:start",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        message="开始起草章节...",
    ))
    text = await chapter_service.draft(
        book_id,
        chapter_no,
        on_chunk_progress=lambda c, t: sse_manager.publish(
            make_progress_event(book_id, chapter_no, c, t)
        ),
    )
    await sse_manager.publish(PipelineEvent(
        type="pipeline:complete",
        book_id=book_id,
        chapter_no=chapter_no,
        stage="draft",
        message="章节起草完成",
    ))
    return ...
```

### 4.2 修改 ChapterService.draft() 签名

在 `src/storyforge3/services/chapter_service.py` 的 `draft()` 方法中新增可选的进度回调：

```python
async def draft(
    self,
    book_id: str,
    chapter_no: int,
    intent: ChapterIntent | None = None,
    *,
    on_chunk_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> str:
```

在调用 `ChunkedGenerator` 时传入回调（当前第 106-111 行）：

```python
if _should_chunk_draft(target_chars):
    text = await ChunkedGenerator(
        self.llm,
        on_progress=on_chunk_progress,
    ).generate(...)
```

### 4.3 修订路由也发布进度

对 revise 端点做类似处理：发布 `pipeline:start`（stage="revise"）和 `pipeline:complete` 事件。修订不使用 ChunkedGenerator，所以只有 start/complete 事件。

### 4.4 向后兼容

- `on_chunk_progress` 参数默认 `None`
- MCP tool 调用 `draft()` 时不传回调，行为不变
- `run_full_pipeline()` 不传回调（全流程有自己的 SSE 事件）

## Part 4.5：🐕 Truth 提取保障（Dogfood D2 修复）

**问题**：Dogfood 中 `truth/` 目录为空但状态已标记 `exported`。`ChapterStateMachine` 允许 `force` 推进绕过 truth 提取。第 2 章起草时将没有任何前文事实检索。

**修复方案**：在 `src/storyforge3/workflow.py` 的 `ChapterWorkflow.run()` 中，确保 truth 提取是 exported 前的必经步骤：

1. 在 `step_export()` 之前，验证 truth 提取已完成（检查 truth store 中是否有当前章节数据）
2. 如果 truth 提取未执行或失败，不推进到 exported 状态，而是返回错误
3. 错误信息应明确："Truth 提取未完成，无法导出。请重新运行 truth_extract 步骤。"

**实现要点**：
- 不修改 `ChapterStateMachine.force_needs_review()` 等现有方法——force 是合法的开发/调试手段
- 只在 `ChapterWorkflow.run()` 的正常流程中增加 truth 检查
- 允许 `ChapterService.approve()` 单独调用时跳过 truth 检查（人工审批路径）
- `run_full_pipeline()` 是唯一需要强制 truth 的路径

**测试**：
```python
# test_run_full_pipeline_requires_truth_before_export
#    Mock truth_store 为空，验证 run_full_pipeline 在 export 前失败并报错

# test_run_full_pipeline_succeeds_with_truth
#    Mock truth_store 有数据，验证正常完成
```

## Part 5：测试要求

### 5.1 LLM 流式输出测试

新增 `tests/test_api/test_llm_streaming.py`：

```python
# 1. test_generate_text_stream_yields_chunks
#    Mock httpx streaming response，验证 yield 了正确的文本块

# 2. test_generate_text_stream_openai_chat_format
#    提供标准 openai_chat SSE 格式的 mock 数据，验证 delta 解析正确

# 3. test_generate_text_stream_openai_responses_format
#    提供标准 openai_responses SSE 格式的 mock 数据

# 4. test_generate_text_stream_fallback_on_anthropic
#    当只有 anthropic route 可用时，回退到非流式 generate_text()

# 5. test_generate_text_stream_timeout_raises_error
#    Mock 超时，验证抛出 LLMTimeoutError

# 6. test_generate_text_stream_fallback_on_429
#    Mock 429 响应，验证回退到非流式
```

### 5.2 ChunkedGenerator 进度测试

新增到 `tests/test_llm/test_chunked_generator.py`（如果存在则追加）：

```python
# 7. test_chunked_generator_calls_on_progress
#    传入 mock on_progress 回调，验证每个 chunk 完成后调用一次

# 8. test_chunked_generator_no_progress_without_callback
#    不传 on_progress，验证行为与之前完全相同

# 9. 🐕 test_chunked_generator_fallback_on_plan_timeout
#    Mock chunk_plan 抛出 LLMTimeoutError，验证降级为用 outline 直接分段生成

# 10. 🐕 test_chunked_generator_fallback_on_plan_provider_error
#     Mock chunk_plan 抛出 LLMProviderError，验证降级行为

# 11. 🐕 test_chunked_generator_plan_succeeds_no_fallback
#     Mock chunk_plan 正常返回，验证不触发降级
```

### 5.3 SSE 进度事件测试

新增到 `tests/test_api/test_events.py`（如果存在则追加）：

```python
# 9. test_make_chunk_event_structure
#    验证 llm:chunk 事件结构正确

# 10. test_make_progress_event_structure
#     验证 llm:progress 事件结构正确

# 11. test_draft_publishes_sse_events
#     验证 draft 端点发布了 pipeline:start、llm:progress、pipeline:complete 事件
```

### 5.4 向后兼容测试

```python
# 14. test_generate_text_unchanged
#     验证现有 generate_text() 方法的测试全部通过（回归测试）

# 15. test_mcp_draft_no_progress_callback
#     验证 MCP tool 调用 draft 时不传 on_chunk_progress
```

### 5.5 🐕 Truth 提取保障测试

新增到 `tests/test_workflow/` 或 `tests/test_services/test_chapter_workflow.py`：

```python
# 16. test_run_full_pipeline_requires_truth_before_export
#     Mock truth_store 为空，验证 run_full_pipeline 在 export 前失败

# 17. test_run_full_pipeline_succeeds_with_truth
#     Mock truth_store 有数据，验证正常完成到 exported
```

## Part 6：借鉴来源

### 直接借鉴

| 借鉴内容 | 来源文件 | 借鉴方式 | 新写比例 |
|---------|---------|---------|---------|
| httpx streaming 用法 | httpx 官方文档 `AsyncClient.stream()` | 模式复用：标准 HTTP streaming 模式 | 50% |
| OpenAI SSE 格式解析 | OpenAI Chat Completions Streaming 文档 | 模式复用：标准 SSE delta 解析 | 40% |
| SSEManager 事件发布 | `src/storyforge3/api/sse.py` 已有 publish 模式 | 直接移植：复用现有 SSEManager | ≤20% |
| PipelineEvent 构造 | `sse.py:12-26` 已有的事件类型 | 骨架移植：新增两个 type 值 | 15% |

### 无直接来源说明

- `generate_text_stream()` 的完整实现：httpx streaming + SSE 解析 + provider fallback 组合：无现成来源，需新写。风险缓解：单元测试覆盖所有 SSE 格式分支。
- 新写比例约 50%。原因：流式输出是全新的基础设施，需要处理 SSE 解析、格式适配、错误回退等逻辑，但这些模式在 httpx 和 OpenAI 文档中有明确参考。

## 验收标准

### 功能检查

- [ ] `LLMService.generate_text_stream()` 方法存在，返回 `AsyncIterator[str]`
- [ ] 支持 `openai_chat` 和 `openai_responses` 两种格式的流式解析
- [ ] 不可用格式（anthropic/gemini）自动回退到非流式
- [ ] `ChunkedGenerator` 支持 `on_progress` 回调，每段完成后触发
- [ ] `PipelineEvent` 支持 `llm:chunk` 和 `llm:progress` 两种新事件类型
- [ ] `make_chunk_event()` 和 `make_progress_event()` 辅助函数存在
- [ ] 章节起草路由发布 `pipeline:start` → `llm:progress`(N次) → `pipeline:complete` 事件序列
- [ ] 修订路由发布 `pipeline:start` → `pipeline:complete` 事件序列
- [ ] 🐕 ChunkedGenerator chunk_plan 超时时自动降级为 outline 直接分段，不报错
- [ ] 🐕 `run_full_pipeline()` 在 truth 提取未完成时不推进到 exported

### 向后兼容

- [ ] `generate_text()` 方法签名和行为完全不变
- [ ] `generate_json()` 方法签名和行为完全不变
- [ ] 现有 487 后端测试全部通过，无退步
- [ ] MCP tool 调用 draft 时不传 on_chunk_progress，行为不变
- [ ] `run_full_pipeline()` 正常路径（truth 有数据）不受影响

### 测试覆盖

- [ ] ≥12 个新测试（流式输出 6 + 进度回调 2 + SSE 事件 3 + 兼容 2 + 降级 3 + Truth 保障 2）
- [ ] 每个 `generate_text_stream()` 的 SSE 格式分支有对应测试
- [ ] 回退路径有测试（anthropic 格式、429 错误、超时）

### 质量门禁

- [ ] `pytest tests/ -q` 全绿，无退步（基线 487 + 新增 ≥12 = ≥499）
- [ ] `ruff check .` clean
- [ ] `pnpm test` 全绿（基线 62，本指令不改前端）
- [ ] `pnpm build` 通过
- [ ] 无新 `TODO` / `FIXME` 残留

### 文档更新

- [ ] `CLAUDE.md` 更新：Phase 10A-2 完成记录 + 流式输出说明
- [ ] `docs/current.md` 更新：新增测试数 + 流式输出能力标记

## 估算工作量

| 文件 | 估算行数 | 说明 |
|------|---------|------|
| `src/storyforge3/llm/llm_service.py` | +120 行 | `generate_text_stream()` + `_stream_response()` + `_extract_stream_delta()` + `_streaming_body_for_route()` |
| `src/storyforge3/llm/chunked_generator.py` | +30 行 | `on_progress` 参数 + 回调调用 + 🐕 chunk_plan 降级策略 |
| `src/storyforge3/api/sse.py` | +25 行 | 新事件类型 + 辅助函数 |
| `src/storyforge3/services/chapter_service.py` | +8 行 | `on_chunk_progress` 参数透传 |
| `src/storyforge3/api/routes/chapters.py` | +20 行 | draft/revise 路由 SSE 事件发布 |
| `src/storyforge3/workflow.py` | +15 行 | 🐕 truth 提取保障逻辑 |
| 测试文件 | +280 行 | ≥12 个新测试（含降级和 truth 保障） |
| **合计** | **~500 行** | 以后端基础设施为主 |

## 不做的事（Out of Scope）

- ❌ 不修改前端代码（前端进度 UI 在 Phase 10A-3）
- ❌ 不修改 `generate_text()` 和 `generate_json()` 的现有行为
- ❌ 不支持 Anthropic / Gemini 格式的流式输出（后续按需添加）
- ❌ 不做 token 级实时推送（`llm:chunk` 事件定义了但本章不实现逐 token 推送到前端；Phase 10A-3 可按需启用）
- ❌ 不修改 MCP Server（MCP tool 不需要流式输出）
- ❌ 不修改 `pipeline_logger.py`（JSONL 日志保持现有逻辑）
- ❌ 不修改 `run_full_pipeline()` 的事件发布逻辑（只增加 truth 检查，不改事件）
