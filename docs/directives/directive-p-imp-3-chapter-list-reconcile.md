# 指令 P-IMP-3：章节列表以 reconcile 为真相源（消除"5 章"启发式 + 空卡片噪声）

> 下发 Codex。前置：P-OPS-1 完成（565 passed）；P1-1b reconcile 端点已就绪。
> 目标：兑现 PM 分析 [`docs/reviews/pm-analysis-import-and-chapter-flow.md`](../reviews/pm-analysis-import-and-chapter-flow.md) §4 的重设计——把章节列表从"`current_chapter+2` 启发式"改为"读 reconcile 真实产物"，让幽灵章节可见、空卡片消失。

## 背景

当前 `web/src/components/chapters/ChapterList.tsx:5`：

```typescript
const visibleCount = Math.min(Math.max(book.current_chapter + 2, 5), book.target_chapters || 5);
```

三个问题：
1. **与真实产物脱钩**：新书也强制 5 张空卡片（无运行按钮的 agent-mode 下，空卡片无意义）。
2. **被幽灵章节污染**：《别打了》`current_chapter=2`，但 ch3/ch4 有 truth+export 无正文；启发式把它们当"空"，掩盖不一致。
3. **`current_chapter` 已被证伪**（P1-1b reconcile 显示 max_chapter=4，但 book.json 写 2）——不该再用它驱动 UI。

P1-1b 的 `GET /api/books/{id}/reconcile` 已给出 per-chapter `has_text/plan/truth/export/state/run` + `inconsistent_reasons`。本指令让前端消费它。

## 任务

### 1. 前端 reconcile 数据层

- 新增 `web/src/api/reconcile.ts`：`reconcileApi.get(bookId)` → `GET /api/books/{id}/reconcile`，返回 `BookReconciliation`（复用后端 `BookReconciliationResponse` shape）。
- 新增 `web/src/hooks/useReconcile.ts`：`useReconcile(bookId)` TanStack Query hook，与 `useChapters` 同生命周期（进 BookDetailPage chapters tab 时拉取，invalidate 时机对齐章节变更）。

### 2. `ChapterList` 改为真相驱动

- **列表来源**：从 `reconcile.chapters`（已含真实存在章）渲染，**不再用** `current_chapter+2` 启发式。
- **每章卡片**（扩展 `ChapterCard`）：
  - 阶段进度：依据 `has_plan/text/truth/export` + state_status 显示已产出阶段（勾），贴合既有 Run Viewer 的"勾=已产出"语义。
  - **inconsistent 标记**：`status === "inconsistent"` 的章（如 ch3/ch4）显示 `⚠ 数据不一致` 徽标 + 可展开 `inconsistent_reasons`（中文映射：`export_without_state`→"已导出但无状态记录" 等）。**只读展示，不 heal、不删。**
- **"下一章"指示器**：列表末尾单个条目「第 N+1 章 — 由 agent 触发生产」（N = `reconcile.max_chapter`），**不堆空卡片**。无产物新书（`max_chapter=0`）显示「第 1 章 — 由 agent 触发生产」。
- **分页/分组**（兑现注释承诺）：章数多时按卷分组或分页（卷数据来自 `volumes.json`，已有 API）。

### 3. `book.json.current_chapter` 降级

- 章节列表**不再读** `current_chapter` 驱动显示。
- BookDetailPage 顶部"章节进度"显示若仍用 `current_chapter/target_chapters`，改为 `reconcile.max_chapter / target_chapters`（真实进度），或保留 `current_chapter` 但加角标"进度计数（待 heal 校正）"。
- **不改 `book.json.current_chapter` 的值**（heal 留 PM 决定，见红线）。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| reconcile 端点 + 序列化模型 | `src/storyforge3/api/routes/books.py:141` `reconcile_book` + `BookReconciliationResponse`/`ChapterConsistencyResponse`（books.py:45-103） | **直接消费** |
| 书级数据 hook 模式 | `web/src/hooks/useProviders.ts` / Truth/Snapshot panel 的 fetch+invalidate | **模式复用** → `useReconcile` |
| 卡片阶段勾语义 | `web/src/components/chapters/ChapterPipeline.tsx`（勾=已产出 tab） | **直接复用**语义 |
| 卷分组数据 | `GET /api/books/{id}/volumes`（已有） | **直接消费** |

**新写比例**：约 **40%**。后端 reconcile 已完成；新写前端 `reconcileApi` + `useReconcile` + `ChapterList` 重写 + `ChapterCard` inconsistent 标记。无新后端。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥565 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
pnpm --dir web test                                      # 前端测试全绿
```

手动（`storyforge3 dev` 起后对《别打了》）：
- 章节列表显示 ch1、ch2（正常卡）+ ch3、ch4（`⚠ 数据不一致`，可展开 reasons）+ 末尾「第 5 章 — 由 agent 触发生产」。
- **无空占位卡片堆**。
- 无产物新书只显示「第 1 章 — 由 agent 触发生产」。

## 必须覆盖的测试

- `ChapterList`：渲染真实存在章 / inconsistent 标记 / reasons 展开 / 下一章指示器 / 空书。
- `useReconcile`：fetch + invalidate。
- inconsistent reason 中文映射快照测试。

## 红线

- ❌ 不加任何运行按钮（agent-mode-only）。
- ❌ reconcile 只读——**不 heal、不删 ch3/ch4**（PM 验收可见性后再决定）。
- ❌ 不改 `book.json.current_chapter` 值（降级其 UI 作用即可）。
- ❌ 不引入新重依赖。

## 回报

- commit hash（建议 `feat(web): chapter list driven by reconciliation truth`）
- pytest + ruff + typecheck + 前端 test 结果
- 《别打了》章节列表截图或 DOM 描述（ch3/ch4 ⚠ + 下一章指示器 + 无空卡片）

## Out of Scope

- ❌ 不做 ch3/ch4 heal（独立 PM 决策，等本指令可见性验收后）。
- ❌ 不做 P1-2 Run Viewer（独立指令）。
- ❌ 不做 P-IMP-2 导入 auto-verify / P-IMP-4 "运行全流程"标签清理（独立指令）。
