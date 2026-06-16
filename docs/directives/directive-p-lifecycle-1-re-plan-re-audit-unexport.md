# P-LIFECYCLE-1：修改闭环（re-plan / re-audit / EXPORTED 回退）

> 指令编号：P-LIFECYCLE-1
> 下发时间：2026-06-16
> 下发人：ZCode（PM）
> 执行人：Trae / Codex
> 优先级：P0

---

## 1. 问题陈述

产品的"修改-迭代"回路断裂。当前状态机只支持前向推进和丢弃重来，不支持"小改后重新走管线"：

- **手动编辑正文后**：状态变 `NEEDS_REVIEW`，只能回退到 `PLANNED` / `DRAFTED` / `EMPTY`
- **想重新审计已修改的正文**：没有路径，只能从 draft 重新开始
- **已导出章节想小改后重新导出**：不可能，`EXPORTED` 是死胡同，只能 discard 整章重来

这意味着用户做任何小修改（改个错别字、调整一段描写）都等于推翻全部下游产物。**高频操作没有回路，产品不可用于真实迭代。**

## 2. 目标

打通三条修改路径：

1. **re-plan**：已规划/已起草的章节可以重新生成计划，覆盖旧 plan，不丢正文
2. **re-audit**：已审计/已批准/已导出的章节在手动编辑后可以重新走 audit，不需要从 draft 重来
3. **EXPORTED 回退**：导出不是终点，可以回退到 `APPROVED` 状态，修改后重新导出

## 3. 改动范围

### 3.1 re-plan

**端点**：`POST /books/{book_id}/chapters/{chapter_no}/re-plan`

**行为**：
- 允许状态：`PLANNED`、`DRAFTED`、`NEEDS_REVIEW`、`NEEDS_REVISION`、`REVISED`
- 不允许：`EMPTY`（没有旧 plan 可覆盖）、`AUDITED`/`APPROVED`/`TRUTH_COMMITTED`/`EXPORTED`（plan 已被下游消费，重新 plan 会与现有正文脱节）
- 执行：调用 plan 服务生成新 plan，覆盖 `plans/{NNNN}.json`，状态保持不变（不回退）
- 返回：新 plan 内容

**设计理由**：re-plan 是"换计划但保留正文"——用户觉得方向偏了想调计划，但不想丢已写的内容。不允许在 AUDITED+ 状态 re-plan，因为正文已与 plan 绑定审计通过，改 plan 需要同时改正文。

### 3.2 re-audit

**端点**：`POST /books/{book_id}/chapters/{chapter_no}/re-audit`

**行为**：
- 允许状态：`NEEDS_REVIEW`、`DRAFTED`、`AUDITED`、`APPROVED`、`TRUTH_COMMITTED`、`EXPORTED`
- 不允许：`EMPTY`（没有正文）、`PLANNED`（没有正文）
- 执行：
  1. 如果状态是 `EXPORTED`，先回退到 `APPROVED`
  2. 如果状态是 `TRUTH_COMMITTED`，先回退到 `APPROVED`
  3. 运行本地机械审计 + LLM 审计
  4. 如果通过，状态推进到 `AUDITED`（覆盖旧的审计结果）
  5. 如果不通过，状态推进到 `NEEDS_REVISION`
  6. **不删除现有 truth 数据**——truth 在 re-audit 阶段仍然有效，只有 approve 才重新提取 truth
- 返回：审计结果

**设计理由**：用户改了正文后需要重新审计，但不需要重新生成 plan 或 draft。从 EXPORTED 回退到 APPROVED 而非 EMPTY，保留了所有下游产物（truth、导出文件），用户只需要重新走 audit→approve→export。

### 3.3 EXPORTED 回退

**端点**：`POST /books/{book_id}/chapters/{chapter_no}/unexport`

**行为**：
- 允许状态：`EXPORTED`
- 不允许：其他所有状态
- 执行：状态从 `EXPORTED` 回退到 `APPROVED`
- **不删除导出文件**（用户可能想对比新旧导出）
- **不删除 truth 数据**
- 返回：回退后的状态

**设计理由**：导出是一个"发布动作"，不是"不可逆状态"。回退只改状态标记，不删任何数据。用户重新 export 时覆盖旧文件（与现有 export 行为一致）。如果用户想保留旧导出，可以先手动下载。

### 3.4 状态机更新

**文件**：`src/storyforge3/state/machine.py`

在 transition table 中添加：

```python
# re-plan：覆盖 plan，状态不变
# 不需要新的 transition，因为状态不变

# re-audit：从各种已审核状态回到 AUDITED 或 NEEDS_REVISION
# 需要以下新 transition：
NEEDS_REVIEW → AUDITED       (via re-audit pass)
DRAFTED → AUDITED              (via re-audit pass)
AUDITED → AUDITED             (via re-audit, 重新审计)
APPROVED → AUDITED             (via re-audit, 回退后重新审计)
TRUTH_COMMITTED → AUDITED     (via re-audit, 回退后重新审计)
EXPORTED → AUDITED             (via re-audit, 回退后重新审计)
NEEDS_REVIEW → NEEDS_REVISION (via re-audit fail)
DRAFTED → NEEDS_REVISION      (via re-audit fail)
AUDITED → NEEDS_REVISION      (via re-audit fail)
APPROVED → NEEDS_REVISION     (via re-audit fail)
TRUTH_COMMITTED → NEEDS_REVISION (via re-audit fail)
EXPORTED → NEEDS_REVISION      (via re-audit fail)

# unexport：EXPORTED → APPROVED
EXPORTED → APPROVED            (via unexport)
```

**注意**：如果现有 transition table 用 `set()` 表示允许的目标状态，只需要扩展这些 set。不需要新方法——现有的 `advance` 或等效方法应该能处理。

### 3.5 gating 更新

**文件**：`src/storyforge3/state/gating.py`

在 `allowed_actions()` 中为新端点添加状态门禁：

```python
if status == ChapterStatus.EXPORTED:
    return {"unexport", "re-audit"}  # 现在返回空 set，改为返回这两个

if status in (ChapterStatus.AUDITED, ChapterStatus.APPROVED, 
              ChapterStatus.TRUTH_COMMITTED):
    actions = existing_actions | {"re-audit"}

if status in (ChapterStatus.DRAFTED, ChapterStatus.NEEDS_REVIEW,
              ChapterStatus.NEEDS_REVISION, ChapterStatus.REVISED):
    actions = existing_actions | {"re-audit", "re-plan"}
```

### 3.6 storage 清理

不需要新文件。re-plan 覆盖现有 `plans/{NNNN}.json`，re-audit 覆盖现有审计结果，unexport 只改状态。

## 4. 改动文件汇总

| 文件 | 改动 |
|------|------|
| `src/storyforge3/state/machine.py` | 扩展 transition table |
| `src/storyforge3/state/gating.py` | 新增 re-plan / re-audit / unexport 状态门禁 |
| `src/storyforge3/api/routes/chapters.py` | 新增 3 个端点 |
| `src/storyforge3/services/chapter_service.py` | 新增 re_plan / re_audit / unexport 方法 |
| `src/storyforge3/api/errors.py` | 如需要，新增 `invalid_transition_for_action` 错误 |
| `tests/` | 覆盖三个新端点的测试 |

## 5. 验收标准

### 5.1 re-plan
- [ ] `POST .../chapters/{n}/re-plan` 在 `PLANNED` 状态下成功，返回新 plan
- [ ] `PLANNED` 状态不变
- [ ] 旧 plan 被覆盖
- [ ] `DRAFTED` 状态下 re-plan 成功，正文不受影响
- [ ] `AUDITED`/`APPROVED`/`EXPORTED` 状态下返回 409/422（不允许）
- [ ] `EMPTY` 状态下返回 409/422（不允许）

### 5.2 re-audit
- [ ] `NEEDS_REVIEW` 状态下 re-audit 通过 → `AUDITED`
- [ ] `DRAFTED` 状态下 re-audit 通过 → `AUDITED`
- [ ] `EXPORTED` 状态下 re-audit → 先回退到 `APPROVED`，再审计 → `AUDITED` 或 `NEEDS_REVISION`
- [ ] `TRUTH_COMMITTED` 状态下 re-audit → 先回退到 `APPROVED`，再审计
- [ ] re-audit 不通过 → `NEEDS_REVISION`
- [ ] re-audit 不删除 truth 数据
- [ ] re-audit 不删除导出文件
- [ ] `EMPTY`/`PLANNED` 状态下返回 409/422（没有正文可审计）

### 5.3 unexport
- [ ] `EXPORTED` 状态下 unexport → `APPROVED`
- [ ] 导出文件不被删除
- [ ] truth 数据不被删除
- [ ] 非 `EXPORTED` 状态下返回 409/422

### 5.4 质量基线
- [ ] 后端测试全量通过（≥617 passed）
- [ ] ruff clean
- [ ] 无交叉污染

## 6. 不在本指令范围

- ❌ 不改前端 UI
- ❌ 不做世界观/角色/卷纲删除（P1，低频操作）
- ❌ 不做 run 记录清理（P1）
- ❌ 不做 staleness 标记系统（P2）
- ❌ 不做 reconcile heal（P2）
- ❌ 不做 truth 版本记录（P2）
- ❌ 不做 snapshot 恢复范围扩展（P2）

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| re-audit 后 truth 与正文不一致 | 不删 truth，用户走 approve 时重新提取 truth 覆盖 |
| re-plan 后 plan 与已有正文脱节 | 限制 AUDITED+ 不允许 re-plan，强制先回退 |
| EXPORTED 回退后重复导出覆盖 | 不删旧导出，重新 export 覆盖（与现有行为一致） |
| 状态机 transition table 改动引入不一致 | 严格测试每种状态下每个端点的预期行为 |

## 8. 实现优先级建议

1. **先改状态机**（machine.py + gating.py）
2. **再做 unexport**（最简单，只改状态）
3. **再做 re-audit**（核心价值，需要调用现有审计逻辑）
4. **最后做 re-plan**（覆盖 plan 文件，逻辑最独立）
