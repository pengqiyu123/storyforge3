# StoryForge3 阶段历史

> 更新时间：2026-06-15
> 职责：记录已完成阶段。当前事实见 `docs/current.md`，后续计划见 `docs/next.md`。

## P1-3 + P-DISCARD-1：门禁统一 + 章节 discard 原语 → P1 全部闭环（2026-06-15）

状态：完成。后端 589 passed（+23 vs P-IMP-3b 的 566）/ 前端 111 passed / ruff clean。

**P1-3 门禁统一**（commit `46746c2`）：

- **`allowed_actions()` 纯函数**（`state/gating.py` 37 行）：门禁唯一真相源，12 条参数化规则覆盖全部 ChapterStatus × RunStatus 组合。RUNNING/WAITING 全禁；AUDITED blocking>0 强制 revise；APPROVED+truth_exists 兼容 export；EXPORTED/NEEDS_REVIEW 空集。
- **后端 guard 集中接入**：`_guard_action()` → `_gate_state()` → `allowed_actions()`，7 个端点（plan/draft/audit/revise/approve/export/run）入口统一校验，不允许则抛 `ACTION_NOT_ALLOWED(409)` 含 `current_status`/`required` 诊断。
- **前端 `gating.ts` 按 DEFER 不做**：agent-mode 无按钮承载；409 错误体已自带诊断。
- **测试**：`test_gating.py` 12 参数化 + export compat；`test_api_chapters.py` 验证 export 409 / run gate 409。

**P-DISCARD-1 章节 discard 原语**（commit `c86b0ac`）：

- **`ChapterDiscarder` 服务**（`services/chapter_discarder.py` 275 行）：`preview()` 只读枚举 + `discard()` 备份→删除→reconcile。覆盖 5 层（正文/规划/truth JSON/导出/快照）+ run 目录 + pipeline.jsonl 行剥离 + state 键移除 + **Truth DB 删除**（`TruthStore.delete_by_chapter`，参数化 SQL）。
- **强制安全**：先备份到 `_trash/ch{n}/NNN` 再删除；`_is_scoped()` 防路径逃逸；pipeline 行解析双条件 `book_id + chapter_no`；不动 `book.json`。
- **幂等**：无产物章返空 summary 不报错。
- **API**：`GET /{n}/discard-preview` + `DELETE /{n}`，统一 envelope。
- **测试**：`test_chapter_discarder.py` 3 个（preview hash 对比 / 5 层全清 + 备份完整 + scope 安全 + 幂等）+ `test_api_chapters.py` scoped API 测试 + `test_api/test_chapter_discard.py` 全量 API 测试。

**P1 正式闭环。** 从 P1-1（RunRecord）到 P1-3（门禁），流程可信基础全部就绪。引擎工作收官。

## P-IMP-3b：章节展示精细化（2026-06-15）

状态：完成。后端 566 passed（+1）/ 前端 111 passed（+1）/ ruff + typecheck + build clean。commit `590c4fe`（RED `fbf9451`）。

关键里程碑：

- **reconcile 补派生字段**：`valid_chapter_count` / `highest_contiguous_chapter` / `next_writable_chapter_no` / `has_blocking_inconsistency`；per-chapter `validity`(valid/partial/orphan/empty)。纯派生，不改扫描逻辑。
- **阻断优先（PM 改进，优于分析师 §8.4）**：`has_blocking_inconsistency` 时指示器警告「⚠ 存在数据不一致（第 X、Y 章），请先检查」，**不**建议续写章号；仅全书一致时 `next_writable = highest_contiguous+1`。
- **文案修正**：顶部「真实产物 {maxChapter} 章」→「已发现章节产物 N 章 · 最高第 M 章 · ⚠ K 章不一致」；ch3/4 显示「孤儿产物：有 Truth/导出但无正文」。
- 《别打了》实测：`valid_count=2 / highest_contiguous=2 / next_writable=3 / has_blocking=true`；DOM 全字段命中，`forbidden_run_buttons=0`、`agent_trigger_mentions=0`。
- 不 heal / 不删 / 不改 book.json。

分析师文档 [`章节按进度展示体验分析与改进建议.md`](../章节按进度展示体验分析与改进建议.md) §7/§10 三处缺陷全部修复。

## P1-2 + P-IMP-3：Run Viewer 最小版 + 章节列表读 reconcile（2026-06-15）

状态：完成。后端 565 passed / 前端 110 passed（+28 vs P-OPS-1 的 82）/ ruff + typecheck + build clean。

**P-IMP-3**（commit `fb19096`，RED `a8e37f9`）：

- `ChapterList` 改读 `GET /reconcile`，废弃 `current_chapter+2` 空卡片启发式。
- ch3/4 显示「数据不一致」+ 可展开中文 reasons（3 条）；末尾单个「下一章指示器」；顶部进度改 `reconcile.max_chapter`。
- DOM 验收：`chapter-card-1..4` / `chapter5_buttons=0` / `next_indicator=1` / 进度 4/80 取代旧 2/80。

**P1-2**（commit `058d5f7`，RED `8037b01`）：

- 新增 `api/runs.ts` + `useRunRecord`（`GET /run` 刷新恢复）+ `useRunEvents`（SSE `run:*`/`stage:*`/`llm:chunk`，ref 模式）+ `RunTrack` + `LiveStage`。
- 集成进章节详情页顶部，保留既有 view-tabs + ChapterEditor（演进非重写）。
- **agent-mode-only 严格执行**：PM 裁决覆盖 spec §4 ActionBar——无运行按钮，ActionBar 只读 `run.status` + 「取消」（仅 RUNNING/WAITING 时）。
- DOM 四快照（active / after_reload / streaming / final）验收：RunTrack 逐阶段点亮 / 刷新恢复一致 / 流式累加 / `forbidden_run_buttons=0` 贯穿 / cancel 门控（运行时 1 → 完成 0）。
- 注：人工证据用 fake provider（隔离 `output/p1-2-manual/`），流式正文为 canned 重复段，非真实写作；真实 provider dogfood 待 sanity-check chunk 去重。

未做（转 P-IMP-3b）：分析师文档 [`章节按进度展示体验分析与改进建议.md`](../章节按进度展示体验分析与改进建议.md) §7/§10 抓到「真实产物 maxChapter 误导」「nextChapter=max+1 跳过幽灵章」「缺 valid/partial/orphan 分类」三处缺陷，PM 核验属实。

## P-OPS-1：统一启动入口（2026-06-14）

状态：完成。后端 565 passed（+20 vs P1-1b 的 545）/ ruff clean / 16 dev_runner 测试。

关键里程碑：

- **`storyforge3 dev` 子命令**：一条命令同时起 FastAPI(:8000) + Vite(:5173)，`[api]`/`[web]` 日志前缀，健康门（轮询 `/api/health` 校验 `ok`+`status==ok`，30s 超时），SIGINT/SIGTERM 优雅退出（Windows `taskkill /T /F` 进程树清理）。
- **启动诊断日志**：ready 时只读打印 providers.json 绝对路径(exists) + active_provider(label+model) + ccswitch_db(available) + books_dir(N books)——让"导入成功但读不到 provider"一眼可见，不创建 `.storyforge3`。
- **清晰错误**：`DevProcessError` 覆盖命令缺失 / web 目录缺失 / 端口占用 / 健康超时 / 子进程早退 / 端口类 OSError。
- **无新重依赖**：stdlib `asyncio.subprocess` + urllib + 既有 uvicorn；默认不开浏览器（`--open` 可选）。
- **借鉴**：`src-tauri/process_manager.rs` 双进程 + 健康门 + 进程树终止模式。

文档：`docs/quickstart.md` 顶部加警示"浏览器开发必须用 `storyforge3 dev`，否则后端不在线→书消失"；`CLAUDE.md` Commands + Service Boundary 更新。

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
