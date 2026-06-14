# StoryForge3 文档索引

> 入口。先读 `CLAUDE.md`（含 "Product Direction — agent-mode ONLY" 硬约束），再按需查此处。

## 进度与方向（先读这三份）
- [`current.md`](current.md) — 当前状态、质量基线、工作焦点。
- [`next.md`](next.md) — 下一步计划（当前：P1 RunRecord + Run Viewer + 门禁）、风险。
- [`history.md`](history.md) — 已完成阶段流水（最新在前）。

## 架构与决策
- [`architecture-run-state-and-viewer.md`](architecture-run-state-and-viewer.md) — **P1 架构 spec**：运行状态拆分（产物 vs 运行）、PipelineRunRecord、SSE 契约、Run Viewer、门禁规则。
- [`adr/`](adr/) — 架构决策记录（FastAPI service protocol / React-Vite / Truth-SQLite / Tauri-PyInstaller / CCSwitch 只读集成）+ `TEMPLATE.md`。

## 方案与外部评估（归档）
- [`proposals/小说创作全流程重设计方案.md`](proposals/小说创作全流程重设计方案.md) — 全流程重设计提案（阶段产物、状态模型、Action Module、门禁链）。
- [`proposals/豆包评估-p0.5-p1.md`](proposals/豆包评估-p0.5-p1.md) — 豆包对 P0.5 的验收 + P1 三步实施建议。

## 流程与运维
- [`quickstart.md`](quickstart.md) — 快速开始（环境、启动、provider 导入/切换）。
- [`dogfood-protocol.md`](dogfood-protocol.md) — dogfood 执行协议。
- [`dogfood-runs/`](dogfood-runs/) — dogfood run 记录。
- [`pm-process.md`](pm-process.md) — PM↔Codex 多代理开发流程。
- [`release-setup.md`](release-setup.md) — 发布/签名设置。
- [`mcp-registration.md`](mcp-registration.md) — MCP server 注册。

## 指令与历史归档
- [`directives/`](directives/) — PM 下发 Codex 的阶段指令（Phase 4–10A + 批量提交指令），历史归档。
- 早期策略/路线文档：`project-strategy.md`、`roadmap-phase4.md`、`roadmap-phase5.md`、`phase7-plan.md`、`剩余功能评估.md`、`架构决策-前端与规范.md`（多为历史背景，以 current/next 为准）。

## 约定
- **进度真相源** = `current.md` + `next.md`；其余策略文档为背景。
- **改章节页前**先读 `CLAUDE.md` "Product Direction — agent-mode ONLY"（UI 是只读 Run Viewer，勿加回 run 按钮）。
- 重大难逆决策 → 新增 `adr/ADR-NNN-*.md`。
