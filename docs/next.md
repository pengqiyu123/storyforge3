# StoryForge3 下一步计划

> 更新时间：2026-06-12  
> 职责：只记录后续计划、风险和目标。当前事实见 `docs/current.md`，历史见 `docs/history.md`。

## Phase 10A 路线图

| 阶段 | 目标 | 验收标准 | 状态 |
|------|------|----------|------|
| 10A-1 | 覆盖率基线 + 文档治理 | 覆盖率入档、状态文档拆分、5 个 ADR | 完成 |
| 10A-2 | 后端长任务可观察化 | LLM stream、chunk progress、truth 保障、后端测试不退步 | 完成 |
| 10A-3 | 前端 SSE 进度 UI | PipelineProgress、前端事件类型扩展、前端测试不退步 | 待执行 |

## Phase 10B：自动导演 MVP

目标：把 StoryForge3 从“管线控制台”推进到“AI 自动导演工作流”。

候选交付：

- `AutoDirectorService`：灵感输入 → BookConfig → world/characters/volume → 前 1-3 章。
- 书籍级 checkpoint/resume。
- 失败重试与人工介入点。
- 前端“一键开书”向导。
- MCP tool `auto_create_book`。

验收建议：

- 一条灵感能端到端生成前 1 章，失败可恢复。
- 全程 SSE 可见。
- 不绕过 truth 提取和审计门禁。

## Phase 10C：RAG + 方法论 + 产品化

候选方向：

- Truth 检索优化：中文分词、章节距离衰减、召回量评估。
- 轻量 RAG：向量检索与关键词检索混合，不急于引入重基础设施。
- 写作方法论增强：雪花法、钩子设计、节奏曲线、角色弧光。
- 编辑器体验：专注模式、打字机模式、项目树、卡片视图。
- 同人模式前端 UI。

## 《别打了》复杂世界观缺口

《别打了，我帮你们翻译还不行吗?》是管线压力测试书。当前只做数据入库，不改模型；后续需要在 Phase B/C 处理：

| 缺口 | 严重度 | 建议阶段 |
|------|--------|----------|
| 无势力/组织/文明实体模型 | 高 | Phase 10B |
| `WorldConfig.power_system` 仍是纯文本 | 中 | Phase 10C |
| Truth 关键词检索在 12 文明体量下可能退化 | 中 | Phase 10C |
| 无“文明揭露进度”追踪 | 中 | Phase 10B |
| 无主角能力阶段追踪 | 低 | 先由 rules + truth hooks 承载 |

## 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 真实 dogfood 暴露章节质量或 prompt 问题 | 中 | 高 | 先修管线可靠性，再扩自动导演 |
| Provider 延迟或限流导致长任务失败 | 高 | 高 | stream/progress、checkpoint、重试和降级 |
| 自动导演黑盒化 | 中 | 高 | 每阶段 SSE 和日志可见，失败可恢复 |
| 复杂世界观 truth 召回遗漏 | 中 | 中 | 先结构化 truth，再评估 RAG |
| PyInstaller sidecar 体积过大 | 高 | 中 | 记录体积基线，评估 UPX/Nuitka/依赖裁剪 |
| Rust/桌面构建只在 CI 验证 | 中 | 中 | Windows CI job 保持必跑 |

## Phase A 量化目标

| 指标 | 当前值 | Phase 10A 目标 |
|------|--------|----------------|
| 后端 tests | 498 | ≥498 且不退步 |
| 前端 tests | 62 | ≥68（10A-3 后） |
| pytest --cov | 91% | 已记录 |
| ADR 文档 | 5 | ≥5 |
| LLM 流式输出 | 后端可用 | 前端可见 |
| SSE 进度事件 | 后端 `llm:progress` | 前端进度条 |
