# 指令 P1-1：RunRecord 后端最小闭环

> 下发 Codex（Codex 罢工则 Claude 实施）。架构依据 `docs/architecture/run-state-and-viewer.md` §2-5；外部评估 `docs/proposals/doubao-p0.5-p1-eval.md` P1-1。
> 前置：P0.5 已完成（章节页纯查看 + SSE 流式可用，522/82 绿）。
> 目标：**刷新后前端能知道"后台之前跑到哪"**——把 run 状态从内存（SSE 最近 100 条回放）升级为持久化一等公民。完成后回报。

## 背景
P0.5 让 SSE 事件能到浏览器、流式正文可见，但 run 状态只在内存：后端重启 / 浏览器刷新 / 长任务断线都会丢失"当前跑到哪一步"。P1-1 引入 `PipelineRunRecord` 作为可查询、可恢复的真相源，SSE 退化为实时增量通道。

## 任务

### 1. 模型 `src/storyforge3/models.py`
- `RunStatus(str, Enum)`: `pending / running / waiting_for_human / completed / failed / resumable / cancelled`
- `StageResult`（dataclass）: `stage, status(running|completed|failed|skipped), started_at, finished_at, duration_ms, error_code, error_message, summary(dict|None)`
- `PipelineRunRecord`（dataclass）: `run_id, book_id, chapter_no, mode(full|single), target_stages(list[str]), status(RunStatus), current_stage(str|None), started_at, updated_at, stage_results(dict[str,StageResult]), llm_calls(list), error_code, error_message, resume_from(str|None)`
- `ChapterStatus` 加 `TRUTH_COMMITTED`（语义：truth 已提交，导出前置满足）

### 2. 状态机 `src/storyforge3/state/machine.py`
- 加合法转移 `APPROVED → TRUTH_COMMITTED → EXPORTED`
- 现有 `EXPORTED` 章节回填：若已 exported 则视为 TRUTH_COMMITTED+EXPORTED（迁移脚本或读时兼容）

### 3. RunRegistry `src/storyforge3/services/run_registry.py`（新）
- 进程内 run 生命周期：`start(...) / mark_stage_start / mark_stage_complete / complete / fail / cancel`
- 持久化：`books/{id}/chapters/{n}/runs/{run_id}.json`（每次状态变更原子写）+ `current_run.json`（指向当前/最近 run）
- `get_current(book_id, chapter_no) -> PipelineRunRecord | None`
- **启动扫描**：`status==running` 但进程已没（启动时发现）→ 标 `resumable`（不假装无损恢复）

### 4. 异步 run `src/storyforge3/api/routes/chapters.py`
- `POST /{n}/run` 改**异步**：建 RunRecord(`pending`) → 起 `asyncio.Task` 后台跑 → **立即返 `{run_id}`（HTTP 200，<50ms）**
- `GET /{n}/run` → 当前 RunRecord
- `POST /{n}/run/{run_id}/resume` → 从 `resume_from` 恢复
- `POST /{n}/run/{run_id}/cancel` → cancel
- 后台任务 = 现有 `ChapterWorkflow.run()` 包一层：每阶段 `mark_stage_start/complete` 更新 RunRecord + publish SSE；失败 `fail`（写 `resume_from`）

### 5. SSE 标准化 `src/storyforge3/api/sse.py` + `api/routes/events.py`
- 现有 `pipeline:start|progress|complete|error` + `llm:progress` 重命名为 `stage:start|progress|complete|error`（保留 `llm:chunk` 流式正文）
- 加 `run:start / run:complete / run:waiting`
- **后端本期发新名**；前端适配层在 P1-2 处理（过渡期可双发或前端临时映射，勿断流式）

## Part 3：借鉴来源

### 主要借鉴：StoryForge2 run 生命周期模型

StoryForge2 有完整的 run tracking 体系，与 P1-1 RunRecord 高度同构。

| 借鉴内容 | 来源文件 | 行数 | 借鉴方式 |
|---------|---------|------|---------|
| **run 生命周期协议** `start_run(book_id, chapter_no, action, actor_role, input_refs)` / `finish_run(run_id, ...)` | `storyforge2/engine/cli/studio_actions.py:52-57` | ~20 行 | **骨架移植** → RunRegistry 的 `start/mark_stage_*/complete/fail/cancel` 方法签名直接对齐 SF2 的 start_run/finish_run 协议 |
| **artifact ↔ run 关联** `ArtifactRecord.produced_by_run_id` | `storyforge2/engine/schemas/artifact.py:48-57` | ~10 行 | **模式复用** → PipelineRunRecord.run_id + stage_results 的设计依据 |
| **阶段产物 record 模式** `RevisionRecord`/`ChapterPlanRecord`/`ChapterSettlementRecord`/`GateDecisionRecord` | `storyforge2/engine/schemas/artifact.py:123-176` | ~50 行 | **模式复用** → StageResult(dataclass) 字段对齐（stage/status/started/finished/error/summary） |
| **status.last_run_id 持久化指针** | `storyforge2/engine/cli/studio_actions.py:155` | — | **模式复用** → `current_run.json` 指针机制 |

### 内部复用：SF3 既有基础设施

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| **状态转移** `advance()` + `InvalidTransitionError` + `force_needs_review()` | `state/machine.py:27-47` | **直接复用** → APPROVED→TRUTH_COMMITTED→EXPORTED 转移加法 |
| **SSE 事件发布** `SSEManager.publish(event: PipelineEvent)` | `api/sse.py:31-51` | **直接复用** → stage/run 事件发布 |
| **原子 JSON 持久化** tmp + rename | `snapshot.py` + `storage._atomic_write_text` | **直接复用** → runs/{run_id}.json + current_run.json 写入 |
| **后台任务包装** `ChapterWorkflow.run()` | `workflow.py` | **直接复用** → 异步 POST /run 包一层 RunRecord 更新 |

### InkOS 对照（已验证无直接可移植代码）

搜索 `docs/inkos-master/packages/core/src` 的 `runId/pipelineRun/RunRecord/stageResult` → **零命中**。InkOS 的 pipeline 是内存执行流，无持久化 run record。架构对照（持久化 run 状态）是 SF3 的新增设计点，但 SF2 已有等价模型，故借鉴源充分。

**新写比例**：约 **35%**。模型/持久化/状态机/SSE 全部复用 SF3 内部 + SF2 run 协议骨架；真正新写的是 RunRegistry 进程内生命周期管理 + 异步 POST /run endpoint 包装 + resumable 启动扫描逻辑。

---

## 验收门禁（全过）
```powershell
.\.venv\Scripts\python.exe -m pytest --tb=no -q     # ≥522 + 新增 run/gating 测试
.\.venv\Scripts\python.exe -m ruff check .            # clean
```
手动：
- `POST /run` → 立即返 `run_id`（<50ms，不挂）。
- `GET /run` 在 run 进行中返回 `status=running, current_stage=...`。
- 后端重启后，原 `running` 的 run 显示 `resumable`。
- truth-before-export 守卫仍生效。

## 必须覆盖的测试
- RunRecord 持久化 + 重启恢复（running→resumable）。
- 异步 `POST /run` 立即返回 + 后台推进 + SSE。
- `APPROVED→TRUTH_COMMITTED→EXPORTED` 转移合法；非法跳步被拒。
- truth 未提交时 export 被守卫阻断（不回归）。

## 红线
- ❌ 不破坏现有 522 测试（`TRUTH_COMMITTED` 是加法 + 回填，非破坏）。
- ❌ `POST /run` 不得挂（必须 <50ms 返回 run_id）。
- ❌ 进程内 registry **明确标注**"重启丢运行中任务→resumable"，绝不假装无损（单机 dogfood 可接受；多 worker/队列是 P3）。
- ❌ 不改 P0.5 已落地的纯查看前端（Run Viewer 前端是 P1-2，本期只后端 + GET /run）。

## 回报
- commit hash（建议 `feat(run): PipelineRunRecord + async POST /run + resumable`）
- pytest + ruff 结果
- 一次完整 run 的 `GET /run` 输出（展示 stage_results + 各阶段耗时）
