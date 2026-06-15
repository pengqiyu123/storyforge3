# 指令 P-IMP-3b：章节展示精细化（真相源统计 + 下一章正确推导）

> 下发 Codex。前置：P-IMP-3 章节列表读 reconcile ✅；P1-2 Run Viewer ✅。
> 触发：分析师文档 [`docs/章节按进度展示体验分析与改进建议.md`](../章节按进度展示体验分析与改进建议.md) §7/§10 抓到 P-IMP-3 三处真缺陷，PM 核验属实（见 `docs/reviews/pm-consolidated-decisions-2026-06-14.md`）。

## 背景

P-IMP-3 让章节列表读 reconcile，消除了空卡片。但留下三处缺陷，对**活跃书《别打了》有实际误导**：

1. **顶部文案误导**：显示「真实产物 {maxChapter} 章」——但 `maxChapter=4` 含 ch3/4 幽灵章，有效仅 2。
2. **下一章推导错**：`nextChapter = maxChapter + 1` → 对《别打了》提示「第 5 章」，**跳过了不一致的 ch3/ch4**。
3. **缺有效/孤儿分类**：reconcile 只有 consistent/inconsistent，没有 valid/partial/orphan 语义。

## 任务

### 1. 后端 ChapterReconciler 扩展（`src/storyforge3/services/chapter_reconciler.py`）

`BookReconciliation` 新增字段：

```python
valid_chapter_count: int           # validity == "valid" 的章数
highest_contiguous_chapter: int    # 从第1章起连续 valid 的最高章号（无 valid 则 0）
next_writable_chapter_no: int      # 全书一致时 = highest_contiguous+1；有不一致时 = 最低 inconsistent 章号（供用户定位，非建议续写）
has_blocking_inconsistency: bool   # 是否存在任意 inconsistent 章
```

`ChapterConsistency` 新增 `validity` 字段（基于现有 `has_*` 派生，不改扫描逻辑）：

| validity | 条件 |
|----------|------|
| `valid` | `has_text` 或 state_status ∈ {approved, truth_committed, exported} |
| `partial` | 非 valid，但有 has_plan 或 has_run |
| `orphan` | 非 valid，但有 has_truth 或 has_export（无正文/状态——幽灵特征） |
| `empty` | 无任何产物 |

**`next_writable_chapter_no` 推导**（PM 裁决：阻断优先于建议）：
- 若 `has_blocking_inconsistency`：返回**最低 inconsistent 章号**（让用户先定位异常，前端据此警告而非建议续写）。
- 否则：返回 `highest_contiguous_chapter + 1`。
- 《别打了》预期：has_blocking=True → next_writable=3（最低 inconsistent），valid_count=2，highest_contiguous=2。

### 2. 后端响应序列化（`src/storyforge3/api/routes/books.py`）

`BookReconciliationResponse` / `ChapterConsistencyResponse` 加上述新字段。`GET /reconcile` 返回完整新 shape（向后兼容，纯增字段）。

### 3. 前端精细化（`web/src/components/chapters/ChapterList.tsx` + `ChapterCard`）

- **顶部文案**：`真实产物 {maxChapter} 章` → `已发现章节产物 {chapters.length} 章 · 最高第 {maxChapter} 章`；若 `has_blocking_inconsistency` 加 `· ⚠ {inconsistent_count} 章数据不一致`。
- **NextChapterIndicator 用 `next_writable_chapter_no`**（不再 `maxChapter+1`）：
  - 若 `has_blocking_inconsistency`：显示 `⚠ 存在数据不一致（第 X、Y 章），请先检查后再继续生产`，**不**建议续写章号。
  - 否则：`下一章：第 {next_writable} 章 · 尚未产生章节产物，由 agent/API 启动生产`。
- **ChapterCard validity 徽标**：orphan 章（ch3/4）既有「数据不一致」，补 `orphan` 语义说明（如「孤儿产物：有 Truth/导出但无正文」）；partial 章标「部分产物」。

## Part 3：借鉴来源

| 借鉴 | 来源 | 方式 |
|------|------|------|
| reconcile 扫描逻辑 | `chapter_reconciler.py`（P1-1b） | **直接扩展**（加派生字段，不改扫描） |
| 响应模型 | `books.py:45-103` `BookReconciliationResponse`（P-IMP-3 已扩过一轮） | **直接扩展** |
| inconsistent reason 中文映射 | `ChapterList` 既有 `inconsistentReasonLabel()`（P-IMP-3） | **直接复用 + 扩 validity** |
| 分析师文档建议 | `docs/章节按进度展示体验分析与改进建议.md` §7-§10 | **设计采纳**（PM 对 §8.4 做了「阻断优先」改进） |

**新写比例**：约 **30%**。纯派生字段 + 文案/指示器逻辑，无新扫描、无新端点。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥565 不退步
.\.venv\Scripts\python.exe -m ruff check .               # clean
pnpm --dir web typecheck                                 # clean
pnpm --dir web test                                      # 全绿
```

手动（`storyforge3 dev` 对《别打了》）：
- `GET /reconcile` 返回 `valid_chapter_count=2`、`highest_contiguous_chapter=2`、`next_writable_chapter_no=3`、`has_blocking_inconsistency=true`。
- 章节列表顶部：`已发现章节产物 4 章 · 最高第 4 章 · ⚠ 2 章数据不一致`（**不再**显示「真实产物 4 章」误导）。
- 下一章指示器：`⚠ 存在数据不一致（第 3、4 章），请先检查后再继续生产`（**不再**「第 5 章」）。

## 必须覆盖的测试

- Reconciler：`valid_chapter_count` / `highest_contiguous` / `next_writable`（含幽灵 gap 场景）/ `has_blocking_inconsistency` / `validity` 分类（valid/partial/orphan/empty）。
- 《别打了》真实数据 fixture：断言上述四字段期望值。
- 前端：顶部文案正确 / 指示器阻断态文案 / ChapterCard orphan 徽标。

## 红线

- ❌ 不 heal / 不删 ch3/ch4（PM 验收可见性后再决定）。
- ❌ 不改 `book.json.current_chapter` 值。
- ❌ 不加运行按钮（agent-mode-only）。
- ❌ 不改 reconcile 扫描逻辑（只加派生字段）。
- ❌ next_writable 在有 inconsistent 时**不**建议续写，只定位异常章（PM 裁决，优于分析师 §8.4）。

## 回报

- commit hash（建议 `feat(reconcile): validity classification + next-writable derivation + chapter label fixes`）
- pytest + ruff + typecheck + 前端 test
- 《别打了》`GET /reconcile` 新字段输出 + 章节列表顶部文案 + 指示器截图/DOM

## Out of Scope

- ❌ heal/修复幽灵章（独立 PM 决策）。
- ❌ 卷进度摘要（分析师 §11.4，留后续）。
- ❌ P1-3 门禁统一 `allowedActions()`（独立指令）。
- ❌ P-IMP-2/P-IMP-4（独立指令）。
