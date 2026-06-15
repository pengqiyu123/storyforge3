# 调研总报告：前端 6 阶段展示设计 + Docs 缺口分析

> PM 调研 | 2026-06-15~16
> 背景：用户报告前端所有章节均显示"尚未起草"，且 docs/ 下大量查缺补漏与优化建议尚未实施。
> 目的：(1) 诊断前端阶段展示的根因并给出设计方案；(2) 梳理所有未实施 docs 条目，分诊优先级。

---

## 一、前端 6 阶段展示设计

### 1.1 根因诊断

**根本 Bug：`fallbackResult()` 硬编码空文本**

文件：`web/src/components/chapters/ChapterCard.tsx:151-160`

```typescript
function fallbackResult(bookId: string, chapter: ChapterConsistency): ChapterResult {
  const status = chapter.status === "inconsistent" ? "needs_review" : resolvedStatus(chapter);
  return {
    book_id: bookId,
    chapter_no: chapter.chapter_no,
    status,
    title: "未命名",
    text: ""  // ← 永远为空
  };
}
```

**数据流**：
```
章节列表页 → reconcile API 返回 ChapterConsistency（摘要数据，无 text）
           → ChapterCard 用 ChapterConsistency 构建 fallbackResult(text:"")
           → ChapterPipeline 接收 result，hasText = (result.text ?? "").trim().length > 0 → false
           → 起草 tab 显示"尚未起草"
```

**而真实数据 API 已存在**：`useChapterStatus` hook（`hooks/useChapters.ts:13-36`）调用 `GET /api/books/{id}/chapters/{n}/status`，返回完整的 `ChapterResult`（含 text、title、revision_diff 等）。但 **ChapterCard 从未调用此 hook**。

### 1.2 组件清单：已实现 vs 未挂载

| 组件 | 文件路径 | 实现状态 | 挂载状态 | 数据来源 |
|------|---------|---------|---------|---------|
| `PlanView` | `ChapterPipeline.tsx:283-331` | ✅ 完整 | ✅ 已挂载 | `useChapterPlanState` → `GET /plan` |
| `ChapterEditor`（起草/正文） | `components/editor/ChapterEditor.tsx` | ✅ 完整 | ✅ 已挂载 | `result.text`（但被 fallbackResult 截断） |
| `AuditResultPanel` | `components/chapters/AuditResultPanel.tsx` | ✅ 完整（92 行） | ❌ **未挂载** | 需 `AuditResult` 数据 |
| `RevisionDiffPanel` | `components/chapters/RevisionDiffPanel.tsx` | ✅ 完整（113 行） | ❌ **未挂载** | `ChapterResult.revision_diff` |
| `ExportPreviewDialog` | `components/export/ExportPreviewDialog.tsx` | ✅ 完整 | ✅ 已挂载 | 独立 API 调用 |
| `RunTrack` | `components/chapters/RunTrack.tsx` | ✅ 完整（7 阶段） | ✅ 已挂载 | `useRunRecord` |
| `LiveStage` | `components/chapters/LiveStage.tsx` | ✅ 完整 | ✅ 已挂载 | `useRunRecord` |
| Truth 摘要面板 | — | ❌ 不存在 | — | 需新建 |
| 批准记录视图 | — | ❌ 不存在 | — | 轻量，可就地写 |

### 1.3 7 阶段 vs 6 Tab 的关系

后端状态机有 **7 个产物阶段**：

```
plan → draft → audit → revise → approve → truth → export
```

前端 `ChapterPipeline` 定义了 **6 个 view tab**（无 truth 独立 tab）。
`RunTrack` 显示了 **7 个阶段**（含 truth）。

这不是 Bug。approve 和 truth 在后端是两步（approve 双跳到 TRUTH_COMMITTED），但在前端可以合并展示，因为 approve 对用户是瞬间操作。建议在 approve tab 中同时展示批准状态和 truth 统计信息。

### 1.4 建议的 6 Tab 设计方案

| Tab 标签 | 展示内容 | 数据来源 | 当前状态 | 修复动作 |
|---------|---------|---------|---------|---------|
| **规划** | chapter goal、outline_node、arc_context、must_keep/avoid、style | `GET /plan` → `ChapterIntent` | ✅ 已工作 | 无需改动 |
| **起草（正文）** | 章节正文 + 编辑器（支持手动编辑） | `GET /status` → `ChapterResult.text` | ❌ fallbackResult 截断 | **ChapterCard 改用 `useChapterStatus`** |
| **审计** | 审计结果面板：passed/blocked/warning 规则列表 | 需 `GET /status` 扩展 `audit_result` 字段 | ❌ PlaceholderView | **挂载 `AuditResultPanel`** |
| **修订 diff** | 修订前/后对照（insert/delete/replace block） | `GET /status` → `ChapterResult.revision_diff` | ❌ PlaceholderView | **挂载 `RevisionDiffPanel`** |
| **批准** | 批准状态 + truth 统计（条目数等） | `GET /status` → status + truth 字段 | ❌ PlaceholderView | **就地写批准记录视图** |
| **导出** | 导出格式预览 + 历史导出记录 | `GET /export-preview` + 历史记录 | 🔧 部分工作 | 增强：显示历史导出 |

### 1.5 修复路径

**Step 1（核心 Bug 修复，~20 行改动）**

`ChapterCard.tsx`：在组件内调用 `useChapterStatus(bookId, chapterNo)`，将真实 `ChapterResult` 传给 `ChapterPipeline`，替代 `fallbackResult`。

```typescript
// Before
const result = fallbackResult(bookId, chapter);

// After
const statusQuery = useChapterStatus(bookId, chapterNo);
const result = statusQuery.data ?? fallbackResult(bookId, chapter);
```

修复后 `ChapterPipeline` 的 `hasText` 和 `currentText` 拿到真实数据，"尚未起草"消失，编辑器显示实际正文。

**Step 2（挂载已有组件，~30 行改动）**

替换 `ChapterPipeline.tsx` 中 3 个 `PlaceholderView`：
- L258 audit tab → `<AuditResultPanel result={auditResult} />`
- L259 revise tab → `<RevisionDiffPanel diff={result.revision_diff} />`
- L260 approve tab → 批准状态记录视图（就地新建轻量组件）

**Step 3（后端扩展，~50 行改动）**

`GET /status` 返回的 `ChapterResult` 新增 `audit_result: AuditResult | null` 字段：
- `chapter_service.get_status()` 在 `AUDITED`/`NEEDS_REVISION`/`REVISED`/`APPROVED`/`TRUTH_COMMITTED`/`EXPORTED` 状态时加载持久化的 AuditResult
- 前端类型 `ChapterResult` 同步添加 `audit_result` 字段
- `ChapterPipeline` 从 `result.audit_result` 取数据传给 `AuditResultPanel`

### 1.6 架构规范对照

`docs/architecture/run-state-and-viewer.md` §4 定义了 `ChapterPanel`（含 `ResultTabs`：正文/审计/修订diff/truth摘要/导出记录），当前 `ChapterPipeline` 是 P0.5 过渡态。

**P-UI-FIX-1 完成后的状态**：ChapterPipeline 的 6 个 tab 全部有真实数据展示，达到 P0.5 的"结果查看器"目标。完整的 `ChapterPanel` P1 重设计（异步 Run 模型、统一 Action 层）作为后续迭代。

---

## 二、Docs 缺口分析（三级分诊）

### 2.1 总量

跨 3 份文档，共有约 **30 项未实施条目**：

| 文档 | 未实施数 | 说明 |
|------|---------|------|
| `docs/项目查缺补漏清单.md` | 8/10 | #1 (ChapterDiscarder) 和 #3 已完成，其余 8 项延期 |
| `docs/架构分析与优化方案.md` | 12/12 | A-L 全部优化项，均为架构级 |
| `docs/research/sf3-gap-analysis.md` | ~10 | 零散功能缺口（世界构建 UI、角色管理 UI 等） |

### 2.2 🔴 级：阻塞生产可见性（应立即修复）

这些不是来自 docs 的"待办"，而是调研中发现的前端缺陷，必须修复才能让已生产的 3 章内容在前端可查看：

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| R1 | `fallbackResult(text:"")` 导致所有章节显示"尚未起草" | `ChapterCard.tsx:151-160` | **生产结果不可见** |
| R2 | `AuditResultPanel` 已实现但未挂载 | `ChapterPipeline.tsx:258` | 审计结果无法查看 |
| R3 | `RevisionDiffPanel` 已实现但未挂载 | `ChapterPipeline.tsx:259` | 修订 diff 无法查看 |
| R4 | `GET /status` 缺少 `audit_result` 字段 | 后端 `chapter_service.py` | 挂载 AuditResultPanel 无数据源 |

**合计**：4 项，预计工时 1-2 天，产出为 `P-UI-FIX-1` 指令。

### 2.3 🟡 级：正确延期的架构优化（暂不实施）

来自 `docs/架构分析与优化方案.md` 的 A-L 12 项：

| # | 优化项 | 工时估算 | 延期理由 |
|---|--------|---------|---------|
| A | Service Interface 分离（PipelineOrchestrator） | 3 周 | 当前 workflow 单线程可用，重构不影响生产 |
| B | Provider 连接池 | 2 周 | P-FIX-3 已覆盖 RemoteProtocolError retry |
| C | Truth 事务性提取 | 3 周 | 单人使用场景冲突极少，fail-closed 够用 |
| D | 统一异常层级 | 1 周 | 工程洁癖，不影响功能 |
| E | Context Package 缓存 | 2 周 | 3 章无瓶颈，10+ 章再评估 |
| F | SQLite 写入队列 | 2 周 | 同上 |
| G | Pipeline Checkpoint | 2 周 | P-FIX-3 retry 覆盖大部分中断场景 |
| H | Provider 健康监控 | 2 周 | 手动切换足够 |
| I | E2E 集成测试扩充 | 2 周 | 600 测试已通过，产出导向优先 |
| J | Web/Desktop 代码分离 | 4 周 | 文档自身标注"不推荐" |
| K | API 密钥管理加固 | 1 周 | 本地单机，泄露风险低 |
| L | 路径安全验证 | 1 周 | 本地单机，无外部输入 |

**总工时**：约 24 周。如果全部实施将严重拖慢生产进度。

**建议重新评估时机**：完成 10+ 章生产后，根据实际痛点选择高价值项（可能优先级为 G > E > A > D）。

### 2.4 🟢 级：P2 功能开发（后续迭代）

来自 `docs/项目查缺补漏清单.md` 和 `sf3-gap-analysis.md`：

| 来源 | 描述 | 建议时机 |
|------|------|---------|
| 查缺补漏 #2 | 世界构建 UI | 核心管线稳定后 |
| 查缺补漏 #4 | 角色管理 UI | 核心管线稳定后 |
| 查缺补漏 #5 | 卷纲编辑器 | 核心管线稳定后 |
| 查缺补漏 #6 | 批量章节操作 | 10+ 章生产后 |
| 查缺补漏 #7 | 章节排序/拖拽 | 10+ 章生产后 |
| 查缺补漏 #8 | 导出格式选择增强 | 导出需求明确后 |
| 查缺补漏 #9 | 版本历史 UI | 需求驱动 |
| 查缺补漏 #10 | 多书籍管理 | 多书籍需求出现后 |
| Gap Analysis | StyleContract UI、Hook 诊断 UI 等 | 逐个按需 |
| Gap Analysis | 桌面壳自动更新 | 发行前 |

---

## 三、阶段路线图

```
Phase 1（当前）:
  ✅ P-FIX-1/2/3 + P-DISCARD-1 + PROD-1a/1b/1c  → 3 章全流程验证
  → P-UI-FIX-1：前端可见性修复（本次）
  → PROD-2：ch4 生产（前端修复后）
  → 目标：5-10 章生产 + 前端完整可观测

Phase 2（中期，10+ 章后）:
  → 根据多章生产反馈评估 A-L 优化项优先级
  → 可能优先：G (Checkpoint)、E (Context Cache)
  → P2 功能：世界构建 UI、角色管理 UI

Phase 3（远期）:
  → Run Viewer P1 重设计（异步 Run 模型）
  → PipelineOrchestrator 架构重构
  → Web/Desktop 代码分离
```

---

## 四、附件：关键代码位置索引

| 位置 | 说明 |
|------|------|
| `web/src/components/chapters/ChapterCard.tsx:151-160` | `fallbackResult()` — 根因 |
| `web/src/components/chapters/ChapterCard.tsx:131-149` | `resolvedStatus()` — reconcile 状态推断 |
| `web/src/components/chapters/ChapterPipeline.tsx:38-45` | 6 阶段 tab 定义 |
| `web/src/components/chapters/ChapterPipeline.tsx:74-75` | `hasText` 判断（受 fallbackResult 影响） |
| `web/src/components/chapters/ChapterPipeline.tsx:226` | "尚未起草" 显示位置 |
| `web/src/components/chapters/ChapterPipeline.tsx:258-260` | 3 个 PlaceholderView（待替换） |
| `web/src/hooks/useChapters.ts:13-36` | `useChapterStatus` hook（已存在，未被 ChapterCard 使用） |
| `web/src/api/chapters.ts:15-25` | `ChapterResult` 类型定义 |
| `web/src/api/chapters.ts:37-44` | `AuditResult` 类型定义 |
| `web/src/components/chapters/AuditResultPanel.tsx` | 已实现审计面板（92 行） |
| `web/src/components/chapters/RevisionDiffPanel.tsx` | 已实现修订 diff 面板（113 行） |
| `web/src/components/chapters/RunTrack.tsx` | 7 阶段轨道（含 truth） |
| `docs/architecture/run-state-and-viewer.md` §4 | 目标架构：ChapterPanel + ResultTabs |
