# StoryForge3 项目发展战略分析

> 产品经理：Claude Code PM
> 日期：2026-06-11
> 版本：v1.0
> 输入源：[评估.md](../../评估.md)、[豆包意见.md](../../豆包意见.md)、代码库实地验证
> ⚠️ **时效性（2026-06-14 审核）：部分过期。** 此处规划的后续路线（dogfood→10B）已被 P0.5 + P1（agent-mode ONLY + RunRecord）取代。战略背景仍有效，执行路线以 `current.md` / `next.md` 为准。
> 基线：486 后端 tests / 62 前端 tests / ruff clean / pnpm build clean

---

## 一、战略定位

### 一句话定位

**StoryForge3 是 AI Native 中文网文全流程生产工作台**——从灵感输入到平台可发布章节，覆盖世界观构建、角色生成、卷纲规划、章节起草、审计修订、真相提取和多格式导出的完整创作链路。

### 差异化锚点

| 锚点 | 说明 | 竞品对比 |
|------|------|---------|
| **Truth 连续性系统** | SQLite + JSON 备份，跨章事实追踪，6 类结构化 truth，可视化面板 | novelWriter 有交叉引用、AI-Novel-Writing-Assistant 有 RAG，但无 Truth 这种结构化事实层 |
| **36 条机械审计** | 确定性质量门禁，不依赖 LLM 判断，段落级定位 + 编辑器高亮 | snowflake-fiction 有质量规则但无确定性审计；竞品全靠 LLM 审查 |
| **MCP 15-tool 集成** | 外部 AI Agent 可直接调用创作管线，`next_step` 引导 + 操作类型标注 | 唯一提供 MCP Server 的中文网文创作系统 |
| **多智能体工程纪律** | 31 份指令文档 + PM↔Codex 验收闭环 + 借鉴评估四档分类 | 个人项目中罕见的工程化水准 |

### 竞品站位

```text
                    工程化程度
                        ▲
                        │
    StoryForge3 ●       │
    （全栈+Truth+审计+MCP）│
                        │
    AI-Novel-Writing ●  │   ● snowflake-fiction
    （RAG+自动导演）      │   （方法论颗粒度最细）
                        │
                        │   ● 91Writing
                        │   （中文新手UI）
                        │
    ────────────────────┼──────────────► AI 原生程度
    novelWriter         │
    manuskript          │
    （传统写作工具）      │
```

**结论**：StoryForge3 占据"工程化程度最高"的位置。下一阶段目标是向右移动（更强的 AI 自动化），同时保持工程化优势。

---

## 二、当前优势（4 项核心壁垒）

### 优势 1：管线端到端闭环

**事实**：14 个管线环节中 13 个前后端全覆盖，14 Service Protocol 全部有实现。

**代码证据**：
- `src/storyforge3/api/app.py` 注册 15 个路由模块
- `src/storyforge3/services/protocols.py` 定义 14 个 Protocol
- `src/storyforge3/workflow.py` 实现完整状态机（EMPTY → PLANNED → DRAFTED → AUDITED → REVISED → APPROVED → EXPORTED）
- E2E 验证：3 章节全链路成功（2255/2706/2940 字，171 条 truth）

### 优势 2：确定性审计体系

**事实**：36 条机械审计规则 + 4 维度 LLM 审计 + 5 种修订模式。

**代码证据**：
- `src/storyforge3/audit/runner.py`：36 条规则
- `src/storyforge3/audit/llm_auditor.py`：OOC/战力/信息边界/情节逻辑 4 维度
- `src/storyforge3/audit/revision_modes.py`：polish/spot_fix/anti_detect/surgical/rework + `RevisionModeRecommender`
- 前端：段落级定位 + CodeMirror 高亮 + 修订前后 Diff 面板

### 优势 3：Truth 连续性系统

**事实**：SQLite 结构化事实存储 + 关键词检索 + 6 类分类 + 可视化面板。

**代码证据**：
- `src/storyforge3/truth/store.py`：SQLite `truth_entries` + JSON 备份
- `src/storyforge3/truth/retriever.py`：复合评分（importance × category_weight + recent_bonus），12000 字上下文预算
- `src/storyforge3/truth/extractor.py`：6 类提取（plot_point/character_event/relationship/world_rule/hook/ability）
- 前端：`TruthPanel` 按章分组 + 不可逆事实高亮 + 搜索过滤

### 优势 4：开放集成能力

**事实**：MCP Server 15 tool + CC-Switch 双层 Provider 路由 + Tauri 桌面壳 + PyInstaller sidecar。

**代码证据**：
- `src/storyforge3/mcp/server.py`：15 个 tool + `MCP_INSTRUCTIONS` 工作流说明
- `src/storyforge3/llm/llm_service.py`：支持 OpenAI Chat/Responses、Anthropic Messages、Gemini Native 4 种协议
- `src-tauri/`：sidecar-first/venv-fallback 双模式启动

---

## 三、关键短板（5 项）

### 短板 1：产品验证空白（P0 — 阻塞项）

| 维度 | 评估 |
|------|------|
| **现状** | dogfood-protocol.md 已写好，E2E 脚本跑过 test books 10 次，但《我是路人甲》零真实创作记录 |
| **影响** | 无法回答"系统到底能不能产出可读章节"这个根本问题；所有代码质量指标都无法替代真实输出验证 |
| **用户价值** | ★★★★★ — 不验证就无法建立产品可信度 |
| **技术可行性** | ★★★★★ — 协议完备、基础设施就绪、provider 可用 |
| **工作量** | 1 天执行 + 1 天分析记录 |

### 短板 2：长操作无反馈（P1 — 体验最大痛点）

| 维度 | 评估 |
|------|------|
| **现状** | SSE 基础设施已存在（SSEManager + 5 种事件类型），但 LLM 服务不支持流式输出，ChunkedGenerator 无进度信号，用户等待 3-5 分钟只看到 loading |
| **影响** | 起草/修订等长操作无 token 级反馈，用户焦虑、误以为卡死、重复点击 |
| **用户价值** | ★★★★★ — 从"能用"到"好用"的关键跨越 |
| **技术可行性** | ★★★☆☆ — LLM 服务改造影响面大（所有调用方），需要审慎设计 |
| **工作量** | 后端 5-7 天（LLM streaming + 进度事件 + SSE 桥接），前端 2-3 天（进度 UI） |

**技术细节**：
- `llm_service.py:generate_text()` 当前用 `await client.post()` 等完整响应
- 需改为 `stream=True` + 逐 token 回调
- `chunked_generator.py` 需在每 chunk 完成时发 `pipeline:progress` 事件
- `pipeline_logger.py` 的 JSONL 记录需桥接到 SSE 实时推送

### 短板 3：自动导演缺失（P1 — 用户价值最高）

| 维度 | 评估 |
|------|------|
| **现状** | DaemonService.run_batch() 已有顺序批处理，但无端到端编排（灵感→全书），无书籍级状态机，无 checkpoint/resume |
| **影响** | 用户必须手动 6 步（世界→角色→卷纲→plan→draft→audit），无法"一键开书" |
| **用户价值** | ★★★★★ — AI-Novel-Writing-Assistant 的核心差异化功能 |
| **技术可行性** | ★★★★☆ — 所有构建块已存在，核心是编排层开发 |
| **工作量** | 4-6 周（编排服务 + 书籍状态机 + idea 解析 + 错误恢复） |

**技术细节**：
- 11 个独立 Service 已全部实现，全部 async + Protocol 约束
- 缺失：`AutoDirectorService`（灵感解析 + 链式调用）、`BookStateMachine`（INCUBATING → OUTLINING → ACTIVE → COMPLETED）、checkpoint/resume
- 借鉴来源：`storyforge/process/AI-Novel-Writing-Assistant/` 的自动导演流程

### 短板 4：RAG 能力缺失（P1 — 但非当务之急）

| 维度 | 评估 |
|------|------|
| **现状** | Truth 系统用关键词检索（SQL LIKE + 中文 n-gram），对单书管线够用，但无语义搜索、无外部知识库、无跨书参考 |
| **影响** | 长篇（50+ 章）可能出现语义相关但关键词不匹配的召回遗漏；同人模式无法做 canon 语义检索 |
| **用户价值** | ★★★★☆ — 长篇连续性和同人模式的刚需 |
| **技术可行性** | ★★★☆☆ — 需引入 Qdrant + embedding API，基础设施成本高 |
| **工作量** | 6-8 周（基础设施 + 索引管线 + 检索集成 + 评估体系） |

**与 Truth 的关系**：Truth 解决"发生了什么"的结构化事实检索，RAG 解决"什么是相关的"的语义检索。两者互补而非替代。

**关键判断**：当前阶段应先**优化 Truth 检索质量**（改进中文分词、加入章节距离衰减、增加召回数量），RAG 作为后期增强。理由：
1. 单书 10-30 章场景，Truth 12000 字上下文预算已覆盖关键事实
2. 引入 Qdrant 增加部署复杂度，与"本地单用户"定位有张力
3. AI-Novel-Writing-Assistant 的 RAG 适合多书/大规模场景，SF3 当前聚焦单书创作

### 短板 5：前端体验不完整（P1 — 功能覆盖 + 编辑器）

| 维度 | 评估 |
|------|------|
| **现状** | 前端 API 覆盖率 ~40%，同人模式/daemon/独立导出模块前端不可达；CodeMirror 无专注/打字机模式 |
| **影响** | 用户无法从 Web UI 使用全部后端能力；编辑器体验不如通用 Markdown 编辑器 |
| **用户价值** | ★★★☆☆ — 功能可用但体验粗糙 |
| **技术可行性** | ★★★★☆ — 前端 API 补齐是模式化工作 |
| **工作量** | 2-3 周（API 补齐 7 天 + 编辑器增强 7 天 + 同人 UI 5 天） |

---

## 四、阶段目标与战略路径

### 核心战略结论

> **先做真实 dogfood、长任务可观察化、自动导演最小闭环，再推进 RAG、写作方法论和产品化体验。**

**路径验证**：

```
Phase A: 验证期（2-3 周）          Phase B: 核心突破（4-6 周）        Phase C: 差异化增强（8-12 周）
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│ Dogfood 真实创作验证      │      │ 自动导演 MVP              │      │ RAG 语义检索             │
│ （P0，阻塞一切后续决策）   │ ───► │ （从灵感到前 3 章全自动）   │ ───► │ （Qdrant + embedding）   │
│                         │      │                         │      │                         │
│ 长任务可观察化            │      │ 书籍级状态机              │      │ 写作方法论增强            │
│ （SSE 进度 + LLM 流式）   │      │ （checkpoint/resume）     │      │ （雪花法 + 钩子 + 节奏）   │
│                         │      │                         │      │                         │
│ 覆盖率基线 + ADR 启用     │      │ 错误恢复 + 重试策略        │      │ 产品化体验               │
│ （文档治理）              │      │                         │      │ （编辑器 + 同人 UI）       │
└─────────────────────────┘      └─────────────────────────┘      └─────────────────────────┘
```

**为什么这个顺序是科学的**：

1. **Dogfood 在最前面**：未经验证的系统不应该投入更多功能开发。真实创作验证会暴露出管线中的真实问题（prompt 质量、审计误判率、上下文遗漏），这些问题直接影响后续自动导演和 RAG 的设计决策。先跑真实数据，再决定往哪投入。
2. **可观察化紧随其后**：自动导演意味着系统自主运行 10+ 步骤，用户必须能实时看到进度。没有可观察化的自动导演是黑盒——出了问题用户无从诊断。同时，流式输出是用户体验最大的单点提升。
3. **自动导演是核心突破**：验证通过 + 可观察化就绪后，自动导演将 StoryForge3 从"手动工具"升级为"AI 驱动的工作流"。这是与 AI-Novel-Writing-Assistant 对标的关键能力。
4. **RAG/方法论/产品化放后面**：这些是增强层，不改变核心工作流。RAG 需要 Truth 先跑出真实数据（才能评估召回质量），方法论需要真实 dogfood 反馈（才能知道哪些规则真正有用），产品化需要功能稳定后再打磨。

---

## 五、优先级总表

### 评分标准

- **用户价值**：5 = 无此功能产品不可用，1 = 锦上添花
- **技术可行性**：5 = 现有代码可直接复用，1 = 需要全新技术栈
- **工作量**：5 = ≤3 天，1 = ≥8 周
- **综合分** = 用户价值 × 0.4 + 技术可行性 × 0.3 + 工作量(反向) × 0.3

### P0：阻塞项（立即执行）

| # | 工作项 | 用户价值 | 技术可行性 | 工作量 | 综合分 | 阶段归属 |
|---|--------|---------|-----------|--------|--------|---------|
| 1 | 执行真实 Dogfood（《我是路人甲》≥1 章） | 5 | 5 | 5 | **5.0** | Phase A |
| 2 | 补充 pytest --cov 覆盖率基线 | 3 | 5 | 5 | **4.1** | Phase A |

### P1：短期补强（Phase A-B）

| # | 工作项 | 用户价值 | 技术可行性 | 工作量 | 综合分 | 阶段归属 |
|---|--------|---------|-----------|--------|--------|---------|
| 3 | LLM 流式输出 + SSE 进度推送 | 5 | 3 | 2 | **3.5** | Phase A |
| 4 | ChunkedGenerator 进度事件 | 4 | 4 | 4 | **4.0** | Phase A |
| 5 | 拆分 project-status 文档 | 2 | 5 | 5 | **3.8** | Phase A |
| 6 | 启用 ADR（≥5 个关键决策） | 3 | 5 | 5 | **4.1** | Phase A |
| 7 | 自动导演编排服务（灵感→前 3 章） | 5 | 4 | 2 | **3.8** | Phase B |
| 8 | 书籍级状态机（checkpoint/resume） | 4 | 4 | 3 | **3.7** | Phase B |
| 9 | 前端 API 覆盖补齐至 70% | 3 | 4 | 3 | **3.3** | Phase B |
| 10 | 性能 Benchmark 体系 | 3 | 4 | 3 | **3.3** | Phase B |

### P2：中期方向（Phase C）

| # | 工作项 | 用户价值 | 技术可行性 | 工作量 | 综合分 | 阶段归属 |
|---|--------|---------|-----------|--------|--------|---------|
| 11 | RAG 知识库（Qdrant + embedding） | 4 | 2 | 1 | **2.3** | Phase C |
| 12 | 写作方法论增强（雪花法 + 钩子 + 节奏） | 4 | 3 | 2 | **3.1** | Phase C |
| 13 | 编辑器体验升级（专注/打字机/预览） | 3 | 4 | 3 | **3.3** | Phase C |
| 14 | 同人模式前端 UI | 3 | 4 | 4 | **3.6** | Phase C |
| 15 | Truth 检索优化（分词 + 衰减 + 召回量） | 3 | 4 | 3 | **3.3** | Phase C |
| 16 | 传统写作管理（场景树/卡片视图） | 2 | 3 | 2 | **2.3** | Phase C |

---

## 六、实施路径

### Phase A：验证期（2-3 周）

#### A-1：真实 Dogfood 验证（1-2 天）

**交付件**：
- 执行 `docs/dogfood-protocol.md` 完整流程，写《我是路人甲》≥1 章
- 填写评分表（启动流畅度/规划质量/草稿质量/审计准确度/修订效果/UI体验/成本/总体可用性）
- 问题列表（阻断/严重/一般）
- 全流程耗时和 token 消耗记录

**验收标准**：
- [ ] 至少 1 章完整走通 plan → draft → audit → truth → export
- [ ] 评分表 8 维度均有数字
- [ ] 问题列表 ≥3 条（如果少于 3 条，说明测试不够严格）
- [ ] 最终判定为"可继续使用"或"需要修复后再用"

**借鉴来源**：
- `scripts/e2e_test.py`（RecordingLLM + 成本追踪模式）
- `scripts/e2e_multi_chapter.py`（多章 E2E + resume 模式）

#### A-2：长任务可观察化（5-7 天后端 + 2-3 天前端）

**后端交付件**：
1. `llm_service.py` 新增 `generate_text_stream()` 方法，返回 `AsyncIterator[str]`
2. `chunked_generator.py` 在每 chunk 完成时通过回调发 `pipeline:progress` 事件
3. `pipeline_logger.py` 桥接到 SSE，实时推送 JSONL 记录
4. 章节路由使用新流式方法，保持 `generate_text()` 不变（向后兼容）

**前端交付件**：
1. `ChapterPipeline` 组件监听 SSE progress 事件
2. 进度条 UI：`正在生成... 已输出 N 字` 或 `正在生成第 K/N 段`
3. 错误状态展示改进（超时/重试次数/provider 错误详情）

**验收标准**：
- [ ] draft/revise 操作期间前端实时显示进度
- [ ] ChunkedGenerator 每完成一段推送一次进度
- [ ] 超时和重试事件前端可见
- [ ] 现有 486 后端测试 + 62 前端测试不退步
- [ ] 新增 ≥5 个测试（流式输出 + 进度事件 + SSE 桥接）

**借鉴来源**：
- CC-Switch `cc-switch-main/` 的 SSE 实时推送模式
- AI-Novel-Writing-Assistant 的 job queue 进度追踪（7 阶段状态机）

#### A-3：文档治理（2-3 天）

**交付件**：
1. 拆分旧状态文档 → `docs/current.md` + `docs/history.md` + `docs/next.md`
2. 补写 ≥5 个 ADR 到 `docs/adr/ADR-*.md`
3. `pytest --cov` 覆盖率基线记录到 `docs/current.md`

**验收标准**：
- [ ] 三个文档各自 <200 行
- [ ] ADR 目录 ≥5 个文件
- [ ] 覆盖率数字已记录

---

### Phase B：核心突破（4-6 周）

#### B-1：自动导演 MVP（4-5 周）

**交付件**：
1. `AutoDirectorService`：接收灵感字符串 → 解析 BookConfig → 链式调用所有 Service → 输出前 3 章
2. `BookStateMachine`：INCUBATING → OUTLINING → ACTIVE → COMPLETED + checkpoint/resume
3. `POST /api/books/auto-create` 端点
4. MCP tool `auto_create_book`
5. 前端"一键开书"向导 UI

**核心流程**：
```
用户输入："都市校园 + 超能力觉醒 + 存在感系统"
    │
    ▼ LLM 解析
BookConfig(title, genre, platform, target_chapters, ...)
    │
    ▼ AutoDirectorService 链式调用
WorldService.build() → CharacterService.create_batch() → VolumeService.plan()
    │
    ▼ 循环前 N 章
ChapterWorkflow.run() × N（含 audit + revise + truth + export）
    │
    ▼ 输出
BookResult(book_id, chapters[], truth_count, audit_summary, export_paths)
```

**验收标准**：
- [ ] 一条灵感到 3 章可发布章节，全程无人工干预
- [ ] 任意步骤失败可从 checkpoint 恢复
- [ ] 全程 SSE 进度可见
- [ ] 真实 provider 端到端验证通过
- [ ] ≥10 个新测试

**借鉴来源**：
- `storyforge/process/AI-Novel-Writing-Assistant/` 的自动导演流程（直接参考编排逻辑）
- 现有 `DaemonService.run_batch()` 的批处理模式（骨架移植）
- 现有 `ChapterWorkflow.run()` 的状态机模式（模式复用）

#### B-2：前端 API 覆盖 + 体验补齐（1-2 周）

**交付件**：
1. `fanfic.ts` API 模块 + 同人模式基础 UI
2. `daemon.ts` API 模块
3. `export.ts` 独立模块
4. 前端 API 覆盖率 ≥70%

---

### Phase C：差异化增强（8-12 周）

#### C-1：RAG 知识库（6-8 周）

**前置条件**：Phase B 的 dogfood 数据足够评估 Truth 召回质量

**交付件**：
1. 嵌入式向量存储（SQLite + sqlite-vss 或轻量 Qdrant）
2. 文档导入 + 分块 + 索引管线
3. 混合检索：向量相似度 + 关键词匹配（Reciprocal Rank Fusion）
4. ContextBlock 集成：RAG 召回结果作为新 context source
5. 同人 canon 语义检索

**借鉴来源**：
- `storyforge/process/AI-Novel-Writing-Assistant/` 的 RAG 栈（Qdrant + embedding + hybrid retrieval + narrative decay）
- 当前 `TruthRetriever.retrieve_for_prompt()` 的检索模式（模式复用）

#### C-2：写作方法论增强（2-3 周）

**借鉴来源**：
- `storyforge/process/snowflake-fiction/` 的雪花写作法、钩子设计、节奏控制、人语化处理

**交付件**：
1. 雪花写作法编排（一句话→段落→场景→章节的展开式规划）
2. 钩子设计规则（黄金三章 hook 检测 + 跨章 callback 追踪）
3. 节奏控制规则（张力曲线 + 场景节奏分析）
4. 扁平角色检测（性格矛盾面 + 弧光追踪）

#### C-3：编辑器体验 + 产品化打磨（2-3 周）

**借鉴来源**：
- `storyforge/process/marktext/` 的专注模式、打字机模式、主题
- `storyforge/process/novelWriter/` 的项目树、场景树
- `storyforge/process/manuskript/` 的卡片视图、Corkboard

---

## 七、风险应对

### 风险矩阵

| # | 风险 | 概率 | 影响 | 缓解策略 |
|---|------|------|------|---------|
| R1 | Dogfood 暴露管线级阻断问题（如 prompt 质量导致草稿不可读） | 中 | 高 — 阻塞 Phase B | dogfood 前先用 E2E 脚本跑 test book 确认基础管线通过；准备 5 种修订模式兜底 |
| R2 | LLM 流式输出改造引入回归 | 中 | 中 — 影响所有 LLM 调用 | 保持 `generate_text()` 不变，新增 `generate_text_stream()`；渐进式迁移调用方 |
| R3 | 自动导演的 idea→BookConfig 解析不准确 | 中 | 中 — 用户需要手动修正 | 允许用户在解析结果上编辑确认后再执行；参考 AI-Novel-Writing-Assistant 的多候选方案 |
| R4 | RAG 引入后检索质量不如 Truth 关键词检索 | 中 | 中 — 投入产出不成比例 | 先做 Truth 检索优化（分词+衰减+召回量），评估后再决定 RAG 投入 |
| R5 | Provider 不稳定导致自动导演中途失败 | 高 | 高 — 全链路中断 | checkpoint/resume 机制 + 失败重试 + Provider fallback |
| R6 | Phase B 工期超出 6 周估算 | 中 | 中 — 延迟 Phase C | 自动导演拆成 B-1a（MVP：灵感→1章）和 B-1b（完整：灵感→N章），先交付 MVP |
| R7 | 前端 CodeMirror chunk 过大（1MB+）影响加载性能 | 低 | 低 — 已有警告 | Phase C 编辑器升级时处理；当前不阻塞 |

### 关键风险缓解原则

1. **验证先行**：每个 Phase 的第一个交付件必须是可以独立运行的端到端验证。Phase A 的 dogfood 验证整个管线，Phase B 的自动导演 MVP 先跑通"灵感→1章"再扩展。
2. **向后兼容**：新功能以新增方法/模块实现，不修改现有接口。LLM 流式输出新增 `generate_text_stream()`，不替换 `generate_text()`。
3. **渐进式交付**：每个子阶段独立可用。自动导演拆成 MVP + 完整版，RAG 拆成 Truth 优化 + 向量检索两步。
4. **真实数据驱动**：dogfood 结果决定后续投入方向。如果审计误判率 >30%，暂停自动导演，先修审计；如果 Truth 召回够用，推迟 RAG。

---

## 附录 A：文档溯源

本战略文档整合了以下输入源的具体建议：

| 来源 | 建议项 | 采纳情况 |
|------|--------|---------|
| 豆包意见 §9.1 自动导演 | 学习 AI-Novel-Writing-Assistant 的端到端流程 | ✅ Phase B-1 |
| 豆包意见 §9.2 RAG 知识库 | 增加向量检索 + 关键词检索 | ⚠️ 降为 Phase C，先优化 Truth |
| 豆包意见 §9.3 传统项目管理 | 场景树/卡片视图 | ✅ Phase C-3（P2） |
| 豆包意见 §9.4 编辑器体验 | 专注/打字机/主题 | ✅ Phase C-3（P2） |
| 豆包意见 §9.5 产品验证 | dogfood 验证 | ✅ Phase A-1（P0） |
| 豆包意见 §10 P0 安全 | 收紧 API 安全边界 | ⚠️ 已知设计选择，本地单用户场景暂可接受 |
| 豆包意见 §10 文档治理 | 拆分 project-status + 启用 ADR | ✅ Phase A-3 |
| 评估.md §八 P0 | 执行 dogfood + 覆盖率基线 | ✅ Phase A-1 |
| 评估.md §八 P1 | LLM 流式输出 + ADR + 前端 API | ✅ Phase A + Phase B |
| 评估.md §八 P2 | 自动导演 + benchmark + 编辑器 | ✅ Phase B + Phase C |
| 评估.md §五 UX 短板 | 流式输出是体验最大单点提升 | ✅ Phase A-2 |

## 附录 B：量化基线快照（2026-06-11）

| 指标 | 当前值 | Phase A 目标 | Phase B 目标 |
|------|--------|-------------|-------------|
| 后端 tests | 486 | ≥490 | ≥510 |
| 前端 tests | 62 | ≥65 | ≥75 |
| 前端 API 覆盖率 | ~40% | ~50% | ≥70% |
| Dogfood 记录 | 0 章 | ≥1 章 | ≥3 章 |
| ADR 文档 | 0 份 | ≥5 份 | ≥7 份 |
| pytest --cov | 未记录 | 已记录 | 不退步 |
| LLM 流式输出 | ❌ | ✅ draft + revise | ✅ 全操作 |
| 自动导演 | ❌ | — | ✅ 灵感→3章 |
