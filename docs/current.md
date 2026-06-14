# StoryForge3 当前状态

> 更新时间：2026-06-14
> 职责：只记录当前事实、质量基线和进行中阶段。历史流水见 `docs/history.md`，后续计划见 `docs/next.md`。

## 当前定位

StoryForge3 是 AI Native 中文网文全流程生产工作台，覆盖建书、世界观、角色、卷纲、章节起草、审计、修订、truth 提取、导出、桌面端和 MCP 集成。

**产品方向（2026-06-14 锁定，见 `CLAUDE.md` "Product Direction — agent-mode ONLY"）：agent 模式唯一实现，手动模式（UI 运行按钮）deferred。** agent（Claude Code/Codex）或外部 API 驱动管线；Web UI 是只读 Run Viewer（运行状态中心 + 结果查看），不再有"点击运行"的步骤按钮。核心引擎价值已由 dogfood 验证（火山引擎 ark-code-latest 可产出高质量章节正文）。

当前阶段：**P0.5（解除 dogfood 阻塞）完成 → 进入 P1（流程可信基础：RunRecord + Run Viewer + 门禁）**。

## 已交付阶段

| 阶段 | 交付内容 | 状态 |
|------|----------|------|
| Phase 1-4 | 后端引擎、API、安全网、审计、Truth、Context 跟踪 | 完成 |
| Phase 5A/5C | React/Vite 前端 MVP、JSONL 日志、Service 对齐、快照 | 完成 |
| Phase 6 | CodeMirror、Tauri、同人、短篇、MCP Server | 完成 |
| Phase 7A-7D | 写作工作台、质量运营（Truth/快照/导出预览）、MCP 实战化、CI/CD、用户数据 | 完成 |
| Phase 8/8.5 | PyInstaller sidecar、Service 测试补齐、Dogfood RC 文档 + 冷启动 | 完成 |
| Phase 9 | Prompt 质量修复 | 完成 |
| Phase 10A-1/2/3 | 覆盖率基线 + 文档治理、后端流式 SSE、前端 SSE 进度 UI | 完成 |
| **P0.5（2026-06-13/14）** | SSE named-event 修复、status 200+empty、分段流式正文、draft→DRAFTED 状态推进、章节页纯查看(Run Viewer)、火山路由 fix、CCSwitch 供应商面板、CI 三连修复 | **完成** |

## P0.5 交付明细（本会话）

- **SSE 根因修复**：后端发 named `event: pipeline`，浏览器 `onmessage` 只收无名事件 → 事件一个都到不了前端。改为无名事件。（潜伏 bug，管理器层测试读 sse_manager 没抓到。）
- **章节页 = 纯 Run Viewer**：六个步骤从"点击运行"改为"点击查看 tab"（勾=已产出）；移除所有 run 按钮（含运行全流程）；运行只走 agent/API；保留手动正文编辑 + SSE 实时进度/流式。
- **draft 状态推进**：`ChapterService.draft()` 此前只写正文不推进状态（卡 PLANNED）→ 补 `PLANNED→DRAFTED`，UI 才能正确显示完成态。
- **CCSwitch 供应商面板**：`/settings` → 导入/切换/验证/移除 provider（6 端点，脱敏 api_key）；切火山 Codingplan 作 active。
- **火山引擎路由 fix**：`COMPAT_SUFFIXES` 错剥 `/api/coding` → 火山端点 404；移除该条。
- **CI 三连修复**：`.gitignore books/` 锚根 + `python -m pytest` + 补回被忽略的 components/books。
- **status 200+empty**：未开始章节不再 404 刷屏。

## 质量基线

| 项 | 当前 |
|----|------|
| 后端测试 | **522 passed**（P0.5 后；含 SSE/状态/流式/供应商/状态推进回归） |
| 前端测试 | **82 passed**（ChapterPipeline 重写为查看模型后） |
| Rust 测试 | 5 既有基线；本机无 cargo，需 CI 验证 |
| Python lint | `ruff check .` clean |
| Frontend build | `pnpm build` clean，仅 CodeMirror 大 chunk 警告 |
| 覆盖率 | ~91%（Phase 10A-1 基线；P0.5 未显著变化） |

## 当前工作焦点

1. **P1-1 RunRecord 后端最小闭环**：`RunStatus`/`PipelineRunRecord`/`StageResult` + `current_run.json` + 异步 `POST /run`（返 run_id）+ `GET /run` + resumable。
2. **P1-2 前端 Run Viewer 最小版**：`RunTrack`/`LiveStage`/`useRunRecord`/`useRunEvents`，刷新后能恢复 run 状态。
3. **P1-3 门禁统一**：`allowedActions()` + 后端 guard + 前端镜像 + exported 新版本入口。

> 详见 `docs/architecture-run-state-and-viewer.md`（架构 spec）与 `docs/proposals/豆包评估-p0.5-p1.md`（豆包的 P1 三步建议）。

## 已知边界（P1 待解）

- 审计/修订/批准/导出的**详细结果**在 UI 还看不到（这些产物未做"可加载持久化"，agent 跑完结果只回到 API 调用方）。规划/起草不受影响。
- `POST /run` 仍同步长请求（挂几分钟）；P1 改异步返 run_id。
- SSE 仅最近 100 条内存回放；P1 改 RunRecord 为真相源。
- 桌面 Tauri `build.rs` 在 CI 仍失败（独立 follow-up）。
