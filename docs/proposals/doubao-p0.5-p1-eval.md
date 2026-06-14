
## 验收意见：P0.5 可以通过，P1 设计方向正确

我认同 ClaudeCode 对 P0.5 的完成判断：**这轮修复方向正确，且已经解决 dogfood 的核心阻塞：SSE 到不了浏览器、agent 触发时前端无反馈、刷新/未开始章节 404 噪音。**

我核对了 [architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md) 和关键实现，结论如下。

---

## 1. 对架构文档的理解

[architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md#L1-L6) 的核心判断是：

> 章节页不再是“六按钮控制面板”，而是“Run Viewer + 结果查看器”。

这个方向是正确的。它把系统模型从“用户手动按步骤”改成：

```text
Action/Run 负责执行
RunRecord/SSE 负责可观察性
前端负责观看、确认、介入
```

这与 agent-mode-first 完全一致。

文档里最关键的三个设计点是：

1. **章节产物状态 vs 运行实例状态拆分**，见 [architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md#L9-L37)。
2. **PipelineRunRecord 一等公民**，见 [architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md#L40-L79)。
3. **Run Viewer 取代六按钮布局**，见 [architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md#L102-L122)。

这三点都是 P1 的正确主线。

---

## 2. P0.5 实现核对

### 2.1 SSE named-event 修复：正确

[events.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/events.py#L18-L25) 现在返回：

```python
yield {"data": event}
```

没有再发 named event。  
这能让浏览器 `EventSource.onmessage` 正常收到事件，和 [usePipelineEvents.ts](file:///D:/python/Novel/storyforge3/web/src/hooks/usePipelineEvents.ts#L37-L48) 的实现匹配。

这个修复是关键根因修复，可以验收。

---

### 2.2 status 200 + empty：正确

[chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py#L519-L543) 在 `get_status()` 返回 `None` 时返回 `empty`，不再抛 404。

这对章节列表和未开始章节非常重要，避免 UI 控制台刷错。

可以验收。

---

### 2.3 分段流式正文：方向正确

[chunked_generator.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/chunked_generator.py#L20-L29) 增加 `on_chunk`，并在每段生成后回调，见 [chunked_generator.py](file:///D:/python/Novel/storyforge3/src/storyforge3/llm/chunked_generator.py#L74-L79)。

API 层在 [chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py#L353-L358) 发布 `llm:progress` 和 `llm:chunk`。

前端在 [ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L100-L108) 接收 `llm:progress` / `llm:chunk`，并把正文逐段追加到 `streamingText`。

这条链路已经闭合。

---

### 2.4 isBusy 解耦：正确但只是过渡

[ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L313-L315) 现在只要有 `pipelineStage` 就显示 `PipelineProgress`，不再依赖 mutation pending。

这解决了“后台/API/agent 触发时 UI 没反应”的核心痛点。

但它仍是 P0.5 过渡方案，因为刷新后运行中的 run 还不能通过 `GET /run` 恢复。这个要靠 P1 的 RunRecord。

---

### 2.5 导出章节锁定按钮：部分正确

[ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L75-L77) 定义 `isExported`，并在 [ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L280-L285) 禁用导出后的步骤按钮。

这能避免“已导出章节误触重跑”，可以作为 P0.5 接受。

但注意：当前只是“导出后全锁”，还不是完整门禁链。比如 `planned/drafted/audited` 各阶段仍主要靠 `isBusy || isExported`，不是根据状态精确禁用非法步骤。完整门禁应放到 P1。

---

## 3. 潜在问题

### 3.1 `GET /plan` 当前仍是 404 语义

架构文档和此前讨论倾向“未规划返回 null/empty”，但现在 [chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py#L328-L337) 仍然在无 plan 时抛 `chapter_not_found`。

前端 [useChapters.ts](file:///D:/python/Novel/storyforge3/web/src/hooks/useChapters.ts#L37-L49) 已经兜底把 not found 转成 `null`，所以用户侧问题不大。

但从 API 语义一致性看，P1 可以考虑改成：

```text
GET /plan -> 200 + data=null
```

不必 P0.5 追修。

---

### 3.2 错误信息仍 3 秒自动消失

[ChapterPipeline.tsx](file:///D:/python/Novel/storyforge3/web/src/components/chapters/ChapterPipeline.tsx#L141-L146) 和保存错误类似逻辑仍会自动清空错误。  
对 LLM 超时、provider 失败、审计失败这类长错误，不够友好。

建议 P1 Run Viewer 中改成：

- toast 短暂；
- 页面内错误持久保留；
- 提供“复制诊断信息”。

---

### 3.3 SSE 仍只有最近 100 条内存回放

[sse.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/sse.py#L41-L66) 使用 `_recent` 做内存回放。这个对 P0.5 足够，但不是可靠运行状态。

P1 必须转向：

```text
RunRecord 持久化为真相源
SSE 只是实时增量通道
```

否则刷新、后端重启、长任务断线仍有状态丢失风险。

---

### 3.4 当前 `POST /draft` 仍是同步长请求

[chapters.py](file:///D:/python/Novel/storyforge3/src/storyforge3/api/routes/chapters.py#L340-L364) 仍然在请求内等待完整 draft。SSE 能改善观感，但 HTTP 请求本身仍可能挂数分钟。

P0.5 可以接受；P1 应改为：

```text
POST /run -> 立即返回 run_id
后台任务执行
前端通过 SSE + GET /run 查看
```

---

## 4. 对 P1 的实施建议

我建议 P1 不要一开始就重写整个章节页，而是分三步推进。

### P1-1：RunRecord 后端最小闭环

先做：

- `RunStatus`
- `StageResult`
- `PipelineRunRecord`
- `current_run.json`
- `POST /run` 返回 `run_id`
- `GET /run`
- run 失败后 `resumable` 标记

目标：刷新后前端能知道“后台之前跑到哪”。

### P1-2：前端 Run Viewer 最小版

先替换“进度显示区”，不要立刻推翻整个章节页：

- `RunTrack`
- `LiveStage`
- `useRunRecord`
- `useRunEvents`
- 保留现有按钮，但降级为 ActionBar

目标：让用户看到 run 当前阶段、流式正文、失败点、等待确认点。

### P1-3：门禁规则统一

再做：

- `allowedActions()`
- 后端 guard
- 前端 disabled 镜像
- exported 后新版本入口
- blocking issue 禁止 approve
- truth 未提交禁止正式 export

目标：解决“按钮乱序、重复执行、已完成还重跑”。

---

## 5. 技术选型判断

### FastAPI BackgroundTasks / asyncio.Task：短期可行

文档 [architecture/run-state-and-viewer.md](file:///D:/python/Novel/storyforge3/docs/architecture/run-state-and-viewer.md#L126-L139) 建议 P1 用 FastAPI `BackgroundTasks` 或进程内 registry。  
我认为对当前单机 dogfood 是合理的。

但要明确限制：

- 后端重启时运行中任务会丢；
- 多 worker 不可靠；
- 不适合长期生产队列。

因此 P1 应把重启后行为定义为：

```text
RUNNING but process gone -> RESUMABLE / FAILED_RESUMABLE
```

不要假装能无损恢复。

---

## 6. 最终判断

### P0.5 验收

**可以通过。**

它解决了当前 dogfood 的实际阻塞：

- SSE 浏览器接收；
- 流式正文显示；
- agent 触发时前端有反馈；
- 未开始章节不再 404；
- 已导出章节避免误触。

### P1 方向

**强烈建议按架构文档推进。**

尤其是：

1. `PipelineRunRecord` 一等公民；
2. `Run Viewer + 结果查看器`；
3. 状态拆分；
4. SSE 作为实时通道，RunRecord 作为真相源；
5. Action 门禁统一。

---

## 一句话意见

ClaudeCode 这轮 P0.5 修得对，尤其 SSE named-event 是关键根因；接下来不要继续在六按钮面板上打补丁，应进入 P1：把 run 状态持久化并让章节页转为 Run Viewer。