# StoryForge3 下一步计划

> 更新时间：2026-06-12  
> 职责：只记录后续计划、风险和目标。当前事实见 `docs/current.md`，历史见 `docs/history.md`。

## Phase 10A 路线图

| 阶段 | 目标 | 验收标准 | 状态 |
|------|------|----------|------|
| 10A-1 | 覆盖率基线 + 文档治理 | 覆盖率入档、状态文档拆分、5 个 ADR | 完成 |
| 10A-2 | 后端长任务可观察化 | LLM stream、chunk progress、truth 保障、后端测试不退步 | 完成 |
| 10A-3 | 前端 SSE 进度 UI | PipelineProgress、前端事件类型扩展、前端测试不退步 | 完成 |

## Phase 10A-Dogfood：产品体验验证（当前阶段）

Phase 10A 工程验证已全部完成，但尚未经过人在 Web UI 上的真实创作验证。两轮 dogfood 是 Phase 10B 的前置门禁。

### Dogfood Round 1：《别打了》第 2 章续写验证

**目标**：验证复杂世界观下的章节续写全流程。

| 维度 | 内容 |
|------|------|
| 书籍 | 《别打了，我帮你们翻译还不行吗?》 |
| 章节 | 第 2 章 |
| 类型 | 续写（已有第 1 章 truth） |
| 重点验证 | truth 召回质量、流式进度 UI、audit/revise 体验、章节可读性 |
| 执行方式 | Web UI 全流程（plan → draft → audit → revise → truth → export） |

### Dogfood Round 2：新书从零创建验证

**目标**：验证从灵感到第 1 章的完整"开书"流程。

| 维度 | 内容 |
|------|------|
| 书籍 | 新建测试书（简单设定，与《别打了》形成对比） |
| 类型 | 从零开始 |
| 重点验证 | 建书 → world → characters → volume → plan → draft 全链路 |
| 执行方式 | Web UI 全流程 |

### Dogfood 输出

- 两轮 dogfood run 记录（`docs/dogfood-runs/`）
- P0/P1/P2 问题清单
- Phase 10B AutoDirector 需求修正输入

### 通过标准

- 能完成一章，不需要绕过系统
- 流式进度 UI 在 draft 阶段可见且有帮助
- truth 被召回，对续写有上下文贡献
- 审计结果可理解，误判不阻断流程
- 章节文本达到"可人工编辑后继续连载"的水平

### 量化目标更新

| 指标 | 当前值 | Dogfood 后目标 |
|------|--------|----------------|
| 后端 tests | 501 | ≥501 且不退步 |
| 前端 tests | 71 | ≥71 且不退步 |
| Dogfood 记录 | 0 章 | ≥2 章（两轮） |
| P0 阻塞问题 | 待发现 | 0（全部修复） |

## Phase 10B：自动导演 MVP

**前置条件**：两轮 dogfood 完成，P0 问题修复。

目标：把 StoryForge3 从"管线控制台"推进到"AI 自动导演工作流"。

### 10B-1a：灵感 → 第 1 章闭环

交付：

- `AutoDirectorService`：灵感 → BookConfig → world → characters → volume → 第 1 章
- 书籍级 checkpoint/resume（INCUBATING → OUTLINING → ACTIVE）
- 全程 SSE 可见
- 人工介入点：world 确认、characters 确认、第 1 章 draft 前确认

验收：

- 一条灵感到第 1 章，全程无人工干预（可选确认点除外）
- 任意步骤失败可从 checkpoint 恢复
- 真实 provider 端到端验证通过

### 10B-1b：第 2-3 章连续性验证

交付：

- 跨章 truth 累积与自动召回
- 批量章节生成（DaemonService 扩展）
- 章节质量评估与连续性验证

验收：

- 第 2-3 章与前章保持设定一致
- truth 累积无遗漏
- 3 章端到端生成成功

### 暂不纳入 10B MVP

- 自动生成 3 章以上
- 完整 RAG
- 复杂势力/组织模型重构
- 多书并发导演
- 逐 token 前端渲染
- 完整导演台 UI

## Phase 10C：RAG + 方法论 + 产品化

候选方向：

- Truth 检索优化：中文分词、章节距离衰减、召回量评估。
- 轻量 RAG：向量检索与关键词检索混合，不急于引入重基础设施。
- 写作方法论增强：雪花法、钩子设计、节奏曲线、角色弧光。
- 编辑器体验：专注模式、打字机模式、项目树、卡片视图。
- 同人模式前端 UI。

## 《别打了》复杂世界观缺口

《别打了，我帮你们翻译还不行吗?》是管线压力测试书和当前主力创作书。后续需要在 Phase B/C 处理：

| 缺口 | 严重度 | 建议阶段 |
|------|--------|----------|
| 无势力/组织/文明实体模型 | 高 | Phase 10B |
| `WorldConfig.power_system` 仍是纯文本 | 中 | Phase 10C |
| Truth 关键词检索在 12 文明体量下可能退化 | 中 | Phase 10C |
| 无"文明揭露进度"追踪 | 中 | Phase 10B |
| 无主角能力阶段追踪 | 低 | 先由 rules + truth hooks 承载 |

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Dogfood 暴露管线级阻断问题 | 中 | 高 | dogfood 作为 10B 前置门禁，P0 必修 |
| Provider 延迟或限流导致长任务失败 | 高 | 高 | stream/progress、checkpoint、重试和降级 |
| 自动导演黑盒化 | 中 | 高 | 每阶段 SSE 和日志可见，失败可恢复 |
| 复杂世界观 truth 召回遗漏 | 中 | 中 | 先结构化 truth，再评估 RAG |
| Prompt 质量在复杂设定下退化 | 中 | 高 | dogfood Round 1 重点观察 |
| PyInstaller sidecar 体积过大 | 高 | 中 | 记录体积基线，评估 UPX/Nuitka/依赖裁剪 |
| Rust/桌面构建只在 CI 验证 | 中 | 中 | Windows CI job 保持必跑 |
