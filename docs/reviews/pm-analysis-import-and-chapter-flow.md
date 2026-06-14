# PM 综合分析：CC-Switch 导入失败诊断 + 章节显示 + 用户流程重设计

> 产品经理：Claude Code PM
> 日期：2026-06-14
> 触发：第三方分析师 Trae 输出 `docs/reviews/trae-ccswitch-import-diff-analysis.md`，用户要求 PM 全面判断 + 解决 4 类问题（页面打不开 / 模型导入设计 / 章节显示 / 用户流程重设计）。
> 状态：分析完成，实施步骤见 §7。本文不写代码，只产出设计 + 指令路线图。

---

## 0. 概要（TL;DR）

1. **Trae 报告质量：后端配置分析扎实，但有一个假阳性 P0。** P0-1（providers_config_dir 相对路径）、P0-2（.env 死配置）**确认属实**；P1-4（火山 `/api/coding`）**确认已修**；但 P0-3（前端 envelope 不匹配导致列表空）**被证伪**——前端 `client.ts` 已正确解包 `envelope.data`。Trae 反复出现"断言代码行为但未读源码"的模式（同上次 truth 泄露误判）。
2. **导入并未"彻底失败"。** `storyforge3\.storyforge3\providers.json` **实际存在**，含火山 Codingplan 作 active provider。导入在从 `storyforge3/` 目录启动时是成功的；Trae 描述的是**cwd 相关的脆弱性**，不是当前活跃故障。
3. **"5 章"的根因是一行 UI 启发式**：`ChapterList.tsx:5` 的 `Math.min(Math.max(current_chapter + 2, 5), target || 5)`。它与"章节是否真实存在"**完全脱钩**——对只写了 1 章的书也强制显示 5 个空卡片。后续章节（ch6+）会随 `current_chapter` 增长自动出现，但启发式本身是错的。
4. **"页面打不开"**与 Trae 文档/路径/权限**无关**。字面意义的"页面打不开"= 后端 `:8000` 不可达（启动失败 / 端口 / Tauri sidecar+venv 双失败 → 30s 健康检查超时 → StartupErrorScreen）。若用户实际指的是"供应商页/导入不工作"，那才落到 P0-1/P0-2/P1-5。
5. **用户流程重设计的核心张力**：产品已锁定 agent-mode-only，但 `DashboardPage.tsx:41` 仍有"运行全流程"快捷入口（实际是导航链接，非运行触发器，但**标签误导**）；章节列表仍假设手动操作者视角。

---

## 1. Q1：Trae 报告 PM 综合判断

### 1.1 逐条裁决

| Trae 主张 | 严重度 | PM 裁决 | 证据 |
|-----------|--------|---------|------|
| **P0-1**：`providers_config_dir=".storyforge3"` 相对路径，依赖 cwd，跨启动目录不稳定 | P0 | ✅ **确认（潜在脆弱性）** | `config.py:10` + `deps.py:66` 仅 `Path(config.providers_config_dir)`，**未 `.resolve()`** |
| **P0-2**：`.env.example` 有 `CCSWITCH_DB_PATH/SETTINGS_PATH/APP_TYPE` 但配置类无字段，`extra="ignore"` 静默丢弃 | P0 | ✅ **确认（误导性死配置）** | `.env.example:3-5` vs `config.py:6-35` 无对应字段 |
| **P0-3**：前端读 `response.providers`（Auto-news2 风格）导致列表空 | P0 | ❌ **证伪** | `web/src/api/client.ts` 的 `request()` 已 `return envelope.data`，前端拿到的就是 data，不会空 |
| **P1-4**：火山 `/api/coding` 必须不剥离，SF3 已修 | P1 | ✅ **确认（已修，Trae 正确）** | `llm_service.py:22-32` 显式注释不剥离；`providers.json` 火山项 base_url 保留 `/api/coding` |
| **P1-5**：无 key provider（`has_api_key=false`）被展示/导入 | P1 | ✅ **确认（UX 陷阱）** | `ccswitch_db_reader.py:103` 标记 has_api_key；`provider_config.py:51` 导入时 `enabled=bool(api_key)`（导入但禁用）；前端 `CCImportDialog.tsx` **不过滤**，全部展示 |

### 1.2 PM 对 Trae 的整体评价

- **可靠度：⭐⭐⭐⭐（4/5）。** 后端配置路径与 .env 一致性的分析准确、有价值，应纳入修复。
- **扣分点：P0-3 是假阳性。** Trae 断言"前端读 raw response"但未读 `client.ts`。这与上一次"truth retriever 未来泄露高风险"误判同模式——**Trae 倾向于在未读源码时断言代码行为**。PM 已读 `retriever.py:49/56/64`（上次）与 `client.ts`（本次）修正。
- **过度诊断：** Trae 把"导入失败"列为 5 因素叠加，但实际 providers.json **存在且 active 已设**。当前不是"彻底失败"，而是"cwd 脆弱 + 死配置 + 无 key 噪声"三类**质量缺陷**。

### 1.3 PM 结论

采纳 P0-1、P0-2、P1-5 的修复；**否决 P0-3**（无需动前端 envelope，它是对的）；P1-4 维持现状（已修）。Trae 的排查步骤（§12）中"Step 1 确认 providers.json 路径""Step 2 打印启动环境"是**最有价值的两条**，应直接落成启动日志。

---

## 2. Q2："页面打不开"诊断

### 2.1 两种解释，需先分清

| 用户说的"页面" | 含义 | 根因方向 |
|---------------|------|---------|
| **A. 整个 Web/Tauri 应用白屏/打不开** | 后端不可达 | 启动链路（后端进程 / 端口 / Tauri sidecar） |
| **B. 供应商设置页/导入弹窗异常** | 导入链路 | P0-1/P0-2/P1-5（见 §3） |

### 2.2 解释 A：应用打不开（最可能）

**前置链路**（任一断裂 → `StartupErrorScreen`）：

```
storyforge3 serve :8000  ─┐
                          ├─→ GET /api/health 200  ─→ 前端 bootstrap
Tauri: sidecar.exe → 失败 → .venv fallback → 失败 ─┘     (失败 → 30s 超时)
```

证据：
- `web/src/main.tsx:23` → `waitForApiReady()` 轮询 `/api/health`，30s 超时记 `StartupError`。
- Tauri 模式 `web/src/api/client.ts:12-15` 硬编码 `DESKTOP_API_BASE = "http://127.0.0.1:8000"`。
- `src-tauri/src/lib.rs:142` 健康检查 30s 超时；`process_manager.rs:29-70` sidecar-first / venv-fallback。

**诊断三问（文件路径/权限/完整性）在此解释下大多不成立：**
- **文件路径**：cwd 相对 providers.json（P0-1）只影响"导入后读不到 active provider"，**不影响页面打开**——dashboard 即使无 provider 也只是显示"未导入"。
- **权限**：写 `.storyforge3/` 失败只让**导入**报错，页面仍开。
- **完整性**：providers.json 损坏只让 LLM 调用失败，页面仍开。

→ **结论：若字面"页面打不开"，查后端是否启动、`:8000` 是否被占、Tauri sidecar/venv 是否都失败。** 与 Trae 文档无关。

### 2.3 解释 B：供应商页/导入不工作

此时 §3 的 P0-1/P0-2/P1-5 才是根因。**PM 倾向认为用户实际遇到的是 B**（因为整个 prompt 围绕导入与显示），但建议用户确认。

### 2.4 关于 Trae 文档本身

`docs/trae-ccswitch-import-failure-diff-analysis.md` PM 已正常读取（无路径/权限/完整性问题）。若用户指的是该 .md 在某预览器打不开，那是预览器问题，非项目问题。

---

## 3. Q3：模型导入设计缺陷与改进

### 3.1 当前导入链路（已读源码确认）

```
CC-Switch SQLite (~/.cc-switch/cc-switch.db)
  → CCSwitchDBReader.list_available()        # ccswitch_db_reader.py
  → POST /providers/import                    # api/routes/providers.py:194
  → ProviderConfigManager.import_providers()  # provider_config.py:39
  → _save() → .storyforge3/providers.json     # 相对 cwd
  → create_llm_service() 读 active provider   # factory.py
```

### 3.2 设计缺陷清单

| # | 缺陷 | 证据 | 影响 |
|---|------|------|------|
| D1 | **配置路径 cwd 相对，不锚定项目根** | `config.py:10` + `deps.py:66` 未 resolve | 从 `Novel/` 或 sidecar cwd 启动 → providers.json 写/读到错位置，"导入成功但运行时读不到" |
| D2 | **.env 死配置项** | `.env.example:3-5` vs `config.py` 无字段 + `extra="ignore"` | 用户以为设了 DB 路径，实际被吞 |
| D3 | **无启动诊断日志** | `get_provider_manager()` 不打印 resolved path / active key | 出问题时无法定位"读的是哪个 providers.json" |
| D4 | **导入对话框不过滤无 key provider** | `CCImportDialog.tsx` 渲染全部 `available.providers` | 用户勾选 official/空 key 项 → 导入即禁用 → 以为坏了 |
| D5 | **导入后不自动 verify** | `providers.py:194-207` import 后仅返列表 | 用户导入成功但不知 endpoint 是否通，首次 draft 才暴露 |
| D6 | **废弃 reader 仍被 client.py import** | `ccswitch_reader.py`（标记 deprecated）被 `llm/client.py:13,56` 引用 | 维护者误参考旧 reader，与 DB 新架构冲突 |
| D7 | **导入失败静默化** | import 持久化失败（权限/磁盘）只在后端抛 500，前端 toast 通用"导入失败" | 用户无法区分"DB 读不到"vs"落盘失败"vs"无 key" |

### 3.3 改进设计

**D1 — 路径锚定（最高优先）**
- `providers_config_dir` 默认改为**相对项目根的绝对路径**：以 `storyforge3/` 包根或可配置 `STORYFORGE3_HOME` 为锚，`Path(...).resolve()`。
- 保持向后兼容：若用户显式传绝对路径则用之；相对路径则相对项目根而非 cwd。
- 替代方案（更稳）：落 `%APPDATA%/StoryForge3/providers.json`，与 Tauri 桌面打包对齐。**PM 倾向项目根锚定（改动小、不动用户数据位置）。**

**D2 — .env 收口**
- **删除** `.env.example` 中 `CCSWITCH_SETTINGS_PATH/DB_PATH/APP_TYPE`（CC-Switch DB 路径已在 `ccswitch_db_reader.py` 默认 `~/.cc-switch/cc-switch.db`，无需 env）。
- 或：若坚持可配，则在 `StoryForge3Config` 加 `ccswitch_db_path` 字段并传入 reader。**PM 选删除**（简单、减少误导面）。

**D3 — 启动日志**
- 服务启动时打印：`cwd`、`resolved providers.json path`、`active_provider_key`、`ccswitch db path`、`db_available`。
- 落到既有 startup log（`storyforge3 serve` 启动序列）。

**D4 — 无 key 过滤**
- `GET /providers/available` 默认隐藏 `has_api_key=false`（或返回但前端禁选 + 标"无密钥"）。
- import 后若无任何 keyed provider 被导入 → 返回明确错误码 `NO_KEYED_PROVIDER_IMPORTED`。

**D5 — 导入后自动 verify**
- import 成功且设了 active → 后台自动调一次 `verify_provider`，把 `cc_probe_status` 回写。
- 前端 import 成功 toast 改为"已导入 N 个，正在验证…"，verify 完显示绿/红。

**D6 — 清理废弃 reader**
- 删除 `ccswitch_reader.py` 或把 `CCSwitchClient` 一起标 deprecated 并从运行路径移除（确认无生产代码依赖后）。

**D7 — 错误分层**
- import 端点区分错误码：`CCSWITCH_DB_UNAVAILABLE` / `NO_KEYED_PROVIDER_IMPORTED` / `PERSIST_WRITE_FAILED`，前端按码给不同文案。

---

## 4. Q4：章节显示逻辑根因与重设计

### 4.1 "5 章"根因（已读源码确认）

`web/src/components/chapters/ChapterList.tsx:5`：

```typescript
const visibleCount = Math.min(Math.max(book.current_chapter + 2, 5), book.target_chapters || 5);
const chapters = Array.from({ length: visibleCount }, (_, index) => index + 1);
```

**语义**：显示 `current_chapter + 2` 章，**下限 5**，上限 `target_chapters`（缺省回退 5）。

**例**：《别打了》`current_chapter=2, target_chapters=100` → `min(max(4,5),100)=5` → 显示 5 张卡片（ch1–5）。即使只写了 ch1，也强制 5 张。

**"5"的其它出现处**（非显示根因，但相关）：
- `daemon_service.py:14` `max_chapters_per_run=5`（守护批量每轮上限）
- `daemon.py:17-18` 同上

### 4.2 该设计为什么不合理

1. **与"章节是否真实存在"脱钩**：对只写了 1 章的新书，显示 5 个空卡片，与"viewer，无运行按钮"的 agent-mode 语境冲突——空卡片没有任何操作意义。
2. **被幽灵章节污染**：ch3/4 有 truth+export 无正文（已知不一致），启发式按 `current_chapter=2` 算出显示 ch1–5，把 ch3/4 显示成"空"，掩盖了它们"其实有产物但不一致"的真相。
3. **"+2 lookahead"无语义依据**：纯拍脑袋。
4. **下限 5 强制空卡片**：违背"只显示真实存在的章节"的直觉。

### 4.3 后续章节如何出现（当前机制）

- 章节由 **agent/API** 创建：`POST /chapters/{no}/plan` 或 `/draft` → `_bump_current_chapter()` 把 `current_chapter` 推到该章号（`chapter_service.py:426-434`）。
- **无 UI 创建章节入口**（符合 agent-mode-only）。
- ch6+ 在 `current_chapter ≥ 5` 时由 `current+2` 自动出现（`current=5→7`，`current=10→12`）。
- **问题**：依赖 `current_chapter` 计数器，而该计数器已被幽灵章节证明**不可信**（`current_chapter=2` 但 ch3/4 有产物）。

### 4.4 重设计：以"真实产物"为真相源

**新模型**：章节列表 = **实际存在任意产物的章节** + **一个"下一章"指示器**。

- 真相源 = **reconciliation 输出**（P1-1b 已下发 `ChapterReconciler`，per-chapter `has_text/plan/truth/export/state/run`）。`ChapterList` 应消费 `GET /books/{id}/reconcile`，而非 `current_chapter+2` 启发式。
- 显示：每章一张卡，标注真实阶段进度（哪些 view-tab 有产物 = 勾），inconsistent 的章（如 ch3/4）显式标"⚠ 数据不一致"并给"查看详情"入口（只读，不自动修复）。
- 末尾**单个**"下一章"指示器：「第 N+1 章 — 由 agent 触发生产」，不堆空卡片。
- 分页：章节多时按卷分组或分页（注释里"后续阶段会加入分页"可顺带兑现）。

**收益**：消除空卡片噪声；让幽灵章节"可见可报"（而不是假装不存在）；与 P1-1b reconcile 闭环对齐。

### 4.5 与既有计划的衔接

- **依赖** P1-1b（reconcile 端点）落地——本重设计是 reconcile 的**前端消费方**。
- 可并入 P1-2（前端 Run Viewer 最小版）一起做，不必单列。

---

## 5. Q5：用户使用流程与程序架构重设计

### 5.1 当前流程的张力

产品 2026-06-14 锁定 **agent-mode-only**（UI = 只读 Run Viewer，运行仅走 agent/API）。但现状有残留：

| 位置 | 现状 | 与 agent-mode 的张力 |
|------|------|---------------------|
| `DashboardPage.tsx:41` | 快捷入口"运行全流程" | 标签误导（实为导航链接到 chapters tab，非运行触发器，但暗示用户能"运行全流程"） |
| 世界/角色/卷纲 tab | "构建世界观""添加角色""规划卷纲"按钮 | 属于 LLM 生成步骤，严格说是 agent 域，但又是建书必需的一次性 setup |
| 章节页 | 已改为查看 tab（P0.5） | ✅ 符合 |

### 5.2 重新分层：三个交互面

PM 提议把用户交互明确分成**三个面**，每个面有清晰的"谁能触发"规则：

```
┌─ Setup 面（手动，一次性，配置性质）─────────────┐
│  导入 provider（/settings）                      │ ← 类似 IDE 配置，按钮 OK
│  创建书（/books 新建）                            │ ← 项目初始化，按钮 OK
│  种子世界/角色/卷纲（?tab=world/characters/...）  │ ← PM 判断：允许手动触发，因为属"建书配置"
│  （这些产 *.md / *.json 控制文件 + 种子 truth）   │
└──────────────────────────────────────────────────┘
┌─ Production 面（agent/API only，UI 只读）────────┐
│  章节六阶段：规划/起草/审计/修订/批准/导出         │ ← viewer tabs，无运行按钮（已符合）
│  批量生产（daemon）                               │ ← agent 触发
│  truth 提取 / 快照 / 导出                         │ ← agent 触发
└──────────────────────────────────────────────────┘
┌─ Authoring 面（手动，始终）──────────────────────┐
│  手编正文（章节编辑器 edit → Ctrl+S）             │ ← 润色，非管线执行（已符合）
│  人工确认（approve 的人工拦截位，若启用 HITL）    │
└──────────────────────────────────────────────────┘
```

**关键判定**：世界/角色/卷纲的"构建"按钮**保留**（属 Setup 面，与 provider 导入同性质的一次性配置）；但**章节生产的六阶段无按钮**（Production 面，agent 域）。这条线比 CLAUDE.md 的"manual text editing stays"更清晰——把"建书配置"也归入允许手动的面。

### 5.3 数据结构与真相源重设计

当前多源且互相矛盾（幽灵章节即证明）：

| 数据 | 当前位置 | 可信度 |
|------|---------|--------|
| 章节存在性 | `chapters/` 目录 + `book.json.current_chapter` | ⚠ current_chapter 已被证伪 |
| 章节状态 | `state/chapter_states.json`（状态机） | ✅ 最可信 |
| 跨章产物 | `truth/` + `exports/` + `plans/` + `runs/` | ✅ 客观存在 |
| 一致性 | 无（P1-1b 引入 reconcile） | 🆕 即将就绪 |

**PM 重设计**：**reconciliation 成为"章节真相"的唯一只读聚合层**：
- `book.json.current_chapter` **降级**为"进度提示"，不再驱动 UI（UI 改读 reconcile）。
- `ChapterReconciler.max_chapter`（扫描所有产物目录取最大章号）取代 `current_chapter` 作"书有多少章"的答案。
- 幽灵章节（ch3/4）由 reconcile 标 inconsistent，**不静默隐藏，也不自动删**（PM 验收后决定 heal）。
- book.json 的 `current_chapter` 修正留给"heal"阶段（reconcile 准确性确认后），不在本批改。

### 5.4 端到端用户旅程（重设计后）

```
首次启动
  → 后端 :8000 起（启动日志打印 providers.json 路径 + active provider）   ← D3
  → Dashboard（显示书列表 / 健康 / provider 状态）
Setup 面
  → /settings 导入 provider（过滤无 key / 导入后自动 verify）              ← D4/D5
  → /books 新建书
  → 种子世界/角色/卷纲（手动按钮 OK）
Production 面（agent 驱动，用户旁观）
  → agent 调 /run → 章节页显示 Run Viewer（RunTrack/LiveStage + SSE）
  → 各阶段 view-tab 勾随产物出现而点亮
  → 章节列表读 reconcile：显示真实存在的章 + 下一章指示器，幽灵章标⚠       ← §4.4
Authoring 面
  → 用户手编正文 → Ctrl+S → NEEDS_REVIEW
导出
  → agent 调 export → 导出预览/下载
```

---

## 6. 借鉴来源（PM §3.6 借鉴评估，强制）

| 改进 | 借鉴来源 | 借鉴方式 |
|------|---------|---------|
| 配置路径锚定项目根 | Auto-news2 `PROJECT_ROOT=Path(__file__).resolve().parent.parent` 模式（Trae §4.1 已指出） | 模式复用 → SF3 用包根锚定 |
| 启动诊断日志 | 通用 FastAPI startup event logging | 直接写，无新依赖 |
| 无 key provider 过滤 | `provider_config.py:51` 已有 `enabled=bool(api_key)` 判定 | 直接复用该判定做前端过滤 |
| 章节列表读 reconcile | P1-1b `ChapterReconciler`（已下发指令） | 直接消费其输出 |
| 错误码分层 | 既有 `ApiError(code=...)` 模式（providers.py:219） | 模式复用 |

**新写比例**：约 30%。多数是收口既有逻辑（resolve 路径、过滤、日志），非从零写。

---

## 7. 实施步骤（指令路线图）

按"先解诊断阻塞、再改显示、最后清 UX"排序。每条对应一份 Codex 指令。

### 指令 P-IMP-1：provider 配置健壮性（P0，最高优先，低风险）

- D1：`providers_config_dir` 锚定项目根并 `.resolve()`，保持向后兼容。
- D3：启动日志打印 resolved providers.json 路径 + active_provider_key + db_available。
- D2：删除 `.env.example` 死配置项（CCSWITCH_*）。
- D6：移除/标注废弃 `ccswitch_reader.py`（确认无生产依赖后）。
- 验收：从 `storyforge3/` 与从 `Novel/` 两个 cwd 启动，providers.json 解析到**同一绝对路径**；启动日志可见。

### 指令 P-IMP-2：provider 导入 UX（P1）

- D4：`GET /providers/available` 默认隐藏/禁选 `has_api_key=false`；无 keyed 导入返 `NO_KEYED_PROVIDER_IMPORTED`。
- D5：导入设 active 后自动 verify，回写 `cc_probe_status`。
- D7：import 端点错误码分层（DB 不可用 / 无 key / 落盘失败）。

### 指令 P-IMP-3：章节列表以 reconcile 为真相源（P1，依赖 P1-1b）

- §4.4：`ChapterList` 改读 `GET /books/{id}/reconcile`，显示真实存在章 + 单个"下一章"指示器；inconsistent 章标⚠。
- `book.json.current_chapter` 不再驱动 UI（保留字段，降级为提示）。
- 兑现"分页/按卷分组"（注释承诺）。

### 指令 P-IMP-4：agent-mode UI 清理（P2）

- `DashboardPage.tsx:41` "运行全流程"快捷入口 → 改标签"查看章节进度"或移除。
- §5.2 三面分层在 UI 上可视化（Setup/Production/Authoring 区分，至少在章节页明确"本页由 agent 驱动生产，你只能查看与手编"提示）。

### 与既有 P1 序列的关系

```
P1-1b（reconcile）→ P-IMP-3（章节列表消费 reconcile）→ P1-2（Run Viewer）→ P-IMP-1/2（导入健壮性，可与 P1-2 并行）→ P-IMP-4（UI 清理）
```

P-IMP-1（provider 健壮性）**独立、低风险、解诊断阻塞**，PM 建议**最先发**。

---

## 8. 红线 / Out of Scope

- ❌ 不改前端 envelope 协议（Trae P0-3 是假阳性，前端是对的）。
- ❌ 不动 truth retriever 过滤（已正确）。
- ❌ 不在本批 heal 幽灵章节 ch3/4（等 reconcile 准确性验收后由 PM 决定）。
- ❌ 不改 `book.json.current_chapter` 字段值（降级其 UI 作用即可，修正留 heal 阶段）。
- ❌ 不重新引入运行按钮（agent-mode-only 锁定）。

---

## 9. 待用户确认

1. **"页面打不开"指 A（整个应用）还是 B（供应商/导入页）？** §2.2 vs §2.3，根因方向不同。
2. **世界/角色/卷纲的"构建"按钮是否保留为手动 Setup 面？** §5.2 PM 倾向保留（建书配置性质）。
3. **providers.json 落项目根 vs `%APPDATA%/StoryForge3`？** §3.3 PM 倾向项目根（改动小）。

PM 默认按倾向执行；用户可在指令下发前调整。
