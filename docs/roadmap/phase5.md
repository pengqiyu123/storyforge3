# Phase 5 路线图：从开发者工具到写作者工具

> 创建日期：2026-06-08
> 状态：✅ 已完成
> 📦 **时效性（2026-06-14 审核）：历史归档。** Phase 5/6/7 均已完成（原"规划中"状态过时），路线图保留作阶段背景，进度以 `../history.md` 为准。
> 前置里程碑：Phase 4 完成（301 tests, ruff clean, 引擎安全网 + Context 跟踪 + API 测试）

---

## 战略目标

**Phase 5 核心目标：将 StoryForge3 从 CLI-only 开发者工具转变为可视化写作者工具。**

Phase 1-4 构建了完整的后端引擎和 API 层。Phase 5 在此基础上交付用户界面，让非开发者（网文作者）能直观使用全部能力。

---

## 调研基础

### 当前能力盘点

| 功能域 | 状态 | 详情 |
|--------|------|------|
| 后端 API | ✅ 完成 | 37 端点，11 router，SSE 事件，标准错误信封 |
| API 测试 | ✅ 完成 | 15 端点集成测试（P0 11 + P1 4） |
| 引擎安全 | ✅ 完成 | 原子写入 + 失败诊断 |
| Context 跟踪 | ✅ 完成 | ContextBlock/ContextPackage + 优先级裁剪 |
| 审计 | ✅ 完成 | 36 机械规则 + LLM 4 维度 |
| 导出 | ✅ 完成 | TXT/MD/EPUB/Qidian 4 格式 |
| CLI | ✅ 完成 | 9 个命令覆盖全部操作 |
| **前端** | ❌ 不存在 | 零代码，零 scaffold |
| 通知 | ❌ 不存在 | SSE 有但推送无 |
| Service 对齐 | ⚠️ 部分 | 12 Protocol 中 5 个功能分散在模块中 |

### 技术栈决策

**依据**：同 workspace 的 CC-Switch 已验证以下技术栈：

| 选型 | 决策 | 依据 |
|------|------|------|
| 框架 | React 19 + TypeScript | CC-Switch 用 React 18，生态成熟 |
| 构建工具 | Vite 7 | CC-Switch 验证，DX 快 |
| 样式 | Tailwind CSS 4 | CC-Switch 用 3.4，升级到 4 |
| 组件库 | shadcn/ui (Radix UI) | CC-Switch 大量使用，组件可复用 |
| 状态管理 | TanStack Query (服务端) + Zustand (UI) | CC-Switch 用 TanStack Query |
| 图标 | Lucide React | CC-Switch 已用 |
| 编辑器 | Phase 1: textarea → Phase 2: CodeMirror 6 | 渐进式，CC-Switch 有 CodeMirror 集成 |
| 包管理 | pnpm | CC-Switch 用 pnpm |
| 通知库 | Sonner | CC-Switch 已用 |

**不在本 Phase 使用**：Plate.js 富文本编辑器（Phase 2 考虑）、Tauri 桌面端（Phase 3 考虑）

---

## 阶段总览

```
Phase 5A（前端 MVP）     →  Phase 5B（通知渠道）  →  Phase 5C（基础设施）
     ~10 天                      ~3 天                  ~4 天
  ┌──────────────────┐          ┌─────────────┐       ┌──────────────────┐
  │ 5A-1: Scaffold   │          │ Webhook     │       │ JSONL 审计日志    │
  │     + Book List  │          │ Telegram    │       │ Service 架构对齐  │
  │ 5A-2: Book Detail│          │ 飞书         │       │ 历史快照          │
  │     + Pipeline   │          │ 企微         │       │                  │
  │ 5A-3: Dashboard  │          │             │       │                  │
  │     + Polish     │          │             │       │                  │
  └──────────────────┘          └─────────────┘       └──────────────────┘
```

### 决策依据

1. **前端先行**：用户价值最高，CLI-only 严重限制了用户群体
2. **通知次之**：Daemon 用户需盯终端，推送通知解放人力
3. **基础设施最后**：JSONL 日志和 Service 对齐是技术债务，用户无感

---

## Phase 5A：React 前端 MVP（~10 天）

### 5A-1：前端 Scaffold + Book 管理（~3 天）

**目标**：从零搭建前端项目，交付第一个可用页面。

**产出**：
- `storyforge3/web/` 目录（前端项目根）
- Vite + React 19 + TypeScript + Tailwind 4 + shadcn/ui 脚手架
- API 客户端层（typed HTTP client，基于 FastAPI OpenAPI spec）
- 路由结构：`/` (dashboard), `/books` (list), `/books/:id` (detail)
- Book 列表页（展示所有书籍，状态标签）
- Book 创建表单（标题/类型/平台/目标章节/字数）
- 全局布局（侧边栏 + 顶栏 + 内容区）

**验收标准**：
- [x] `pnpm dev` 启动成功
- [x] Book 列表调用 `GET /api/books` 并渲染
- [x] Book 创建调用 `POST /api/books` 并刷新列表
- [x] TypeScript 编译无错误
- [x] 响应式布局（移动端可用）

**验收结果**（2026-06-08）：✅ 通过。31 个前端文件，4 个测试全绿，tsc/vite build 零错误，后端 301 tests 不退步。深色主题 + amber 强调色 + 网格纹理背景，非模板风格。

### 5A-2：Book Detail + Chapter Pipeline UI（~4 天）

**目标**：单本书的全景管理界面 + 章节管线可视化。

**产出**：
- Book 详情页（tabs: 概览/世界观/角色/卷/章节）
- World 编辑器（setting/power_system/core_conflict）
- Character 列表 + 创建
- Volume 规划展示
- Chapter 列表（状态徽章: PLANNED/DRAFTED/AUDITED/REVISED/EXPORTED）
- Chapter 管线操作：单步执行（plan/draft/audit/revise/approve）
- 管线全流程一键运行（调用 `POST /run`）
- SSE 实时状态更新
- Chapter 文本预览（只读 textarea）

**验收标准**：
- [x] Book 详情页展示 world/characters/volumes
- [x] Chapter 列表展示状态徽章
- [x] 管线操作调用对应 API 并刷新状态
- [x] SSE 事件实时更新 chapter 状态
- [x] 文本预览正确显示中文内容

**验收结果**（2026-06-08）：✅ 通过。20+ 新增前端文件（API 6 + hooks 5 + 组件 7 + 页面 1 + tabs 1），9 tests（7 files）全绿，tsc/build 零错误，后端 301 tests 不退步。ChapterPipeline 含 6 步操作条 + 全流程 + SSE hook + 文本预览。

### 5A-3：Dashboard + Polish（~3 天）

**目标**：全局仪表盘 + 视觉打磨。

**产出**：
- Dashboard 页面（书籍概览、Provider 健康状态、最近活动）
- Provider 列表页（`GET /api/providers`）
- Health 状态展示
- Audit 结果可视化（passed/failed 规则列表）
- 错误展示（API 错误信封 → toast 通知）
- 深色/浅色主题切换
- 全局搜索（书籍/章节）
- loading skeleton + empty state

**验收标准**：
- [x] Dashboard 展示书籍数量、Provider 状态
- [x] Audit 结果展示 passed/failed 规则
- [x] API 错误触发 toast 通知
- [x] 专注模式可用（替代浅色主题）
- [x] 无 console 错误

**验收结果**（2026-06-08）：✅ 通过。8 个新增文件（health API + hooks + AuditResultPanel + FocusMode + ThemeToggle），14 tests（10 files）全绿，tsc/build 零错误，后端 301 tests 不退步。Dashboard 含 Provider 状态卡片 + 最近活动流 + 快速操作。专注模式用 Context + localStorage + CSS transition 实现。

---

## Phase 5A 完成总结

**日期**：2026-06-08
**三个子阶段全部验收通过**：

| 子阶段 | 新增文件 | 测试 | 核心交付 |
|--------|----------|------|----------|
| 5A-1 Scaffold + Book | 31 | 4 (3 files) | React + Vite + Tailwind + shadcn 脚手架 + Book CRUD |
| 5A-2 Detail + Pipeline | ~20 | 9 (7 files) | Book Detail 5 Tabs + Chapter Pipeline + SSE + World/Char/Volume |
| 5A-3 Dashboard + Polish | 8 | 14 (10 files) | Provider 状态 + 活动流 + AuditResultPanel + 专注模式 |

**前端 MVP 终态**：~59 源文件，14 tests，CSS 6.5KB gzipped，JS 131KB gzipped。

---

## Phase 5B：通知渠道（~3 天）

### 5B-1：Webhook 通知框架

**目标**：Daemon 完成批次后推送通知。

**产出**：
- `src/storyforge3/notifications/` 模块
- 通知协议：`NotificationChannel` Protocol
- Telegram Bot 实现
- 飞书 Webhook 实现
- 企业微信 Webhook 实现
- 配置集成到 `book.json`（`notifications` 字段）
- Daemon 批次完成后触发通知

**验收标准**：
- [ ] `NotificationChannel` Protocol 定义
- [ ] 至少 1 个渠道实现（Telegram 优先）
- [ ] Daemon 完成时发送通知
- [ ] 配置可从 book.json 读取
- [ ] 通知失败不阻塞主流程

---

## Phase 5C：基础设施补全（~4 天）

### 5C-1：JSONL 审计日志（~2 天）

**产出**：
- `src/storyforge3/logging/` 模块
- 每次管线运行写一条 JSONL 记录
- 字段：timestamp, book_id, chapter_no, task, status, duration_ms, llm_calls, context_sources, audit_passed/blocking/warnings
- 日志文件：`books/{id}/runs/pipeline.jsonl`

**验收结果**（2026-06-08）：✅ 通过。6 个文件改动（logging 模块 2 + workflow + chapter_service + deps + 测试），9 个新测试全绿，310 passed / ruff clean。超越指令：实现了 perf_counter() 精确计时（指令标 duration_ms=None 可后续补充）。零整改。

### 5C-2：Service 架构对齐（~1 天）

**产出**：
- 补全 4 个缺失的 Service 实现（AuditService, TruthService, PromptService, StyleService）
- 每个服务封装现有模块功能，匹配 Protocol 定义
- deps.py 依赖注入 + Protocol 返回类型修正
- 12 个测试覆盖全部 Service + FastAPI 注入

**验收结果**（2026-06-08）：✅ 通过。8 个文件改动（4 新 Service + protocols + __init__ + deps + 测试），12 个新测试全绿，322 passed / ruff clean。StyleService 含类型安全辅助函数（超越指令）。零整改。

### 5C-3：历史快照（~1 天）

**产出**：
- 每次导出前自动创建 `books/{id}/snapshots/{timestamp}_ch{chapter_no}.zip`
- 快照包含：chapters/ + truth/ + state/ + 根目录 JSON/MD + truth.db + 全局 state.json
- `.meta.json` 记录快照元数据
- 最大保留 N 个快照（可配置），超限自动清理 zip+meta 成对
- Config 新增 `snapshot_enabled` / `snapshot_max_count`

**验收结果**（2026-06-08）：✅ 通过。4 个文件改动（snapshot.py + config + workflow + 测试），12 个新测试全绿，334 passed / ruff clean。微秒精度时间戳 + 全局文件覆盖（超越指令）。零整改。

---

## Phase 5C 完成总结

**日期**：2026-06-08
**三个子阶段全部验收通过**：

| 子阶段 | 新增文件 | 测试 | 核心交付 |
|--------|----------|------|----------|
| 5C-1 JSONL 审计日志 | 2 (logging 模块) + workflow + deps + chapter_service | 9 | PipelineLogger + 7 步管线钩子 + 非阻塞日志 |
| 5C-2 Service 架构对齐 | 4 (Audit/Truth/Prompt/Style Service) + protocols + deps | 12 | 11/11 Protocol 全部有实现 + FastAPI 注入 |
| 5C-3 历史快照 | snapshot.py + config | 12 | 导出前 zip 快照 + meta.json + 自动清理 |

**Phase 5C 终态**：334 tests，ruff clean，11/11 Service Protocol 实现，管线全链路审计日志 + 导出前快照。

---

## 未来阶段（Phase 6+）

| 阶段 | 功能 | 备注 |
|------|------|------|
| Phase 6A | Plate.js 富文本编辑器 | 替换 textarea，ANWA 验证 |
| Phase 6B | 短篇管线 | InkOS 7→5 阶段简化 |
| Phase 6C | 同人模式 | canon 导入 + 4 模式审计 |
| Phase 6D | Tauri 桌面端 | CC-Switch 技术栈复用 |
| Phase 6E | MCP Server 接口 | 外部 Agent 集成 |

---

## 技术约束

### 前端（Phase 5A）

1. **不引入 Plate.js**：Phase 1 用 textarea/CodeMirror，降低复杂度
2. **不引入 Tauri**：Phase 1 是 Web SPA，后续可封装为桌面端
3. **TypeScript strict 模式**：与 CC-Switch 一致
4. **组件 ≤300 行**：超出则拆分
5. **API 客户端从 OpenAPI spec 生成**：保持前后端类型同步
6. **中文 UI**：界面语言为中文

### 后端（Phase 5B/5C）

1. **不修改现有 API 契约**：新增端点可以，改字段需评审
2. **通知失败不阻塞主流程**：catch + log + continue
3. **新模块遵循现有模式**：Protocol → 实现 → 依赖注入 → API 路由

---

## 文件结构预览

### 前端新增

```
storyforge3/web/                       # 前端项目根
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/                          # API 客户端层
│   │   ├── client.ts                 # httpx 封装
│   │   ├── types.ts                  # 响应类型
│   │   ├── books.ts                  # Book API
│   │   ├── chapters.ts              # Chapter API
│   │   └── providers.ts             # Provider API
│   ├── components/
│   │   ├── ui/                       # shadcn/ui 组件
│   │   ├── layout/                   # 布局组件
│   │   ├── books/                    # Book 相关组件
│   │   └── chapters/                # Chapter 相关组件
│   ├── hooks/                        # 自定义 hooks
│   ├── pages/                        # 页面组件
│   │   ├── Dashboard.tsx
│   │   ├── BookList.tsx
│   │   ├── BookDetail.tsx
│   │   └── Settings.tsx
│   └── lib/                          # 工具函数
│       └── utils.ts
└── public/
```

### 后端新增

```
src/storyforge3/
├── notifications/                    # Phase 5B
│   ├── __init__.py
│   ├── protocol.py                   # NotificationChannel Protocol
│   ├── telegram.py                   # Telegram Bot
│   ├── feishu.py                     # 飞书 Webhook
│   └── wework.py                     # 企微 Webhook
├── logging/                          # Phase 5C
│   ├── __init__.py
│   └── pipeline_logger.py            # JSONL 日志
└── services/                         # Phase 5C 补全
    ├── audit_service.py              # 新增
    ├── truth_service.py              # 新增
    ├── prompt_service.py             # 新增
    └── style_service.py              # 新增
```

---

## 执行节奏

```
Day 1-3:   Phase 5A-1（Scaffold + Book List + API Client）
           Codex 独立完成，PM 验收

Day 4-7:   Phase 5A-2（Book Detail + Chapter Pipeline + SSE）
           Codex 独立完成，PM 验收

Day 8-10:  Phase 5A-3（Dashboard + Polish + Theme）
           Codex 独立完成，PM 验收

Day 11-13: Phase 5B（通知渠道）
           Codex 独立完成，PM 验收

Day 14-17: Phase 5C（JSONL + Service 对齐 + 快照）
           Codex 独立完成，PM 验收
```

---

## 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| 前端技术栈选择不当 | 低 | CC-Switch 已验证，风险低 |
| API 客户端类型不同步 | 中 | 从 OpenAPI spec 自动生成 |
| SSE 浏览器兼容性 | 低 | SSE 是标准 API，主流浏览器都支持 |
| 前端开发时间超出预期 | 中 | 拆成 3 个子阶段，每阶段独立验收 |
| 通知渠道 API 变更 | 低 | 使用各平台稳定版 Webhook API |

---

## Phase 6：从开发者工具到创作平台

### 阶段总览

| 子阶段 | 功能 | 借鉴来源 | 估算工期 |
|--------|------|----------|----------|
| 6A-1 | CodeMirror 编辑器 | CC-Switch MarkdownEditor (95%) | ~3 天 |
| 6D-1 | Tauri 桌面端 Scaffold | CC-Switch tauri.conf + lib.rs 骨架 (40%) | ~4 天 |
| 6D-2 | Tauri 桌面端 Polish | CC-Switch updater (~90%) | ~3 天 |
| 6E | MCP Server | Letta MCP 客户端 (50%) | ~8 天 |
| 6C | 同人模式 | InkOS FanficCanonImporter (~70%) | ~4 天 |
| 6B | 短篇管线 | 无现成代码 (10%) | ~10 天 |

### 6A-1：CodeMirror 编辑器（~3 天）

**验收结果**（2026-06-09）：✅ 通过。ChapterEditor.tsx (124行) 从 CC-Switch MarkdownEditor.tsx (159行) 移植。5 个前端测试全绿，334 后端 tests 不退步，ruff clean，pnpm build 零错误。超越指令：countChineseChars 提取为共享工具函数，测试用 vi.hoisted() 完整 mock CodeMirror。

### 6D-1：Tauri 桌面端 Scaffold（~4 天）

**验收结果**（2026-06-09）：✅ 通过。180 行 Rust（lib.rs + process_manager.rs + tray.rs），7 个 Tauri 插件（含 single-instance、window-state），前端 tauriBootstrap.ts + resolveApiUrl() 双模式。4 Rust tests，23 前端 tests，335 后端 tests 全绿，ruff/cargo clean。

### 6D-2：Tauri 桌面端 Polish（~3 天）

**验收结果**（2026-06-09）：✅ 通过。三项功能交付：

1. **自动更新**：`updater.ts`（93 行）+ `UpdateContext.tsx`（131 行）+ `UpdateBanner.tsx`（59 行）从 CC-Switch 移植简化。Rust 侧注册 `tauri-plugin-updater`，endpoint 指向 `pengqiyu123/storyforge3`。前端 2 秒后自动检查，支持下载进度条 + 忽略版本 + 重启。
2. **启动错误 UI**：`StartupErrorScreen.tsx`（53 行）。Python 启动/健康检查失败时 Rust emit `python-startup-error` 事件，前端展示错误页含重试 + 查看日志按钮。`tauriBootstrap.ts` 扩展为 error 状态机（sessionStorage + CustomEvent）。
3. **原生导出对话框**：`exportChapterDesktop()` 集成到 `ChapterPipeline.tsx`。Tauri 模式弹系统保存框（`@tauri-apps/plugin-dialog`），写入用户选择路径；Web 模式保持原行为。

新增 `capabilities/default.json` 统一权限声明（updater/dialog/fs/opener/process/store/window-state）。

**测试**：34 前端 tests（+11 新增），4 Rust tests，335 后端 tests 全绿。ruff clean，cargo clippy/fmt/build clean。

**指令文件**：`docs/directives/directive-6d-2.md`

### 6C：同人模式（~4 天）

**验收结果**（2026-06-09）：✅ 通过。三项功能交付：

1. **Canon 导入**：`FanficService`（197 行）从 InkOS `fanfic-canon-importer.ts`（146 行）移植。提示模板（54 行 systemPrompt）100% 复制。Section 解析用 `re.finditer` 替代多次 `re.match`（更 Pythonic）。50k 字符截断 + fanfic_canon.md + fanfic_canon.json 双格式持久化。3 个 API 端点（import/get/refresh）。
2. **同人审计维度**：`dimensions.py`（78 行）从 InkOS `fanfic-dimensions.ts`（88 行）移植。4 维度（34-37）+ severity 映射表 100% 复制。`ChapterService` 和 `AuditService` 均通过 `_fanfic_audit_context()` 注入同人审计上下文，非同人书完全不受影响。
3. **提示注入**：`prompt_sections.py`（101 行）从 InkOS `fanfic-prompt-sections.ts`（110 行）移植。MODE_PREAMBLES + MODE_CHECKS + 角色语音表格提取 100% 复制。`ChapterService.draft()` 注入 fanfic_canon + voice_profiles + mode_instructions。

数据模型：`FanficMode` enum + `FanficCanon` dataclass + `BookConfig.fanfic_mode` 字段。不修改 Character 模型——同人角色档案作为只读参考存在 canon 中。

**测试**：20 个新增 fanfic tests（service 6 + dimensions 5 + prompt_sections 4 + API 5），358 后端 tests 全绿（+23 新增），34 前端 tests 不退步，ruff clean。

**指令文件**：`docs/directives/directive-6c.md`

### 6B-1：短篇管线后端（~5 天）

**验收结果**（2026-06-09）：✅ 通过。核心交付：

1. **数据模型**：`ShortStoryStatus`（6 状态 EMPTY→EXPORTED）+ `ShortStoryConfig` + `ShortStoryMeta` + `ShortStoryPlan` + `ShortStoryResult`。现有长篇模型零改动。
2. **ShortStoryService**（445 行）：完整 5 步管线 plan→draft→audit→revise→export。`draft()` 在 target_chars > 8000 时使用 `ChunkedGenerator` 分段生成。`audit()` 复用 AuditRunner 36 机械规则 + LLMAuditor 4 维度（零新代码）。`revise()` 固定 patch 模式，最多 1 轮。`export()` 支持 tomato_txt/txt/md/epub/qidian_txt 5 格式单文件导出。`run_full_pipeline()` 一键运行全流程。
3. **Prompt 模板**：`short-plan-v1` + `short-draft-v1` 注册到 PromptRegistry。模板内容参照指令规格，含 AI 告警词和叙事节奏要求。
4. **API 路由**（236 行）：8 个端点（create/get/plan/draft/audit/revise/export/run）独立前缀 `/api/short-stories`。404 信封 + 参数验证 + 错误处理完整。
5. **Protocol + DI**：`ShortStoryServiceProtocol` 加入 protocols.py，`get_short_story_service()` 加入 deps.py，路由注册到 app.py。

文件隔离：`short_story.json / short_plan.json / short_text.md / exports/short.*` 与长篇文件互不干扰。

**测试**：9 个 service tests + 5 个 API tests（14 新增），372 后端 tests 全绿（+14 新增），34 前端 tests 不退步。ruff check clean。

**指令文件**：`docs/directives/directive-6b-1.md`

### 6B-2：短篇管线前端 + 前端 API 补齐（~3 天）

**验收结果**（2026-06-09）：✅ 通过。三部分交付：

1. **短篇前端页面**：`/shorts` 列表页（ShortsPage + ShortList + ShortCard）+ `/shorts/:id` 详情页（ShortDetailPage + ShortPipeline）。ShortPipeline 5 步（构思→起草→审计→修订→导出）+ 一键运行 + 格式选择 + 审计结果面板 + 正文预览复用 ChapterEditor（readOnly）。CreateShortDialog 含 title/genre/target_chars(5000-20000)/premise/style。侧边栏添加"短篇"导航（FileText 图标）。

2. **短篇前端 API + hooks**：`api/shorts.ts`（8 端点）+ `hooks/useShorts.ts`（list/get/create/plan/draft/audit/revise/export/run hooks）。后端补充 `GET /api/short-stories` 列表端点（`list_stories()` + 路由 + Protocol）。

3. **前端 API 缺口补齐**：`fanfic.ts`（3 函数 + TypeScript 类型）+ `daemon.ts`（1 函数 + DaemonStartRequest 类型）+ `exports.ts`（2 函数）。`chapters.ts` 补 `llmAudit` + `normalize`。`truth.ts` 补 `extract`。

**测试**：374 后端 tests（+2 新增列表测试），39 前端 tests（+5 新增：shorts API 2 + ShortPipeline 2 + CreateShortDialog 1）。ruff clean，pnpm build clean。

**指令文件**：`docs/directives/directive-6b-2.md`

### 6E-1：MCP Server 基础框架（~4 天）

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **MCP Server 框架**：`mcp/server.py`（31 行）使用 FastMCP（`mcp>=1.20`，本地安装 1.27.2）。`create_server()` 一次性组装 BookService + ChapterService（含 PipelineLogger）+ ExportService，闭包注入 tool 函数。`FastMCP("StoryForge")` + 中文 instructions。
2. **5 个核心 Tool**（`mcp/tools.py`，145 行）：`list_books` → `BookInfo[]`，`get_book(book_id)` → `BookInfo`（不存在 raise ValueError），`draft_chapter(book_id, chapter_no)` → plan + draft 全文，`audit_chapter(book_id, chapter_no)` → `AuditSummary`，`export_book(book_id, fmt)` → `ExportResult`。每个 tool 有中文 docstring + 参数说明。Pydantic 输出模型提供 structuredContent + text 双通道。
3. **CLI 入口**：`storyforge3 mcp`（__main__.py:94, 109-113）+ `python -m storyforge3.mcp`（mcp/__main__.py）。两者都调用 `create_server().run(transport="stdio")`。
4. **独立 tool 函数**：Codex 将 tool 逻辑提取为 `list_books_tool()` 等 5 个独立 async 函数（tools.py:43-89），`@mcp.tool()` 装饰的函数只做参数解包和调用。这使得测试无需 FastMCP 上下文。

**测试**：8 个 MCP 测试（7 个 tool 逻辑测试 + 1 个注册验证测试）+ 1 个 CLI 测试。383 后端 tests（+9 vs 6B-2）。39 前端 tests 不退步。ruff clean。

**指令文件**：`docs/directives/directive-6e-1.md`

### 6E-2：MCP Server 工具扩展（~4 天）

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **10 个新 tool**（从 5 → 15）：Tier 1 长篇管线补充（`create_book` / `plan_chapter` / `revise_chapter` / `get_chapter_status`），Tier 2 世界观+角色（`build_world` / `create_character` / `list_characters`），Tier 3 短篇管线（`run_short_story` / `get_short_story_status`），Tier 4 Truth 查询（`get_truth`）。
2. **服务组装扩展**：`server.py` 新增 `WorldService` + `CharacterService`（各独立 LLM 实例）+ `ShortStoryService` + `TruthService`。`register_tools()` 签名从 4 → 8 个 service 依赖。
3. **代码优化**：Codex 提取了 `_book_info()` / `_chapter_status_info()` / `_character_info()` / `_short_story_status_info()` 4 个辅助函数（tools.py:401-440），消除了重复的 model → Pydantic 转换代码。

**测试**：20 个 MCP 测试（+12 新增：13 个 tool 逻辑 + 1 个注册验证，每个新 tool 至少 1 个测试）。395 后端 tests（+12 vs 6E-1）。39 前端 tests 不退步。ruff clean。

**指令文件**：`docs/directives/directive-6e-2.md`

---

## Phase 7 路线图：写作工作台 + 质量运营 + MCP 实战化 + 打包发布

> 创建日期：2026-06-10
> 前置里程碑：Phase 6 完成（438 tests: 395 后端 + 39 前端 + 4 Rust）

### 战略目标

Phase 1-6 构建了完整的后端引擎 + 前端 MVP + 桌面端 + MCP 集成。**Phase 7 将前端从"管线控制台"升级为"写作工作台"，同时推进 MCP 实战化和打包发布。**

详细规划见 `docs/roadmap/phase7.md`。

### 7A-1：章节编辑 + 保存（~3 天）

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **后端 `update_text()`**（chapter_service.py:177-197）：接收 `text` + `expected_hash`（SHA-256 前 8 位乐观锁）。空章节拒绝写入（409 `CHAPTER_EMPTY`），hash 不匹配拒绝覆盖（409 `CONTENT_CONFLICT`）。保存后状态转 `NEEDS_REVIEW`（`force_needs_review(reason="manual_edit")`）。`_content_fingerprint()` 作为模块级私有函数（line 385-386）。
2. **PUT API**（routes/chapters.py:267-285）：`UpdateTextRequest(text, expected_hash)` + 标准 404/409 错误映射。`GET /status` 返回新增 `text`/`content_hash`/`actual_chars` 字段（`_result_to_response()` line 167-177）。
3. **Protocol 更新**：`ChapterServiceProtocol` 新增 `update_text(book_id, chapter_no, text, *, expected_hash)` 签名（line 180-187）。
4. **前端编辑模式**：`ChapterPipeline` 新增 `editing`/`editText` 状态，编辑按钮触发编辑模式，ChapterEditor 切换 `readOnly={!editing}` + `onChange`。底部操作栏含"放弃修改"和"保存 (Ctrl+S)"按钮。脏状态橙色提示"未保存的修改"。
5. **前端 API + Hook**：`chaptersApi.updateText` PUT 函数 + `useChapterUpdateText` mutation（成功后 invalidate chapterStatus 缓存）。`ChapterResult` 接口新增 `content_hash`/`actual_chars`。
6. **Ctrl/Cmd+S**：编辑模式下全局 keydown 监听，preventDefault + 触发保存。冲突时 toast 提示"内容已被修改"。

**测试**：403 后端 tests（+8 vs 395：3 service + 5 API），44 前端 tests（+5 vs 39：API 1 + hook 1 + ChapterPipeline 3）。ruff clean，pnpm build clean。

**指令文件**：`docs/directives/directive-7a-1.md`

### 7A-2：审计问题定位 + 编辑器高亮（~3 天）

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **后端定位信息**：9 条段落相关机械审计规则在失败 detail 中返回 `paragraph_indices` + `snippet`，包括 `golden_three_hook`、`cliffhanger_presence`、`info_dump`、`max_paragraph_length`、`pacing_flat`、`repeated_phrase`、`forbidden_patterns`、`internal_engine_terms`、`unbalanced_quote_or_bracket`。密度型规则保持无定位字段。
2. **API 响应增强**：`AuditResponse` 新增 `rule_results`，每条规则返回 `rule_id`、`passed`、`severity`、`category`、`message`、`detail`。severity/category 以大写 enum 名输出，便于前端直接分色。
3. **前端定位闭环**：`AuditResultPanel` 对可定位失败项显示 MapPin、snippet 和点击态；`ChapterEditor` 用 CodeMirror Decoration 支持 BLOCKING 红色、WARNING 黄色高亮并滚动到字符偏移；`ChapterPipeline` 将后端段落索引转换为字符范围，点击审计项即可定位正文。
4. **优雅降级**：无 `paragraph_indices` 的规则不可点击、不显示定位图标；新管线操作、进入编辑、保存/放弃编辑都会清除旧高亮。

**测试**：406 后端 tests（+3 vs 7A-1），47 前端 tests（+3 vs 7A-1），ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线，本轮环境未安装 `cargo`，未复跑。

**指令文件**：`docs/directives/directive-7a-2.md`

**核心交付**：
1. 后端 ~10 条段落相关规则在 detail 中增加 `paragraph_indices` + `snippet`
2. `AuditResponse` 新增 `rule_results`（含定位信息）
3. 前端 `AuditResultPanel` 点击问题 → `ChapterEditor` 段落高亮 + 滚动定位
4. 无定位信息的规则优雅降级为不可点击

### 7A-3：修订 Diff 展示（~2 天）

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **真实 revise 落地**：`ChapterService.revise()` 不再只返回 `revision_mode=...` 占位结果，而是复用 `ChapterWorkflow.step_revise()` 执行真实修订，并写回章节正文。
2. **修订前快照**：LLM 修订和人工 `update_text()` 保存前都写入 `{chapter_no}.before.md`，为 7B 版本回滚预留基础设施。
3. **段落级 diff 数据面**：新增 `RevisionDiff` / `RevisionDiffSummary` / `RevisionDiffBlock` 数据模型，以及 `audit/revision_diff.py` 中基于 `split_paragraphs()` + `difflib.SequenceMatcher` 的 `build_revision_diff()`。
4. **API 响应增强**：`ChapterStatusResponse` 新增可选 `revision_diff`，`POST /revise` 返回完整 diff summary + replace/insert/delete blocks。
5. **前端可视化**：新增 `RevisionDiffPanel` 左右对比面板；`ChapterPipeline` 在修订成功后自动展示 diff，并在 plan/draft/audit/approve/export、进入编辑、保存/放弃编辑时清除旧 diff。

**测试**：412 后端 tests（+6 vs 7A-2），50 前端 tests（+3 vs 7A-2），ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线，本轮环境未安装 `cargo`，未复跑。

**指令文件**：`docs/directives/directive-7a-3.md`

### 7B-1：Truth 可视化面板（~3 天）

**状态**：⬜ 指令已发出

**核心交付**：
1. `TruthStore.load_history()` + `GET /truth/history` 全章 truth 列表端点
2. `TruthPanel` 组件：按章节分组展示 6 类 truth 数据（事实/角色/关系/钩子/不可逆/备注）
3. 章节标签栏切换 + 搜索过滤
4. `BookDetailPage` 新增"真相"tab

**指令文件**：`docs/directives/directive-7b-1.md`

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **后端 history 链路**：`TruthStore.load_history()` 按章节升序返回全部 truth 数据；`GET /truth/history` 端点在 `/{chapter_no}` 之前注册（line 41 vs line 50）。
2. **前端 TruthPanel**：按章节分组展示 6 类 truth（事实断言/角色更新/关系更新/钩子/不可逆事实/备注），不可逆事实最高优先高亮。章节标签栏切换 + 搜索过滤。
3. **BookDetailPage**：新增"真相"tab（第 6 个 tab）。
4. **Hooks**：`useTruthHistory` + `useTruthByChapter`。

**测试**：416 后端 tests（+4 vs 7A-3：load_history + history API），53 前端 tests（+3 vs 7A-3：TruthPanel 2 + truth API 1）。ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线。

### 7B-2：快照管理 + 回滚（~2 天）

**状态**：⬜ 指令已发出

**核心交付**：
1. `SnapshotManager.restore_snapshot()` 白名单恢复（chapters/ + state/）+ zip slip 防护
2. `GET /snapshots` 列表 + `POST /snapshots/{path}/restore` 回滚 API
3. `SnapshotPanel` 组件：快照列表 + 确认回滚对话框
4. `BookDetailPage` 新增"快照"tab

**指令文件**：`docs/directives/directive-7b-2.md`

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **`SnapshotManager.restore_snapshot()`**：白名单只恢复 `chapters/` + `state/`，三重安全过滤（`..` 路径跳过 + 绝对路径跳过 + resolve 相对路径验证），原子写入 tmp+rename。
2. **`GET /snapshots` + `POST /snapshots/{path}/restore`**：路由注册到 `app.py`，404 处理快照不存在。
3. **前端 `SnapshotPanel`**：从 CC-Switch `BackupListSection` 移植骨架（列表 + 确认回滚 Dialog + toast），`BookDetailPage` 新增"快照"tab（第 7 个 tab）。
4. **`useSnapshotList` + `useSnapshotRestore`** hooks，回滚成功后 invalidate chapter-status + truth-history 缓存。

**测试**：422 后端 tests（+6 vs 7B-1：restore + 白名单 + API），56 前端 tests（+3 vs 7B-1：SnapshotPanel + snapshots API + BookDetailPage tab）。ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线。

### 7B-3：导出预览（~1 天）

**状态**：⬜ 指令已发出

**核心交付**：
1. `GET /{chapter_no}/export-preview?fmt=` 预览端点（复用现有格式化器，不写文件）
2. `ExportPreviewDialog` 组件（格式下拉 + 只读预览 + 格式错误提示 + 复制/下载）
3. `ChapterPipeline` 新增"预览"按钮入口

**指令文件**：`docs/directives/directive-7b-3.md`

**验收结果**（2026-06-10）：✅ 通过。核心交付：

1. **`GET /export-preview?fmt=`**：支持 tomato_txt/markdown/qidian_txt 三种格式，纯内存格式化不写文件，番茄格式带 `format_errors`。
2. **`ExportPreviewDialog`**：格式下拉 + 只读预览 + 格式错误提示 + 复制全文 + 导出下载按钮。
3. **`ChapterPipeline`** 新增"预览"按钮入口。

**测试**：432 后端 tests（+10 vs 7B-2：preview API 各格式 + 错误格式 + 章节不存在），59 前端 tests（+3 vs 7B-2：ExportPreviewDialog + API + Pipeline 入口）。ruff clean，pnpm build clean（仅 Vite/CodeMirror chunk size 警告）。Rust 4 tests 为既有基线。
