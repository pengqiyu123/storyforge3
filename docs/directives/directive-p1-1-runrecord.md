# 指令 P1-1：RunRecord 后端最小闭环

> 下发 Codex（Codex 罢工则 Claude 实施）。架构依据 `docs/architecture-run-state-and-viewer.md` §2-5；外部评估 `docs/proposals/豆包评估-p0.5-p1.md` P1-1。
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
