# 指令 P-FIX-2：修复 pipeline resume_from 逻辑 + NEEDS_REVIEW 门禁缺失

> 下发 Codex。前置：P1-3（门禁）✅、P-DISCARD-1（discard）✅。
> 触发：PROD-1 生产审计发现——`_stages_from()` 在 resume 时跳过失败阶段本身，导致 resume 后跳过重试直接执行后续阶段；同时 `gating.py` 对 NEEDS_REVIEW 返回空集合，手动编辑后的章节无任何可执行动作。属 PM 缺陷全景报告 Bug B（P1）+ NEEDS_REVIEW 门禁缺失。

## 背景

### Bug B：resume_from 指向失败阶段但 _stages_from 跳过它

**调用链**：
1. Full pipeline 运行到 truth 阶段时 `TruthExtractionError` 抛出。
2. `chapters.py:785-787` 捕获异常：`registry.mark_stage_failed(run_id, "truth", ...)`。
3. `run_registry.py:138` `mark_stage_failed` 设置 `resume_from=stage`（即 `"truth"`）。
4. 用户/agent 调用 `POST /{chapter_no}/run/{run_id}/resume`。
5. `chapters.py:667` `_run_full_pipeline_background(..., resume_from=record.resume_from)` → `resume_from="truth"`。
6. `chapters.py:820-825` `_stages_from("truth", target_stages)`：
   ```python
   def _stages_from(resume_from: str | None, target_stages: list[str]) -> list[str]:
       if resume_from is None:
           return list(target_stages)
       if resume_from not in target_stages:
           return list(target_stages)
       return target_stages[target_stages.index(resume_from) + 1 :]  # ← 跳过 truth！
   ```
   返回 `["export"]`（truth 的下一个）→ **跳过 truth 重试** → export 必然失败（无 truth）。

**同样影响 `fail()` 方法**：`run_registry.py:163` `resume_from=resume_from or record.current_stage`，如果 `current_stage="truth"`，同样的跳过。

**正确行为**：resume 应从**失败阶段本身**重新开始（inclusive），而非从失败阶段的下一个开始。

### NEEDS_REVIEW 门禁缺失

- `models.py:23` `NEEDS_REVIEW = "needs_review"` 存在于枚举中。
- `machine.py:24` TRANSITIONS 定义了 NEEDS_REVIEW 可回到 `{PLANNED, DRAFTED, EMPTY}`。
- `chapter_service.py:290` `update_text()` 手动编辑后调用 `force_needs_review()`。
- `gating.py` 最后两行对 NEEDS_REVIEW 返回 `frozenset()` → **编辑后无任何可执行动作**。
- 用户手动编辑章节正文后，状态变为 NEEDS_REVIEW，但无法通过 API 重新 audit/approve/plan → **章节卡死**。

## 任务

### 1. 修复 `_stages_from()`（`src/storyforge3/api/routes/chapters.py`）

将 resume 改为 **inclusive**（从失败阶段重新开始）：

```python
def _stages_from(resume_from: str | None, target_stages: list[str]) -> list[str]:
    if resume_from is None:
        return list(target_stages)
    if resume_from not in target_stages:
        return list(target_stages)
    return target_stages[target_stages.index(resume_from):]  # inclusive：从失败阶段重新开始
```

**改动**：`target_stages.index(resume_from) + 1` → `target_stages.index(resume_from)`。

这样 `resume_from="truth"` → 返回 `["truth", "export"]` → truth 阶段重新执行。

**幂等性分析**：
- 如果 resume_from 阶段已成功完成（如 approve 已 complete），重新执行 approve（placeholder 阶段，只标记 human_confirmed）无副作用——`mark_stage_start`/`mark_stage_complete` 是幂等的（覆盖已有记录）。
- truth 阶段（`service.approve()`）内部 `_advance_approve_state` 是幂等的（L402-403 检查 `if current == TRUTH_COMMITTED: return`）。
- export 阶段同理。
- **结论**：inclusive resume 安全。

### 2. 补全 NEEDS_REVIEW 门禁（`src/storyforge3/state/gating.py`）

NEEDS_REVIEW 状态下允许恢复动作：

```python
if chapter_status in {ChapterStatus.EXPORTED, ChapterStatus.NEEDS_REVIEW}:
    return frozenset()
```

改为：

```python
if chapter_status == ChapterStatus.NEEDS_REVIEW:
    return frozenset({"plan", "draft", "audit"})
if chapter_status == ChapterStatus.EXPORTED:
    return frozenset()
```

**依据**：
- `machine.py:24` NEEDS_REVIEW 可回到 `{PLANNED, DRAFTED, EMPTY}`。
- 手动编辑后用户需要重新 audit（看审计结果）、或重新 draft（覆盖正文）、或重新 plan（从零开始）。
- `discard` 不在此处——discard 端点有独立路由 `DELETE /{chapter_no}`，不走 `_guard_action`。
- 不允许 `approve`/`truth`/`export`（需先通过 audit）。

### 3. 对齐 `_guard_action` 中 discard 的处理

检查 `DELETE /{chapter_no}`（`chapters.py:645-651`）是否已走 `_guard_action`：

```python
@router.delete("/{chapter_no}")
async def discard_chapter(
    book_id: str,
    chapter_no: int,
    discarder: ChapterDiscarder = Depends(get_chapter_discarder),
):
    return ok(_discard_result_to_response(discarder.discard(book_id, chapter_no)))
```

**当前不走 `_guard_action`**——discard 直接执行。这是正确行为（discard 是独立操作，不受门禁约束，`allowed_actions` 不含 "discard"）。**保持不变。**

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| `_stages_from` 现有逻辑 | `chapters.py:820-825` | **修改**（`+1` 移除） |
| NEEDS_REVIEW 转换规则 | `machine.py:24` TRANSITIONS | **参照**（PLANNED/DRAFTED/EMPTY） |
| `force_needs_review` 调用 | `chapter_service.py:290` update_text | **参照**（确认 NEEDS_REVIEW 触发场景） |
| `mark_stage_failed` resume_from | `run_registry.py:138` | **不变**（值正确，消费方 _stages_from 修复） |
| 幂等性分析 | `chapter_service.py:396-411` _advance_approve_state | **验证**（确认 resume 安全） |

**新写比例**：约 **5%**。纯修改两处既有逻辑（一行 `+1` 移除 + gating.py 一个分支扩展）。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥589 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
```

手动（用 fixture 书）：
- 构造 run 记录 resume_from="truth" → `_stages_from("truth", target_stages)` 返回 `["truth", "export"]`（而非 `["export"]`）。
- 构造 run 记录 resume_from="plan" → `_stages_from("plan", target_stages)` 返回 `["plan", "draft", "audit", "revise", "approve", "truth", "export"]`。
- 构造章节 NEEDS_REVIEW → `allowed_actions()` 返回 `{"plan", "draft", "audit"}`。
- 构造章节 EXPORTED → `allowed_actions()` 返回 `{}`。

## 必须覆盖的测试

- `_stages_from("truth", full_stages)` → `["truth", "export"]`（inclusive）。
- `_stages_from("plan", full_stages)` → 全部 7 个阶段（inclusive）。
- `_stages_from(None, full_stages)` → 全部 7 个阶段（无 resume）。
- `_stages_from("nonexistent", full_stages)` → 全部 7 个阶段（无效值 fallback）。
- `allowed_actions(NEEDS_REVIEW, None, 0, False)` → `{"plan", "draft", "audit"}`。
- `allowed_actions(EXPORTED, None, 0, True)` → `{}`（不变）。
- `allowed_actions(NEEDS_REVIEW, RUNNING, 0, False)` → `{}`（运行中仍全禁）。
- resume 后重新执行已成功阶段（如 approve placeholder）的幂等性——可集成测试验证。

## 红线

- ❌ 不改 `run_registry.py` 的 `resume_from` 设置逻辑（值本身是正确的——指向失败阶段）。
- ❌ 不改 `allowed_actions()` 对 EXPORTED 的返回（仍为空，新版本规划 Out of Scope）。
- ❌ 不给 NEEDS_REVIEW 加 `approve`/`truth`/`export`（需先 audit）。
- ❌ 不改 discard 端点（保持不走 guard）。
- ❌ 不动《别打了》真实数据。
- ❌ 不做前端改动。

## 回报

- commit hash（建议 `fix(pipeline): inclusive resume_from + NEEDS_REVIEW gating actions`）
- pytest + ruff 结果
- `_stages_from` 参数化测试用例输入/输出对照表
- `allowed_actions(NEEDS_REVIEW, ...)` 返回值确认

## Out of Scope

- ❌ Bug A 修复（truth_exists 门禁误判，见 P-FIX-1）。
- ❌ ChapterStatus.SETTLED 清理（P-FIX-3）。
- ❌ spec §6 命名对齐（`run-full`/`re-plan`/`truth-extract`/`re-audit`）。
- ❌ EXPORTED→新版本规划。
- ❌ export hash 校验。
