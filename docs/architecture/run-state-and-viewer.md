# 架构设计:运行状态中心 + Run Viewer(P0.5 → P1)

> 范式转换:章节页从「六按钮控制面板」(假设用户是手动操作者)改为「**Run Viewer + 结果查看器**」(以运行状态为中心)。Agent 是火车,管线是轨道,前端是面板——面板显示火车在哪、在干什么,而不是让用户去按按钮。
>
> 手动模式不是另一条流程,而是「同一套 Action,用户一个一个点」;agent 模式是「同一套 Action,自动连续驱动」。二者通过统一 Action 层收敛。

---

## 1. 状态模型:产物状态 vs 运行状态(拆分)

当前 `ChapterStatus` 同时承载"产物状态"和"流程状态"——这是 isBusy 耦合、NEEDS_REVIEW 含义混杂、刷新后无 run 状态的根因。拆成两层:

### 1.1 章节产物状态 `ChapterStatus`(已存在,保持线性,语义=产物存到哪一步)

```text
EMPTY → PLANNED → DRAFTED → AUDITED → REVISED → APPROVED → TRUTH_COMMITTED → EXPORTED
                                                                                       ↑ 任何阶段失败不能自恢复 → NEEDS_REVIEW
```

调整:
- **新增 `TRUTH_COMMITTED`**(APPROVED 与 EXPORTED 之间),显式表达"truth 已提交,导出前置满足"。
- `NEEDS_REVISION` 不再作为正式 enum,改为**派生标记** = `AUDITED 且 audit.blocking>0`(状态机保持线性,复杂度交给运行记录)。
- `NEEDS_REVIEW` 保留为异常汇合态(任何失败 + 不能自恢复)。

> 改动面:`models.ChapterStatus` 加 `TRUTH_COMMITTED`;状态机 `state/machine.py` 加 `APPROVED→TRUTH_COMMITTED→EXPORTED` 合法转移;`ChapterStateMachine` 现有线性逻辑基本复用。

### 1.2 运行实例状态 `RunStatus`(新增,语义=某次 run 的生命周期)

```text
PENDING → RUNNING → WAITING_FOR_HUMAN → COMPLETED
                  ↘ FAILED → RESUMABLE
                  ↘ CANCELLED
```

- 一个章节同一时刻**至多一个 active run**(RUNNING/WAITING/FAILED-RESUMABLE)。
- 长任务"运行中"绝不塞进 `ChapterStatus`,由 `RunRecord.status` 表达——这是 agent run 也能在前端显示进度的前提。

---

## 2. PipelineRunRecord(一等公民)

把现有 `pipeline.jsonl`(append-only 审计日志)之上,加一份**可查询的当前 run 记录**:

```python
class RunStatus(str, Enum):
    PENDING = "pending"; RUNNING = "running"; WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"; FAILED = "failed"; RESUMABLE = "resumable"; CANCELLED = "cancelled"

@dataclass
class StageResult:
    stage: str            # plan/draft/audit/revise/approve/truth/export
    status: str           # running/completed/failed/skipped
    started_at: str; finished_at: str | None
    duration_ms: int | None
    error_code: str | None; error_message: str | None
    summary: dict | None  # 阶段产出摘要(chars/blocking_count/truth_count...)

@dataclass
class PipelineRunRecord:
    run_id: str
    book_id: str; chapter_no: int
    mode: str             # "full" | "single"
    target_stages: list[str]
    status: RunStatus
    current_stage: str | None
    started_at: str; updated_at: str
    stage_results: dict[str, StageResult]
    llm_calls: list[dict] # 复用现有 LLMCallRecord
    error_code: str | None; error_message: str | None
    resume_from: str | None
```

**持久化**:`books/{book_id}/chapters/{chapter_no:04d}/runs/{run_id}.json` + 章节级 `current_run.json`(指向当前/最近 run)。`pipeline.jsonl` 保留为不可变审计流。

**API**:
- `POST /api/books/{id}/chapters/{n}/run` → 异步启动,立即返回 `{run_id}`(见 §5 异步模型)。
- `GET /api/books/{id}/chapters/{n}/run` → 当前 run 记录(供前端刷新后恢复)。
- `POST /api/books/{id}/chapters/{n}/run/{run_id}/resume` → 从 `resume_from` 恢复。
- `POST /api/books/{id}/chapters/{n}/run/{run_id}/cancel` → 取消。

---

## 3. SSE 事件契约(标准化)

统一为单流、unnamed event(浏览器 `onmessage` 可收——已修 named-event bug),每个事件带 `run_id`:

| type | 触发 | 关键字段 |
|---|---|---|
| `run:start` | run 启动 | run_id, mode, target_stages |
| `stage:start` | 进入某阶段 | run_id, stage |
| `stage:progress` | 阶段内进度(分段) | run_id, stage, completed, total |
| `llm:chunk` | 流式正文段 | run_id, stage, text |
| `stage:complete` | 阶段完成 | run_id, stage, summary |
| `stage:error` | 阶段失败 | run_id, stage, error_code, message |
| `run:waiting` | 卡在确认点(如批准) | run_id, decision_point |
| `run:complete` | run 结束 | run_id, final_status, chapter_status |

> 向后兼容:P0.5 仍用现有 `pipeline:start/llm:progress/llm:chunk/pipeline:complete/pipeline:error`;P1 重命名为 `stage:*`/`run:*` 并补 `run:waiting`。前端通过事件 `type` 判别,迁移期一个适配层。

---

## 4. 前端 Run Viewer(替代 ChapterPipeline 的六按钮布局)

```text
ChapterPanel(替代 ChapterPipeline)
├── ChapterHeader        产物状态徽章 + 运行状态徽章(run.status) + 字数/章号
├── RunTrack             横向阶段轨:plan→draft→audit→revise→approve→truth→export
│                        每阶段:图标+标签,按 (chapter_status, run.current_stage) 点亮;
│                        门禁未达的阶段灰显+锁标
├── LiveStage            当前活跃阶段的实时输出
│   ├─ 流式正文(draft 期间,llm:chunk 累加)
│   ├─ 阶段进度(stage:progress 的 completed/total)
│   └─ 等待提示(run:waiting:"等待作者批准")
├── ResultTabs           只读结果查看:正文 / 审计 / 修订diff / truth摘要 / 导出记录
└── ActionBar            上下文相关,PRIMARY 是 agent 驱动
    ├─ 主按钮:"运行下一阶段" / "运行全流程"(默认)
    └─ 次级:单阶段手动动作(折叠,按门禁 disabled)
```

**范式体现**:ActionBar 主按钮 = agent 全管线驱动(一键),不是六个并列手动按钮。单步手动降为次级 + 门禁禁用。章节页是"看 run 跑",不是"按步骤"。

**订阅**:一个 `useRunEvents(bookId, chapterNo)`(ref 模式,已修 flapping)订阅 SSE;`useRunRecord(bookId, chapterNo)` 查 `GET /run`(刷新恢复)。run 状态变化驱动 RunTrack + LiveStage + ActionBar。

---

## 5. 异步 Run 模型(P1 关键)

当前 `POST /run` 是**同步阻塞**(连接挂几分钟,违反可观察性)。P1 改异步:

```text
POST /run {mode, target_stages}
  → 后端建 RunRecord(status=PENDING),后台任务启动,立即返回 {run_id}(HTTP 200,<50ms)
  → 后台任务按 target_stages 执行,每阶段 publish SSE,更新 RunRecord
  → 前端用 run_id 订阅 SSE + 轮询/查询 RunRecord
```

实现:FastAPI `BackgroundTasks` 或一个进程内 run registry(`asyncio.Task` + run_id 映射)。后台任务 = 现有 `ChapterWorkflow.run()` 包一层 RunRecord 更新 + SSE publish。

> 风险:进程内 run registry 在后端重启时丢失运行中的任务 → run 标记 RESUMABLE,刷新后前端提示"可恢复"。多 worker 部署需后续上任务队列(P3 考量),单机 dogfood 够用。

---

## 6. 门禁规则(状态→允许动作)

后端状态机强制 + 前端镜像(disabled)。`allowed_actions(chapter_status, run_status, audit, truth_exists)`:

| chapter_status | run_status | 允许的动作 |
|---|---|---|
| 任意 | RUNNING/WAITING | 无(运行中,全部禁用,只允许 cancel) |
| EMPTY | idle | plan、run-full |
| PLANNED | idle | draft、re-plan、run-full |
| DRAFTED | idle | audit、run-full |
| AUDITED(blocking=0) | idle | approve、revise、run-full |
| AUDITED(blocking>0) | idle | revise(强制)、run-full |
| REVISED | idle | re-audit(强制)、run-full |
| APPROVED | idle | truth-extract、run-full |
| TRUTH_COMMITTED | idle | export、run-full |
| EXPORTED | idle | 新版本规划(显式,不覆盖) |
| NEEDS_REVIEW | idle | 由用户选恢复点 |

**强制门禁**(后端 guard,不可绕过):
- approve 需 `audit.blocking==0`
- truth 需 `chapter_status==APPROVED`
- export 需 `chapter_status==TRUTH_COMMITTED`(或 APPROVED+truth_exists)
- export 正文 hash == 批准正文 hash

---

## 7. P0.5:最小过渡(本周,解除 dogfood 阻塞)

P1 的完整 RunRecord/异步 run/Run Viewer 是 1 周工作量。P0.5 用**现有基础设施**先解除阻塞,不引入新契约:

| 修复 | 做法 | 复用 |
|---|---|---|
| **SSE 不送达** | events.py 去掉 named event(✅ 已修) | 现有 SSE |
| **agent run 无进度** | `ChapterPipeline` 的 `PipelineProgress` 显示条件从 `isBusy && pipelineStage` 改为 `pipelineStage`(SSE 驱动,与前端 mutation 解耦) | 现有 `pipeline:start/complete` |
| **六按钮乱序/重跑** | 步骤按钮 `disabled={isBusy \|\| isDone \|\| stageBlocked}`(按产物状态门禁禁用) | 现有 steps 表 |
| **status 404 噪音** | `GET /status` 返回 200+empty(✅ 已修) | — |

> P0.5 不做 Run Viewer 重设计,只让**现有 ChapterPipeline 在 agent 驱动下能显示进度 + 按门禁禁用按钮**。流式正文(llm:chunk)也已接好。这是过渡态,P1 再整体换成 Run Viewer。

---

## 8. 文件改动地图

### P0.5(立即,小)
- `web/src/components/chapters/ChapterPipeline.tsx` — PipelineProgress 解耦 isBusy;步骤按钮门禁禁用
- `src/storyforge3/api/routes/events.py` — ✅ 已修(named→unnamed)
- `src/storyforge3/api/routes/chapters.py` — ✅ 已修(status 200+empty)
- 测试:ChapterPipeline 测试补"agent run 显示进度""done 步骤禁用"

### P1(1 周)
- 后端:
  - `models.py` — `ChapterStatus.TRUTH_COMMITTED`、`RunStatus`、`PipelineRunRecord`、`StageResult`
  - `state/machine.py` — 新转移 + 门禁 guard
  - `services/run_registry.py`(新)— 进程内 run 生命周期 + RunRecord 持久化
  - `services/chapter_service.py` / `workflow.py` — run() 包 RunRecord 更新
  - `api/routes/chapters.py` — `POST /run` 异步返回 run_id;`GET /run`、`/resume`、`/cancel`
  - `api/sse.py` — 标准化 `stage:*`/`run:*` 事件
- 前端:
  - `web/src/api/runs.ts`(新)— RunRecord 类型 + run API
  - `web/src/hooks/useRunRecord.ts`、`useRunEvents.ts`(新)
  - `web/src/components/chapters/RunTrack.tsx`、`LiveStage.tsx`、`ChapterPanel.tsx`(新,替代 ChapterPipeline)
  - `web/src/lib/gating.ts`(新)— `allowedActions()` 纯函数,前后端共享语义
- 测试:RunRecord 持久化/恢复、门禁阻断、异步 run + SSE、刷新恢复

---

## 9. 风险与验收

**风险**:
- 异步 run 的进程内 registry 重启丢失 → 标 RESUMABLE,前端提示(单机可接受)。
- 状态机加 TRUTH_COMMITTED 是破坏性 enum 变更 → 现有 exported 章节回填、522 测试回归。
- SSE 标准化重命名 → 适配层过渡,别一刀切。

**验收(P1)**:
- agent `POST /run` → 前端 Run Viewer 实时显示阶段轨点亮 + 流式正文 + 完成态。
- 刷新浏览器 → RunRecord 恢复 run 状态(RUNNING 显示进行中、FAILED 显示恢复点)。
- 门禁:未批准不能 truth、truth 未提交不能 export、blocking>0 不能 approve——前后端都拦。
- 后端全量测试回绿 + 新增 run/gating 测试。

---

## 10. 不在本期范围(P2/P3)

- Action Module(14 动作元信息,统一 API/MCP/Agent)— P2
- AutoDirector(灵感到第1章、checkpoint/resume、跨章连续性)— P3
- 多 worker 任务队列 — P3
