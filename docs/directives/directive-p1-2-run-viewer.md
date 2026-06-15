# 指令 P1-2：前端 Run Viewer 最小版（agent run 进度可见 + 刷新恢复）

> 下发 Codex。前置：P1-1 RunRecord 后端闭环 ✅（`GET /run` + 异步 `POST /run` + SSE `run:*`/`stage:*`）；P-IMP-3 章节列表读 reconcile ✅。
> 目标：兑现 [`docs/architecture/run-state-and-viewer.md`](../architecture/run-state-and-viewer.md) §4 的 **Viewer 部分**——让 agent run 在前端实时显示阶段轨点亮 + 当前阶段实时输出，刷新后能从 `GET /run` 恢复 run 状态。

## ⚠️ 关键 PM 裁决：agent-mode-only 覆盖 spec §4 ActionBar

spec §4 的 `ActionBar` 含「运行全流程 / 运行下一阶段」PRIMARY 按钮——**这是 spec 写于 agent-mode-only 锁定硬化之前**。CLAUDE.md（2026-06-14 owner-confirmed）明确：**UI 不得有运行按钮，运行只走 agent/API**。

**本指令覆盖 spec §4 ActionBar**：
- ❌ 不实现「运行全流程 / 运行下一阶段 / 单阶段手动」任何运行触发按钮。
- ✅ ActionBar 位改为**只读运行状态读数**：`run.status` 徽章（RUNNING/WAITING_FOR_HUMAN/COMPLETED/FAILED/RESUMABLE/CANCELLED）+ 当前阶段 + 「由 agent 驱动」提示。
- ✅ 唯一允许的用户动作：**取消进行中的 run**（`POST /run/{id}/cancel`，仅 `run.status ∈ {RUNNING, WAITING_FOR_HUMAN}` 时可点）——这是观察者对异常 run 的止损，不是管线触发。
- ✅ 手编正文（Authoring 面）保留在既有 ChapterEditor，不动。

> 这是 PM 对 spec 的定向收窄，**不是矛盾**——spec 的 RunTrack/LiveStage/ResultTabs 全部照做，只删 ActionBar 的运行按钮。

## 范围：最小版（不 wholesale 替换 ChapterPipeline）

不做 spec §4 的完整 `ChapterPanel` 替换（高风险，会动既有 view-tabs + 编辑器）。本指令**演进**既有章节详情视图，加 run 状态可见性：

## 任务

### 1. 前端 run 数据层（新文件）

- `web/src/api/runs.ts`：`RunRecord` / `RunStatus` / `StageResult` 类型（对齐后端 `PipelineRunRecord`）+ `runsApi.get(bookId, chapterNo)` → `GET /api/books/{id}/chapters/{n}/run` + `runsApi.cancel(bookId, chapterNo, runId)` → `POST .../run/{runId}/cancel`。
- `web/src/hooks/useRunRecord.ts`：TanStack Query，`GET /run`，刷新即恢复 run 状态。
- `web/src/hooks/useRunEvents.ts`：SSE 订阅（ref 模式，避免 flapping），消费 `run:*` / `stage:*` / `llm:chunk`，实时更新本地 RunRecord 视图状态。

### 2. RunTrack 组件（新）

`web/src/components/chapters/RunTrack.tsx`：横向阶段轨 `plan→draft→audit→revise→approve→truth→export`。
- 每阶段图标 + 标签，按 `(chapter_status, run.current_stage, run.stage_results)` 点亮：completed=实心✓、running=脉冲、skipped=灰、未达=锁灰。
- 门禁未达阶段（spec §6）灰显 + 锁标（**只读展示，不禁用按钮——因为没有按钮**）。
- 无 run 时（idle）：按 `chapter_status` 静态点亮已产出阶段（复用 P-IMP-3 reconcile 的产物语义）。

### 3. LiveStage 组件（新）

`web/src/components/chapters/LiveStage.tsx`：当前活跃阶段的实时输出。
- 流式正文：draft 期间 `llm:chunk` 累加（既有能力，迁移到这里）。
- 阶段进度：`stage:progress` 的 `completed/total`。
- 等待提示：`run:waiting`（如「等待作者批准」——HITL 时）。
- 错误：`stage:error` / `run:complete(final_status=failed)` 显示 error_message + RESUMABLE 恢复提示。
- 无活跃 run 时：显示最近 run 的终态摘要或「空闲——由 agent 触发生产」。

### 4. 集成进章节详情视图

- 在既有章节详情页（chapters tab 选某章后）顶部加 `RunTrack`，下方 `LiveStage`，保留下方既有 view-tabs（正文/审计/diff/truth/导出）+ ChapterEditor。
- **不删**既有 view-tabs 与编辑器——它们是 ResultTabs + Authoring 面，本指令只**新增** run 可见性层。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| RunRecord API + 持久化 | `GET /api/books/{id}/chapters/{n}/run` + `POST .../cancel`（P1-1 已落地） | **直接消费** |
| SSE 订阅 ref 模式 | 既有 `useRunFullPipeline` / ChapterPipeline SSE 处理（已修 flapping） | **模式复用** → `useRunEvents` |
| 阶段点亮语义 | spec §4 RunTrack + P-IMP-3 reconcile 产物勾语义 | **设计复用** |
| 流式正文累加 | 既有 `llm:chunk` 处理（P0.5/P10A-2） | **直接迁移**进 LiveStage |
| 状态徽章 | 既有 Badge 体系 + P-IMP-3 inconsistent 徽标 | **直接复用** |

**新写比例**：约 **60%**（前端 run 数据层 + RunTrack + LiveStage 是新写；SSE/流式既有）。后端无改动。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥565 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
pnpm --dir web test                                      # 全绿
pnpm --dir web build                                     # clean
```

手动（`storyforge3 dev` + agent 触发一次 `POST /run`）：
- 章节 detail 页顶部 RunTrack 随 `stage:start/complete` 逐阶段点亮。
- draft 阶段 LiveStage 流式显示正文（`llm:chunk` 累加）。
- **刷新浏览器** → `useRunRecord` 从 `GET /run` 恢复，RunTrack/LiveStage 显示进行中态（不丢）。
- run 完成 → RunTrack 全亮 + LiveStage 终态摘要。
- **页面无任何「运行」按钮**（agent-mode-only 验证）；只有「取消」在 run 进行中时可点。

## 必须覆盖的测试

- `useRunRecord`：fetch + 刷新恢复（mock `GET /run` 各 status）。
- `useRunEvents`：SSE 事件 → 本地状态更新（run:start/stage:complete/llm:chunk/run:complete）。
- `RunTrack`：各阶段点亮状态（completed/running/skipped/locked）+ 无 run 静态态。
- `LiveStage`：流式累加 / 进度 / waiting / error / idle。
- **无运行按钮断言**：页面不含「运行全流程/运行下一阶段」文案或 run-trigger 按钮；「取消」仅 run 进行中可见。

## 红线

- ❌ **不加任何运行触发按钮**（agent-mode-only，CLAUDE.md 锁定）。ActionBar 只读 + 取消。
- ❌ 不 wholesale 替换 ChapterPipeline（演进，不重写；保住 view-tabs + 编辑器）。
- ❌ 不改后端（P1-1 已就绪）；不动 book.json / reconcile / ch3-ch4。
- ❌ 不引入新重依赖。

## 回报

- commit hash（建议 `feat(web): minimal Run Viewer (RunTrack + LiveStage + run recovery)`）
- pytest + ruff + typecheck + 前端 test + build 结果
- agent run 实测：RunTrack 点亮 + LiveStage 流式 + 刷新恢复 的截图或 DOM（含「无运行按钮」断言）

## Out of Scope

- ❌ ActionBar 运行按钮（agent-mode-only 永久禁止，除非 owner 再决策）。
- ❌ 完整 ChapterPanel 替换（本指令是最小版；全替换留后续）。
- ❌ P1-3 门禁统一 `allowedActions()` 纯函数（独立指令，本指令门禁只做只读展示）。
- ❌ P-IMP-2 导入 auto-verify / P-IMP-4 标签清理（独立指令）。
