# StoryForge3 下一步计划

> 更新时间：2026-06-14
> 职责：只记录后续计划、风险和目标。当前事实见 `docs/current.md`，历史见 `docs/history.md`。
> 架构依据：`docs/architecture/run-state-and-viewer.md`；外部评估：`docs/proposals/doubao-p0.5-p1-eval.md`。

## 总方向

**agent-mode-first**：把系统从"功能堆叠 + 手动按钮"演进为"创作流程操作系统"——Action/Run 执行、RunRecord/SSE 可观察、前端只看+确认+介入。最终让 Phase 10B AutoDirector 成为可暂停/可检查/可恢复/可审计的生产系统，而非"把现有问题自动放大"的黑盒。

范式转换已落地一半：章节页已是纯查看 Run Viewer（P0.5）；运行入口是 agent/API；**下一步是把"运行状态"持久化为一等公民**，让刷新/重启后能恢复、让前端面板真正反映火车运行。

## P1：流程可信基础（当前重点，约 1 周）

按豆包建议分三步，**不要一次重写整个章节页**。

### P1-1 RunRecord 后端最小闭环
- `RunStatus`（PENDING/RUNNING/WAITING_FOR_HUMAN/COMPLETED/FAILED/RESUMABLE/CANCELLED）
- `PipelineRunRecord` + `StageResult`，持久化到 `chapters/{n}/runs/{run_id}.json` + `current_run.json`
- `POST /run` 改**异步**（立即返 `run_id`，后台跑）+ `GET /run` + `POST /run/{id}/resume` + `/cancel`
- `ChapterStatus` 加 `TRUTH_COMMITTED`（APPROVED→TRUTH_COMMITTED→EXPORTED）
- **目标**：刷新后前端知道"后台之前跑到哪"。
- **限制**（明确接受）：进程内 registry 后端重启丢任务 → 标 RESUMABLE；多 worker 不可靠（P3 上队列）。

### P1-2 前端 Run Viewer 最小版
- `api/runs.ts` + `useRunRecord` + `useRunEvents`（ref 模式，已修 flapping）
- `RunTrack`（横向阶段轨）+ `LiveStage`（流式正文/进度/等待提示）
- 现有查看 tab 降级为 ResultTabs；保留手动正文编辑
- **目标**：用户看到 run 当前阶段、流式正文、失败点、等待确认点；刷新恢复。

### P1-3 门禁规则统一
- `allowedActions(chapter_status, run_status, audit, truth)` 纯函数（前后端共享语义）
- 后端 guard 强制 + 前端 disabled 镜像
- blocking>0 禁 approve；truth 未提交禁正式 export；exported 后"新版本"入口
- **目标**：解决"按钮乱序、已完成重跑、非法跳步"（当前 P0.5 只是"导出后全锁 + 查看不运行"的过渡门禁）。

### P1 SSE 标准化（随 P1-1/2）
现有 `pipeline:*`/`llm:*` 重命名为 `stage:start/progress/complete/error` + `run:start/complete/waiting`，加适配层过渡。

## P0.5 已完成（不再列入计划）

SSE named-event 修复、status 200+empty、分段流式正文、draft→DRAFTED、章节页纯查看、火山路由 fix、CCSwitch 供应商面板、CI 三连修复。详见 `current.md`。

## Phase 10B：自动导演 MVP（P1 之后）

**前置**：P1 完成（流程可信 + RunRecord 真相源 + 门禁）。

- **10B-1a** 灵感→第1章闭环：`AutoDirectorService`，书籍级 checkpoint/resume，全程 SSE，人工确认点（world/characters/第1章 draft 前）。
- **10B-1b** 第2-3章连续性：跨章 truth 累积召回，批量生成，连续性验证。

## Phase 10C：RAG + 方法论 + 产品化（候选）

Truth 检索优化（中文分词/距离衰减）、轻量 RAG、雪花法/钩子/节奏/弧光、编辑器专注模式、同人前端 UI。

## 《别打了》复杂世界观缺口（Phase 10B/C）

| 缺口 | 严重度 | 阶段 |
|------|--------|------|
| 无势力/组织/文明实体模型 | 高 | 10B |
| `WorldConfig.power_system` 纯文本 | 中 | 10C |
| Truth 关键词检索在 12 文明体量下可能退化 | 中 | 10C |
| 无"文明揭露进度"追踪 | 中 | 10B |

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| P1 异步 run 进程内 registry 重启丢任务 | 高 | 中 | 标 RESUMABLE，不假装无损恢复（单机 dogfood 可接受） |
| `TRUTH_COMMITTED` enum 破坏性变更 | 中 | 中 | 现有 exported 章节回填 + 全量回归 |
| Provider 延迟/限流致长任务失败 | 高 | 高 | stream/progress、checkpoint、重试降级、独立 truth timeout |
| 审计/修订结果 UI 看不到（P1 前） | 中 | 中 | P1-1 产物持久化 + GET 加载 |
| 桌面 Tauri build.rs CI 失败 | 中 | 低 | 独立 follow-up，不阻断 dogfood |
