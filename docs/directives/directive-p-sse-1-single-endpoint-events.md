# P-SSE-1：单端点补齐 SSE 事件（修复"前端无法实时跟随 agent"）

> 指令编号：P-SSE-1
> 下发时间：2026-06-17
> 下发人：ZCode（PM）
> 执行人：Codex
> 优先级：P0（生产阻塞项）

---

## 1. 问题陈述

agent 逐个调单端点（`/plan` → `/draft` → `/audit` → `/revise` → `/approve` → `/export`）生产章节时，前端无法实时反映进度。

**根因（已确认）**：单端点基本不发 SSE 事件。

后端 `src/storyforge3/api/routes/chapters.py` 当前 SSE 发布情况：

| 端点 | 行号 | SSE 发布 | 问题 |
|------|------|----------|------|
| `POST /{n}/draft` | 463-489 | ✅ `pipeline:start/progress/complete/error` + `llm:chunk` | 已完整 |
| `POST /{n}/revise` | 553-577 | ✅ `pipeline:start/complete/error` | 已完整 |
| `POST /{n}/run` | 660-672 | ✅ 完整 `run:*/stage:*` 事件链 | 不在本指令范围 |
| `POST /{n}/plan` | 422-431 | ❌ 不发 | **需补发** |
| `POST /{n}/re-plan` | 434-448 | ❌ 不发 | **需补发** |
| `POST /{n}/audit` | 492-504 | ❌ 不发 | **需补发** |
| `POST /{n}/re-audit` | 507-521 | ❌ 不发 | **需补发** |
| `POST /{n}/llm-audit` | 524+ | ❌ 不发 | **需补发** |
| `POST /{n}/normalize` | 535+ | ❌ 不发 | **需补发** |
| `POST /{n}/approve` | 601-610 | ❌ 不发 | **需补发** |
| `POST /{n}/export` | 613-626 | ❌ 不发 | **需补发** |

agent 逐个调时，前端只在 draft 和 revise 阶段能看到进度，其余 5 个阶段完全静默。

## 2. 目标

为所有缺少 SSE 的单端点补发 `pipeline:start` + `pipeline:complete`/`pipeline:error` 事件。

**复用已有辅助函数**（定义在 chapters.py:983-1098）：
- `_publish_start(sse_manager, book_id, chapter_no, stage=...)`
- `_publish_complete(sse_manager, book_id, chapter_no, stage=..., message=...)`
- `_publish_error(sse_manager, book_id, chapter_no, stage=..., error=...)`

## 3. 改动范围

**仅改一个文件**：`src/storyforge3/api/routes/chapters.py`

### 3.1 统一补发模式

每个端点在 service 调用前后补发事件。以 `/plan` 为例：

```python
@router.post("/{chapter_no}/plan")
async def plan_chapter(
    chapter_no: int,
    service: ChapterService = Depends(get_chapter_service),
) -> JsonResponse:
    _publish_start(sse_manager, service.book_id, chapter_no, stage="plan")
    try:
        intent = await service.plan(chapter_no)
        _publish_complete(sse_manager, service.book_id, chapter_no, stage="plan", message="规划完成")
        return _success(_intent_to_response(intent))
    except InvalidTransitionError as exc:
        _publish_error(sse_manager, service.book_id, chapter_no, stage="plan", error=str(exc))
        raise _state_error(str(exc))
    except Exception as exc:
        _publish_error(sse_manager, service.book_id, chapter_no, stage="plan", error=str(exc))
        raise
```

### 3.2 需要补发的端点清单

按上表所有标记"**需补发**"的端点，逐一补发。每个端点：
- 入口调 `_publish_start(stage=端点对应的阶段名)`
- 成功后调 `_publish_complete(stage=..., message="阶段名完成")`
- 失败时调 `_publish_error(stage=..., error=str(exc))`

阶段名映射：

| 端点 | stage 值 |
|------|----------|
| plan / re-plan | `"plan"` |
| audit / re-audit / llm-audit | `"audit"` |
| normalize | `"normalize"` |
| approve | `"approve"` |
| export | `"export"` |

### 3.3 book_id 获取

各端点已有 `service.book_id`（或等价引用）。确认每个端点的 book_id 来源，保持一致。

## 4. 不改的内容

- ❌ 不改 `POST /draft` 和 `POST /revise`（已有 SSE 事件）
- ❌ 不改 `POST /run` 全管线端点（已有独立事件链）
- ❌ 不改 Service 层代码
- ❌ 不改 SSEManager 本身
- ❌ 不改前端代码
- ❌ 不改 `_publish_*` 辅助函数的实现

## 5. 测试

新增 `tests/api/test_chapter_sse.py`：

验证每个补发的端点在成功和失败时都发布了对应事件。方案：

- 用 FastAPI TestClient 调端点（mock service 返回成功/抛异常）
- 在调用前后检查 `sse_manager._recent`（replay buffer）中是否有对应的 `pipeline:start` / `pipeline:complete` / `pipeline:error` 事件
- 或直接 mock `_publish_*` 函数，断言被调用

测试矩阵（每个端点 × 成功/失败）：

```
plan_success, plan_failure
re_plan_success, re_plan_failure
audit_success, audit_failure
re_audit_success, re_audit_failure
llm_audit_success, llm_audit_failure
normalize_success, normalize_failure
approve_success, approve_failure
export_success, export_failure
```

## 6. 验收标准

- [ ] `/plan`、`/re-plan`、`/audit`、`/re-audit`、`/llm-audit`、`/normalize`、`/approve`、`/export` 发布 `pipeline:start/complete` 事件
- [ ] 上述端点失败时发布 `pipeline:error` 事件
- [ ] `/draft`、`/revise` 行为不变
- [ ] `/run` 行为不变
- [ ] `tests/api/test_chapter_sse.py` 全通过
- [ ] 全量后端测试 ≥645 passed
- [ ] ruff clean

## 7. 风险

- 低风险：补发事件不影响端点逻辑，只是增加 SSE 副作用
- 注意：确认 `sse_manager` 的 import 在所有端点作用域内可见（当前 chapters.py 已 import）
