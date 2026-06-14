# StoryForge3 文档索引

> 入口。先读 `CLAUDE.md`（含 "Product Direction — agent-mode ONLY" 硬约束），再按需查此处。

## 进度与方向（先读这三份）
- [`current.md`](current.md) — 当前状态、质量基线、工作焦点。
- [`next.md`](next.md) — 下一步计划（当前：P1 RunRecord + Run Viewer + 门禁）、风险。
- [`history.md`](history.md) — 已完成阶段流水（最新在前）。

## 架构与决策 `architecture/`
- [`architecture/run-state-and-viewer.md`](architecture/run-state-and-viewer.md) — **P1 架构 spec**：运行状态拆分（产物 vs 运行）、PipelineRunRecord、SSE 契约、Run Viewer、门禁规则。
- [`architecture/ccswitch-integration.md`](architecture/ccswitch-integration.md) — CC-Switch 中转站集成（多端点多协议容错）。
- [`architecture/mcp-registration.md`](architecture/mcp-registration.md) — MCP server 注册指南。
- [`architecture/架构决策-前端与规范.md`](architecture/架构决策-前端与规范.md) — 前端架构决策 + 开发规范。
- [`adr/`](adr/) — 架构决策记录（FastAPI service protocol / React-Vite / Truth-SQLite / Tauri-PyInstaller / CCSwitch 只读集成）+ `TEMPLATE.md`。

## 调研报告 `research/`
- [`research/golden-three-hook.md`](research/golden-three-hook.md) — 网文开篇钩子检测与 golden_three_hook 规则重设计。
- [`research/sf3-gap-analysis.md`](research/sf3-gap-analysis.md) — 调研报告与 SF3 现状对照分析。
- [`research/project-strategy.md`](research/project-strategy.md) — 项目发展战略分析。
- [`research/剩余功能评估.md`](research/剩余功能评估.md) — 剩余功能评估（已归档，含执行结果对照）。

## 审查与评估 `reviews/`
- [`reviews/action-module-design.md`](reviews/action-module-design.md) — 动作模块化设计反思。
- [`reviews/action-module-pm-review.md`](reviews/action-module-pm-review.md) — 动作模块化 PM 审查报告。
- [`reviews/chapter-plan-persistence.md`](reviews/chapter-plan-persistence.md) — 章节规划刷新丢失问题审查。
- [`reviews/codex-current-status.md`](reviews/codex-current-status.md) — Codex 状态独立分析（Trae + PM 综合判断）。
- [`reviews/codex-execution-plan-audit.md`](reviews/codex-execution-plan-audit.md) — Codex 执行计划审计。
- [`reviews/doubao-phase10a-direction-eval.md`](reviews/doubao-phase10a-direction-eval.md) — 豆包 Phase 10A 方向决策评估。

## 方案与外部评估 `proposals/`
- [`proposals/小说创作全流程重设计方案.md`](proposals/小说创作全流程重设计方案.md) — 全流程重设计提案（阶段产物、状态模型、Action Module、门禁链）。
- [`proposals/doubao-p0.5-p1-eval.md`](proposals/doubao-p0.5-p1-eval.md) — 豆包对 P0.5 的验收 + P1 三步实施建议。

## 路线图 `roadmap/`（历史背景，以 current/next 为准）
- [`roadmap/phase4.md`](roadmap/phase4.md)、[`roadmap/phase5.md`](roadmap/phase5.md)、[`roadmap/phase7.md`](roadmap/phase7.md) — Phase 4/5/7 路线图。

## 流程与运维
- [`quickstart.md`](quickstart.md) — 快速开始（环境、启动、provider 导入/切换）。
- [`dogfood-protocol.md`](dogfood-protocol.md) — dogfood 执行协议。
- [`dogfood-runs/`](dogfood-runs/) — dogfood run 记录。
- [`pm-process.md`](pm-process.md) — PM↔Codex 多代理开发流程。
- [`release/release-setup.md`](release/release-setup.md) — 发布/签名设置。

## 指令归档
- [`directives/`](directives/) — PM 下发 Codex 的阶段指令（Phase 4–10A + 批量提交指令），历史归档。

## 约定
- **进度真相源** = `current.md` + `next.md`；其余策略文档为背景。
- **改章节页前**先读 `CLAUDE.md` "Product Direction — agent-mode ONLY"（UI 是只读 Run Viewer，勿加回 run 按钮）。
- 重大难逆决策 → 新增 `adr/ADR-NNN-*.md`。
