# P-SSE-2：单端点补发 stage:* 事件（让 RunTrack/LiveStage 响应 agent 调用）

> 指令编号：P-SSE-2
> 下发时间：2026-06-17
> 下发人：ZCode（PM）
> 执行人：Trae
> 优先级：P0（P-SSE-1 的收尾，修复"看不到进度"根因）

---

## 1. 问题陈述

P-SSE-1 让单端点发了 `pipeline:start/complete/error` 事件，但用户仍然看不到进度动画。

**根因（已确认）**：前端最显眼的两个组件 RunTrack（7阶段轨道）和 LiveStage（实时面板）只消费 `run:*/stage:*` 事件，不消费 `pipeline:*` 事件。

前端事件消费链路：

| 组件 | 数据来源 | 监听的事件 | 单端点是否触发 |
|------|----------|-----------|--------------|
| RunTrack（7阶段轨道） | `useRunRecord` → RunRecord | `run:*/stage:*` | ❌ 不触发 |
| LiveStage（实时面板） | `useRunRecord` → RunRecord | `run:*/stage:*` | ❌ 不触发 |
| PipelineProgress（小进度条） | `usePipelineEvents` → 本地 state | `pipeline:*` | ✅ 触发 |

单端点发 `pipeline:*` → 只有 PipelineProgress 响应（位置不显眼）。RunTrack 和 LiveStage 永远不响应。

## 2. 目标

**原生适配**：让后端单端点除了发 `pipeline:*` 事件（保留），同时补发 `stage:*` 事件。前端 `useRunEvents` 已经能处理 `stage:*`，无需改前端。

## 3. 改动范围

**仅改一个文件**：`src/storyforge3/api/routes/chapters.py`

### 3.1 复用已有辅助函数（需改签名）

P-SSE-1 已有的 stage 事件辅助函数（定义在 chapters.py:1070-1125），当前签名 `run_id: str`：

- `_publish_stage_start(book_id, chapter_no, run_id, stage, message)` — 发 `stage:start`
- `_publish_stage_complete(book_id, chapter_no, run_id, stage, detail)` — 发 `stage:complete`
- `_publish_stage_error(book_id, chapter_no, run_id, stage, message)` — 发 `stage:error`

**前置改动**：把这三个函数的 `run_id: str` 改为 `run_id: str | None`，这样单端点可以传 `None`。PipelineEvent.run_id 本身就是 `str | None`，sse.py 的 model_serializer 会 exclude None。

### 3.2 run_id 处理

单端点没有 RunRecord，所以没有真实 run_id。

**方案**：用 `None` 作为 run_id。

前端 `useRunEvents` 的 reducer 处理 `stage:start` 时：
```typescript
const runId = event.run_id ?? record.run_id;  // event.run_id 为 null → 用 record.run_id
```
如果 RunRecord 不存在，`createEventRunRecord` 会用 `event.run_id ?? ""` 创建。所以 `run_id=None` 是安全的。

确认后端 `_publish_stage_*` 函数的 `run_id` 参数是否接受 `None`（PipelineEvent 的 `run_id` 字段是 `str | None`，`model_serializer` 会 exclude None）。如果函数签名是 `run_id: str | None`，直接传 `None`。

### 3.3 每个端点的改动

在 P-SSE-1 已补发的 `_publish_start/complete/error`（`pipeline:*` 事件）基础上，**额外**补发 `_publish_stage_start/complete/error`（`stage:*` 事件）。

以 `/plan` 为例（P-SSE-1 已有的 + 新增的）：

```python
@router.post("/{chapter_no}/plan")
async def plan_chapter(...):
    await _guard_action(...)
    
    # P-SSE-1 已有：pipeline 事件
    await _publish_start(book_id, chapter_no, "plan", f"开始第 {chapter_no} 章规划")
    # P-SSE-2 新增：stage 事件（run_id=None）
    await _publish_stage_start(book_id, chapter_no, None, "plan", f"开始第 {chapter_no} 章规划")
    
    try:
        intent = await service.plan(book_id, chapter_no)
    except Exception as exc:
        await _publish_error(book_id, chapter_no, str(exc), "plan")
        await _publish_stage_error(book_id, chapter_no, None, "plan", str(exc))
        raise
    await _publish_complete(book_id, chapter_no, "plan", {"goal": intent.goal})
    await _publish_stage_complete(book_id, chapter_no, None, "plan", {"goal": intent.goal})
    return ok(_intent_to_response(intent))
```

需要补发 `stage:*` 事件的端点（与 P-SSE-1 相同的 8 个）：

| 端点 | stage 值 |
|------|----------|
| plan / re-plan | `"plan"` |
| audit / re-audit / llm-audit | `"audit"` |
| normalize | `"normalize"` |
| approve | `"approve"` |
| export | `"export"` |

### 3.4 不改的内容

- ❌ 不改前端代码
- ❌ 不改 SSEManager
- ❌ 不改 `/run` 端点
- ❌ 不改 `/draft` 和 `/revise`（它们发的是 `pipeline:*` + `llm:*`，不需要 stage 事件——因为 draft 阶段在 /run 内已经有 stage 事件了，单端点 draft 也有自己的 pipeline 事件链）
- ❌ 不删 P-SSE-1 已补发的 `pipeline:*` 事件（保留给 usePipelineEvents 的 toast）

## 4. 关于 /draft 和 /revise 的特殊处理

**decision**：/draft 和 /revise 也补发 `stage:*` 事件。

原因：agent 逐个调时，/draft 和 /revise 也是单端点调用，同样需要驱动 RunTrack/LiveStage。当前 /draft 和 /revise 只发 `pipeline:*` 事件。

改动：在 /draft 和 /revise 的 `_publish_start/complete/error` 调用旁，补发 `_publish_stage_start/complete/error`。

## 5. 测试

修改 `tests/api/test_chapter_sse.py`：

- 在现有的 `_assert_success_events` / `_assert_failure_events` 中，除了断言 `pipeline:start/complete/error`，增加断言 `stage:start/complete/error` 也被发布
- 或者新增 `_assert_stage_events` 辅助函数，检查 `stage:*` 事件序列

修改后的断言应该验证：每个端点调用后，`sse_manager._recent` 中同时包含 `pipeline:*` 和 `stage:*` 两套事件。

## 6. 验收标准

- [ ] `/plan`、`/re-plan`、`/audit`、`/re-audit`、`/llm-audit`、`/normalize`、`/approve`、`/export` 同时发布 `pipeline:*` 和 `stage:*` 事件
- [ ] `/draft` 和 `/revise` 也补发 `stage:*` 事件
- [ ] `stage:*` 事件的 `run_id` 为 `None`（不在事件 JSON 中出现）
- [ ] `stage:*` 事件的 `stage` 值正确（plan/audit/normalize/approve/export）
- [ ] 失败时同时发 `pipeline:error` 和 `stage:error`
- [ ] `tests/api/test_chapter_sse.py` 更新后全通过
- [ ] 全量后端测试 ≥660 passed
- [ ] ruff clean

## 7. 风险

- 低风险：补发 stage 事件不影响端点逻辑
- 注意：确认 `_publish_stage_*` 函数的 run_id 参数接受 None（PipelineEvent.run_id 是 Optional）
- 注意：前端 useRunEvents 收到没有 run:start 前导的 stage:start 时，会创建临时 RunRecord——这是设计行为，不需要改前端
