# StoryForge3 当前状态

> 更新时间：2026-06-16
> 职责：只记录当前事实、质量基线和进行中阶段。历史流水见 `docs/history.md`，后续计划见 `docs/next.md`。

## 当前定位

StoryForge3 是 AI Native 中文网文全流程生产工作台，覆盖建书、世界观、角色、卷纲、章节起草、审计、修订、truth 提取、导出、桌面端和 MCP 集成。

**产品方向（2026-06-15 锁定，见 `docs/reviews/pm-direction-correction-2026-06-15.md`）：引擎已够用，停手。下一里程碑 = 《别打了》多出几章人读得下去的正文。** agent 模式唯一实现，Web UI 是只读 Run Viewer。核心引擎价值已由 dogfood 验证（火山引擎 ark-code-latest 可产出高质量章节正文）。

当前阶段：**P1 全部闭环 ✅ → 引擎工作收官 → 转入真实多章生产（《别打了》ch3+）**。

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
| **P1-3（2026-06-15）** | `allowed_actions()` 纯函数 + 后端 guard（7 端点）+ 409 ACTION_NOT_ALLOWED + 参数化测试 | **完成** |
| **P-DISCARD-1（2026-06-15）** | 章节 discard 原语（5 层备份→删除→reconcile）+ API preview/DELETE + 幂等 | **完成** |
| **P-FIX-1（2026-06-15）** | `get_status()` 填充 truth + APPROVED 状态 truth 文件 fallback → 修复 export 门禁误拦 | **完成** |
| **P-FIX-2（2026-06-15）** | `_stages_from()` 改 inclusive resume + NEEDS_REVIEW 门禁补全 `{"plan","draft","audit"}` | **完成** |
| **P-FIX-3（2026-06-15）** | `_post_with_retries` 加 RemoteProtocolError retry（P-FIX-3） | **完成** |
| **P-UI-FIX-1（2026-06-16）** | 前端可见性修复：ChapterCard 接入 useChapterStatus + 挂载 AuditResultPanel/RevisionDiffPanel + GET /status 扩展 audit_result | **完成** |
| **P-PROMPT-P0（2026-06-16）** | 提示词结构清理：删除 CHAPTER_DRAFT_PROMPT + 清理 3 个孤儿模板 + _SafeDict warning | **完成** |

## P1 闭环声明

**P1（流程可信基础）于 2026-06-15 全部闭环。** P1-1 RunRecord ✅ → P1-1b reconcile ✅ → P-IMP-3 章节列表读 reconcile ✅ → P1-2 Run Viewer ✅ → P-IMP-3b 章节展示精细化 ✅ → P1-3 门禁统一 ✅。引擎工作收官，不再新增引擎特性。

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
| 后端测试 | **600 passed**（P-UI-FIX-1 + P-PROMPT-P0 后；commit `02be8d7`） |
| 前端测试 | **111 passed**（P-UI-FIX-1 后） |
| Rust 测试 | 5 既有基线；本机无 cargo，需 CI 验证 |
| Python lint | `ruff check .` clean |
| Frontend build | `pnpm build` clean，仅 CodeMirror 大 chunk 警告 |
| 覆盖率 | ~91%（Phase 10A-1 基线；P0.5 未显著变化） |

## 当前工作焦点

1. **⚠ 真实多章生产（《别打了》ch3+）= 当前首要**（P1-3 验收后立即启动）：agent/API 调火山 provider 产《别打了》ch3→ch4→…，验证端到端闭环 + 人工读评。详见 `docs/reviews/pm-direction-correction-2026-06-15.md`。
2. **引擎工作已收官**：P1-3 是最后一项引擎特性。P-IMP-2 / P-IMP-4 / Phase 10B / 10C 全 DEFER，直到 dogfood 暴露**真实阻塞**才动。
3. **P-DISCARD-1 并行完成**：章节 discard 原语已就绪，作 dogfood "写错可安全丢弃重来"的保险。
4. **ch3/4 幽灵已清理**：PM 执行 discard + P-DISCARD-1 固化；reconcile 干净 ch2 状态（max=2/valid=2/inconsistent=0/next_writable=3）。
5. **P-FIX-1/2 修复闭环**：truth_exists 门禁误判（Bug A）+ resume inclusive（Bug B）+ NEEDS_REVIEW 门禁补全，已提交 push。

> 详见 `docs/architecture/run-state-and-viewer.md`（架构 spec）与 `docs/proposals/doubao-p0.5-p1-eval.md`（豆包的 P1 三步建议）。

## 已知边界

- **Tech Debt**：`ChapterResult` 有 `audit` 和 `audit_result` 双字段共存（P-UI-FIX-1 遗留，后续统一为 `audit_result`）。
- **提示词内容待升级**：`compose-v1` 内容偏简陋（5 条防御性约束），需 P-PROMPT-P1 升级为 compose-v2（含爽点密度/断章规则/去AI味等）。
- 审计/修订/批准/导出的**详细结果**在 UI 还看不到（这些产物未做"可加载持久化"，agent 跑完结果只回到 API 调用方）。规划/起草不受影响。
- SSE 仅最近 100 条内存回放；P1 改 RunRecord 为真相源。
- 桌面 Tauri `build.rs` 在 CI 仍失败（独立 follow-up）。
- `ChapterStatus.SETTLED` 孤儿枚举值（无转换规则、无门禁覆盖，可安全删除）。
- Spec §6 命名与实际 action 名不一致（`run-full`/`re-plan`/`truth-extract`/`re-audit`），功能等价，P2 文档级。
- Export hash 校验未实现（spec 强制门禁要求，当前 export 不检查内容 hash）。
