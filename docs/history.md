# StoryForge3 阶段历史

> 更新时间：2026-06-14  
> 职责：记录已完成阶段。当前事实见 `docs/current.md`，后续计划见 `docs/next.md`。

## P1-1b：章节产物一致性诊断 + truth 防御 + provider 健壮性（2026-06-14）

状态：完成。后端 545 passed（+13 vs P1-1 的 532）/ ruff clean / typecheck clean。

关键里程碑（Codex commit `e0e020b`）：

- **ChapterReconciler + `GET /api/books/{id}/reconcile`**：6 类产物对照（text/plan/truth/export/state/run），4 条 inconsistent 规则（`export_without_state`/`export_without_text`/`truth_without_state`/`orphan_state`）。对《别打了》输出 ch3/ch4 inconsistent（含全部 3 条 export/truth 相关 reason）、ch1/ch2 consistent。
- **truth retriever 防御**：严格 `< 目标章` 过滤 + 防御测试断言。
- **export 扫描只认真实导出文件**：排除 `.tmp` / meta sidecar；`StoragePaths.truth_file()` 统一为 `truth/chapter-XXXX.json`。
- **provider 路径健壮性（P-IMP-1 一并落地）**：`providers_config_dir` 锚定项目根（`resolved_providers_config_dir`）；`CCSWITCH_DB_PATH` 正式生效；无 key provider 前端禁选 + 后端 `NO_IMPORTABLE_PROVIDER`；火山 `/api/coding` builder + route-candidate 测试。
- **只读诊断，不 heal**：ch3/ch4 幽灵章节未清理，`book.json.current_chapter` 未改（等 PM 决定）。

事故（同日，非代码 bug）：用户只起前端 `pnpm dev`、后端 `:8000` 未运行 → "网页能开但报错 + 小说消失"。PM 直跑数据层确认 `BOOK COUNT=1`（数据完整），起后端即恢复。**第二次同因事故** → 下发 P-OPS-1（统一启动入口）。详见 `docs/reviews/pm-consolidated-decisions-2026-06-14.md`。

## P1-1：RunRecord 后端最小闭环（2026-06-14）

状态：完成。后端 532 passed（+10 vs P0.5 的 522）/ ruff clean。

关键里程碑：

- **RunRecord 一等公民**：`RunStatus` / `StageResult` / `PipelineRunRecord` 落地，持久化到 `books/{id}/chapters/{n}/runs/{run_id}.json` + `current_run.json`。
- **异步 POST /run**：改异步，`asyncio.create_task` 后台跑，立即返 `run_id`（实测 14-20ms，<50ms 达标）。
- **GET /run + resume + cancel** 端点齐备；后台任务每阶段 `mark_stage_start/complete` 更新 RunRecord + publish SSE。
- **resumable 不假装无损**：启动 `scan_resumable_runs()` 把重启前 running/pending/waiting 的 run 降级为 resumable（asyncio task 无法跨重启存活，注释明确）。
- **TRUTH_COMMITTED 门禁链**：`APPROVED → TRUTH_COMMITTED → EXPORTED`；`ExportService` 只允许 TRUTH_COMMITTED/EXPORTED 导出。
- **SSE 兼容**：保留 `pipeline:*`/`llm:*`，补 `run:*`/`stage:*`。

未做（PM §F 附加，转 P1-1b）：reconciliation 识别"有产物无 state"幽灵章节（如《别打了》ch3/ch4）、truth retriever 防御测试。

## P0.5：解除 dogfood 阻塞 + agent-mode-only 范式落地（2026-06-13/14）

状态：完成。后端 522 passed / ruff clean；前端 82 passed / build clean。

关键里程碑：

- **SSE named-event 根因修复**：后端发 `event: pipeline`（具名），浏览器 `onmessage` 只收无名事件 → SSE 事件一个都到不了前端。改 `events.py` 发无名事件。（潜伏 bug；管理器层测试读 `sse_manager` 未抓到。）
- **产品方向锁定**：`CLAUDE.md` 顶部新增 "Product Direction — agent-mode ONLY" —— 只实现 agent 模式，手动 UI 运行按钮 deferred；章节页 = 纯查看 Run Viewer。
- **章节页改造为纯 Run Viewer**：六个步骤从"点击运行"→"点击查看 tab"（勾=已产出）；移除所有 run 按钮；保留手动正文编辑 + SSE 实时进度/流式。
- **draft 状态推进修复**：`ChapterService.draft()` 此前只写正文不推进状态机（卡 PLANNED）→ 补 `_advance_draft_state`（PLANNED→DRAFTED，幂等）。
- **分段流式正文**：`ChunkedGenerator.on_chunk` → draft 发布 `llm:chunk` → 前端流式累加。
- **status 200+empty**：未开始章节不再 404 刷屏（`get_status` 返 empty 而非 raise）。
- **CCSwitch 供应商面板**：`/settings` → 导入/切换/验证/移除（6 端点，脱敏 api_key）；切火山引擎 CodingPlan（ark-code-latest）作 active。
- **火山引擎路由 fix**：`COMPAT_SUFFIXES` 错剥 `/api/coding` → 火山端点 404；移除该条 + 对应测试。
- **CI 三连修复**：`.gitignore books/`→`/books/` 锚根 + `python -m pytest` + 补回被错误忽略的 `web/src/components/books/`。
- **dogfood 验证**：《别打了》ch2 起草成功（drafted，4237 字，翻译机制驱动剧情、贴十二文明设定）；火山 provider 实测 truth_extract 402.5s（600s 独立超时已落 commit 96d2975）。

相关：架构 spec `docs/architecture/run-state-and-viewer.md`；豆包评估 `docs/proposals/doubao-p0.5-p1-eval.md`；重设计提案 `docs/proposals/小说创作全流程重设计方案.md`。

## Phase 10A-2：后端 LLM 流式输出 + SSE 进度

状态：完成。

交付：

- `LLMService.generate_text_stream()` 支持 OpenAI Chat / Responses 流式解析，非流式格式降级到 `generate_text()`。
- `ChunkedGenerator` 新增 `on_progress` 回调，并在 chunk plan 超时或 provider 错误时按 outline 降级分段。
- 章节 draft/revise 路由发布 `pipeline:start`、`llm:progress`、`pipeline:complete/error`。
- `ChapterWorkflow` 在导出前确保当前章节 truth 已持久化，避免 dogfood 中 truth gap 被状态机 force 掩盖。

验证记录：核心相关测试 59 passed；覆盖率运行 498 passed / 91%。

## Phase 10A-1：覆盖率基线 + 文档治理

状态：完成。

交付：

- 新增 `docs/current.md`、`docs/history.md`、`docs/next.md`，删除旧的混合状态文档。
- 记录 pytest-cov 基线：总覆盖率 91%。
- 启用 ADR：FastAPI Service 分层、React/Vite 前端、Truth SQLite、Tauri sidecar、CC-Switch 只读集成。

## Phase 9：Prompt 质量修复

状态：完成。

交付：

- 升级 `chapter_service.py`、`character_service.py`、`volume_service.py` 的空壳 prompt。
- 加强 `compose-v1` 和 `audit-v1`。
- 为 prompt 内容和 schema 结构增加 9 个测试。

验证记录：486 后端测试通过，ruff clean。

## Phase 8.5：Dogfood RC

状态：完成。

交付：

- `README.md` 和 `docs/quickstart.md`：10 分钟启动 Web 工作台。
- `docs/dogfood-protocol.md`：真实写一章的测试协议。
- 冷启动 smoke：临时 venv 安装、CLI help、`storyforge3 serve`、`/api/health`、Vite 代理验证。
- `docs/release/release-setup.md` 更新 sidecar / venv fallback 描述。

遗留：真实写章 dogfood 需要继续积累样本。

## Phase 8A-1：Python Sidecar 打包

状态：完成。

交付：

- PyInstaller `--onedir` sidecar 入口、spec 和 Windows 构建脚本。
- Tauri 集成 `tauri-plugin-shell`、`externalBin`、`shell:allow-spawn`。
- Rust process manager 改为 sidecar-first / venv-fallback 双模式。

复盘：后续真实打包需对照 Manuskript / novelWriter 的 PyInstaller 经验，重点检查 datas、hidden imports、体积和杀毒误报。

## Phase 8B-1：Service 测试补齐

状态：完成。

交付：

- `PromptService` 7 个测试。
- `StyleService` 7 个测试。
- `TruthService` 6 个测试。
- Service 层 17/17 独立测试覆盖。

## Phase 7D：CI/CD + 用户数据管理

状态：完成。

交付：

- GitHub Actions：backend / frontend / desktop 三 job CI。
- Windows tag release 骨架和 Tauri updater artifact 配置。
- `WorkspaceService`：validate、backup、restore；恢复前自动安全备份。
- `/settings` 前端工作区设置页。

## Phase 7C：MCP 实战化

状态：完成。

交付：

- MCP tool 错误恢复建议。
- `next_step` 字段和结构化 `DraftResult`。
- 15 个 tool docstring 操作分层。
- `docs/architecture/mcp-registration.md` 注册指南。

## Phase 7B：质量运营面板

状态：完成。

交付：

- Truth 历史面板：6 类 truth 分组、章节切换、搜索过滤。
- Snapshot 管理和白名单回滚。
- Export preview：番茄、Markdown、起点格式预览、复制和下载。

## Phase 7A：写作工作台

状态：完成。

交付：

- 章节编辑保存：SHA-256 乐观锁、Ctrl+S、保存后 `NEEDS_REVIEW`。
- 审计定位：规则段落索引、snippet、CodeMirror 高亮。
- 修订 Diff：真实 revise、`.before.md` 快照、段落级左右对比。

## Phase 6：桌面端、短篇、同人、MCP

状态：完成。

交付：

- CodeMirror 编辑器。
- Tauri 桌面 scaffold 和 polish。
- 同人 Canon 导入和 4 维度审计。
- 短篇 5 步管线后端 + 前端。
- MCP Server 15 tool。

## Phase 5：前端 MVP + 基础设施

状态：完成。

交付：

- React/Vite/Tailwind/shadcn 前端 MVP。
- PipelineLogger JSONL 审计日志。
- Audit/Truth/Prompt/Style service 对齐。
- 导出前 zip 快照和自动清理。

## Phase 1-4：核心引擎

状态：完成。

交付：

- 从零建书、世界观、角色、卷纲、章节管线。
- 36 条机械审计、LLM 审计、修订模式。
- Truth 提取、SQLite 存储、上下文注入。
- FastAPI 路由、安全网、ContextBlock 跟踪、API 集成测试。
