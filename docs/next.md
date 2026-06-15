# StoryForge3 下一步计划

> 更新时间：2026-06-15
> 职责：只记录后续计划、风险和目标。当前事实见 `docs/current.md`，历史见 `docs/history.md`。
> **方向权威**：[`docs/reviews/pm-direction-correction-2026-06-15.md`](reviews/pm-direction-correction-2026-06-15.md)（2026-06-15 方向纠偏，凌驾本文旧版）。

## 总方向（2026-06-15 纠偏后）

**小说生产本位**：StoryForge3 存在的唯一理由是**生产中文网文连载小说**（主力《别打了》）。**引擎是仆，小说是主。** 成功度量 = 产出的小说（章节数 / 质量 / 连续性 / 可读性），**不是**引擎特性数或测试通过数。

**漂移诊断**：自 P0.5（ch2 起草）以来 7 阶段全是引擎工作（RunRecord/reconcile/dev/章节显示/Run Viewer/门禁），《别打了》仍停 ch2，ch3/4 是幽灵。**引擎已够用，停手转向生产。**

**纠正**：
1. **P1-3（门禁）= 引擎最后一项**。之后立即转真实多章生产。
2. **生产不等 AutoDirector**——agent 现在就能调 API 产章；AutoDirector 是"自动化产章"，非前提。
3. **引擎扩张 DEFER**：P-IMP-2 / P-IMP-4 / Phase 10B AutoDirector / 10C 全部后置，待 dogfood 暴露真实阻塞才动。
4. **度量切换**：下一里程碑 = 《别打了》多出几章人读得下去的正文。

## 当前首要：真实多章生产（P1-3 验收后立即启动）

**目标**：用当前引擎（火山 ark-code-latest provider）经 agent/API 实际生产《别打了》多章可读正文，验证端到端闭环 + 暴露真实阻塞。

步骤：
1. **ch3/ch4 幽灵处置**（✅ 已完成 2026-06-15）：用户决策 discard，PM 已执行（删 truth.db 92 行 + truth JSON + exports + snapshots + pipeline.jsonl 该章行，全套备份 `books/_discard_backup_ch34/`）。reconcile 干净 ch2 状态。
2. **P-DISCARD-1 并行**（指令已下发）：把上述手写 discard 固化为有测试的 API 原语 + 强制 `_trash/` 备份，作 dogfood redo 保险。不阻塞 dogfood。
3. **生产 ch3**：agent 调 `POST /run` 全管线（火山 ark-code-latest）→ 验证 Run Viewer 实时反映 → reconcile 正确归档 → 人工读评（剧情/连续性/文笔）。
4. **连续性验证**：跨章 truth 召回、伏笔/回收、十二文明设定一致性。
5. **暴露的阻塞才进 backlog**：dogfood 中遇到的真问题（prompt 质量 / provider 稳定 / 世界观缺口）才开新指令，**不再 speculative 建特性**。

**验收**：产出 ≥3 章可读正文（非 fake provider），人工读评通过，无新幽灵产物。

## P1：流程可信基础 — ✅ **已关闭（2026-06-15）**

> P1-1 ✅ / P1-1b ✅ / P1-2 ✅ / P-IMP-3 ✅ / P-IMP-3b ✅ / P1-3 ✅ / P-DISCARD-1 ✅。**P1 全部闭环，引擎工作收官。** 详见 `docs/history.md`。

## P0.5 已完成（不再列入计划）

SSE named-event 修复、status 200+empty、分段流式正文、draft→DRAFTED、章节页纯查看、火山路由 fix、CCSwitch 供应商面板、CI 三连修复。详见 `current.md`。

## Phase 10B：自动导演 MVP（⚠️ DEFER，待真实生产验证后）

**前置**：真实多章生产（见上"当前首要"）跑通 + 暴露"人工驱动 agent 太累"的真需求，才启动 AutoDirector。**不要在没产出小说前造自动化。**

- **10B-1a** 灵感→第1章闭环：`AutoDirectorService`，书籍级 checkpoint/resume，全程 SSE，人工确认点（world/characters/第1章 draft 前）。
- **10B-1b** 第2-3章连续性：跨章 truth 累积召回，批量生成，连续性验证。
- 借鉴：`调研报告/trae-agent-architecture-wiki.md`（外部，agent loop / trajectory / lakeview 模式，仅设计参考）。

## Phase 10C：RAG + 方法论 + 产品化（⚠️ DEFER，候选）

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
