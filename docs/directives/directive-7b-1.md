# Codex 指令：Phase 7B-1 — Truth 可视化面板

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7A 完成（462 tests: 412 后端 + 50 前端, ruff clean）

---

## 任务概述

让作者看到跨章真相数据。当前 Truth 系统在后端完整运行（提取 → 存储 → 检索），但前端零展示。作者是真相系统的盲人——不知道系统记住了什么、遗忘漏了什么、跨章连续性是否被维护。

**当前状态**：
- 后端 3 个 Truth API 端点：`GET /latest`、`GET /{chapter_no}`、`POST /extract`
- `TruthData` 含 7 个字段：`fact_assertions`、`character_updates`、`relationship_updates`、`hook_updates`、`irreversible_facts`、`notes`、`source`
- `TruthStore` 有 `load` + `load_latest`，**无 `load_history`**（Protocol 定义了但 Store 未实现）
- 前端 `truth.ts` API 存在（3 个函数），但无 hook、无组件、无 UI
- `BookDetailPage` 有 5 个 tab（概览/世界观/角色/卷/章节），**无 Truth tab**

**核心原则**：
1. **只读展示，不编辑**——Truth 由管线自动提取，作者只看不动
2. **按章节分组**——truth 数据天然与章节绑定，展示结构应反映这一点
3. **搜索过滤是核心交互**——跨章 truth 数据量大，搜索是发现关联的关键
4. **优先展示不可逆事实和钩子**——这两个类别对连续性最关键

---

## Part 1：后端 — 补齐 Truth History API

### 1.1 `TruthStore.load_history()`

**文件**：`src/storyforge3/truth/store.py`

Protocol 中已定义 `load_history` 但 Store 未实现。新增：

```python
def load_history(self, book_id: str) -> list[TruthData]:
    """加载全部章节的 truth 数据，按章节号升序。"""
    truth_dir = self.books_dir / book_id / "truth"
    if not truth_dir.exists():
        return []
    paths = sorted(truth_dir.glob("chapter-*.json"))
    results: list[TruthData] = []
    for path in paths:
        chapter_no = int(path.stem.split("-")[-1])
        truth = self.load(book_id, chapter_no)
        if truth is not None:
            results.append(truth)
    return results
```

**位置**：在 `load_latest()` 之后。

### 1.2 `GET /api/books/{book_id}/truth/history` 端点

**文件**：`src/storyforge3/api/routes/truth.py`

新增：

```python
@router.get("/history")
async def get_truth_history(
    book_id: str,
    store: TruthStore = Depends(get_truth_store),
):
    history = store.load_history(book_id)
    return ok([_truth_to_response(t) for t in history])
```

**注意**：路由注册顺序！`/history` 必须在 `/{chapter_no}` **之前**，否则 FastAPI 会把 `history` 当成 chapter_no 参数。当前文件中 `/{chapter_no}` 在 line 41，所以 `/history` 需要插在它前面。

### 1.3 不改 Protocol

`TruthServiceProtocol.load_history()` 已经定义，`TruthService.load_history()` 也已存在（委托给 Store）。只需补 Store 实现。

---

## Part 2：前端 — Truth 面板

### 2.1 API 补齐

**文件**：`web/src/api/truth.ts`

新增：

```typescript
export const truthApi = {
  // ... 现有 3 个函数 ...
  history: (bookId: string) => api.get<TruthData[]>(`/api/books/${bookId}/truth/history`),
};
```

### 2.2 Hook

**新文件**：`web/src/hooks/useTruth.ts`

```typescript
import { useQuery } from "@tanstack/react-query";
import { truthApi } from "@/api/truth";

export function useTruthHistory(bookId: string) {
  return useQuery({
    queryKey: ["truth-history", bookId],
    queryFn: () => truthApi.history(bookId),
    enabled: Boolean(bookId),
    retry: false,
  });
}

export function useTruthByChapter(bookId: string, chapterNo: number) {
  return useQuery({
    queryKey: ["truth-chapter", bookId, chapterNo],
    queryFn: () => truthApi.byChapter(bookId, chapterNo),
    enabled: Boolean(bookId && chapterNo),
    retry: false,
  });
}
```

### 2.3 TruthPanel 组件

**新文件**：`web/src/components/truth/TruthPanel.tsx`

**布局**：

```
┌───────────────────────────────────────────────────────┐
│  🧠 真相数据                           [搜索框...]    │
│  第 1 章  第 2 章  第 3 章  ...  全部                 │
├───────────────────────────────────────────────────────┤
│  第 1 章（3 事实 · 2 角色 · 1 钩子 · 0 不可逆）       │
│  ┌─ 事实断言 ────────────────────────────────────┐    │
│  │  • 林默获得存在感系统                           │    │
│  │  • 系统分为布/钉/宗三个阶段                      │    │
│  └───────────────────────────────────────────────┘    │
│  ┌─ 角色更新 ────────────────────────────────────┐    │
│  │  • 林默: 觉醒存在感系统                         │    │
│  │  • 王老师: 对林默态度从忽视变为疑惑               │    │
│  └───────────────────────────────────────────────┘    │
│  ┌─ 不可逆事实 ⚠ ───────────────────────────────┐    │
│  │  （本章无）                                     │    │
│  └───────────────────────────────────────────────┘    │
├───────────────────────────────────────────────────────┤
│  第 2 章（4 事实 · 1 角色 · 2 钩子 · 1 不可逆）       │
│  ...                                                  │
└───────────────────────────────────────────────────────┘
```

**Props**：

```typescript
interface TruthPanelProps {
  bookId: string;
}
```

**核心功能**：

1. **加载 truth history**：调用 `useTruthHistory(bookId)`
2. **章节标签栏**：横向排列所有有 truth 数据的章节号 + "全部"按钮。点击某章只展示该章 truth，点击"全部"展示全部
3. **搜索过滤**：顶部搜索框，过滤显示包含关键词的 truth 条目（全文搜索 fact_assertions、character_updates 的 summary/description、irreversible_facts、hook_updates、notes）
4. **按章节分组**：每组显示章节号 + 各类别数量统计
5. **分类折叠**：每个章节内按 5 个类别分组展示（事实断言、角色更新、关系更新、钩子、不可逆事实、备注），每个类别可折叠

**分类渲染规则**：

| 字段 | 标签 | 图标 | 重要性 | 默认展开 |
|------|------|------|--------|---------|
| `irreversible_facts` | 不可逆事实 | `AlertTriangle` | 最高（黄/红高亮） | ✅ |
| `hook_updates` | 钩子 | `Anchor` | 高 | ✅ |
| `fact_assertions` | 事实断言 | `FileText` | 中 | ✅ |
| `character_updates` | 角色更新 | `UserCircle` | 中 | ✅ |
| `relationship_updates` | 关系更新 | `Users` | 中 | ❌ |
| `notes` | 备注 | `StickyNote` | 低 | ❌ |

**空状态**：无 truth 数据时显示"暂无真相数据。运行章节管线后，真相会在 audit 通过后自动提取。"

**搜索实现**：

```typescript
function filterTruth(history: TruthData[], query: string): TruthData[] {
  if (!query.trim()) return history;
  const q = query.toLowerCase();
  return history
    .map(t => ({
      ...t,
      fact_assertions: t.fact_assertions.filter(s => s.toLowerCase().includes(q)),
      character_updates: t.character_updates.filter(d =>
        JSON.stringify(d).toLowerCase().includes(q)
      ),
      relationship_updates: t.relationship_updates.filter(d =>
        JSON.stringify(d).toLowerCase().includes(q)
      ),
      hook_updates: t.hook_updates.filter(d =>
        JSON.stringify(d).toLowerCase().includes(q)
      ),
      irreversible_facts: t.irreversible_facts.filter(s => s.toLowerCase().includes(q)),
      notes: t.notes.filter(s => s.toLowerCase().includes(q)),
    }))
    .filter(t =>
      t.fact_assertions.length > 0 ||
      t.character_updates.length > 0 ||
      t.relationship_updates.length > 0 ||
      t.hook_updates.length > 0 ||
      t.irreversible_facts.length > 0 ||
      t.notes.length > 0
    );
}
```

### 2.4 BookDetailPage 新增 Truth Tab

**文件**：`web/src/pages/BookDetailPage.tsx`

在 tabs 中新增"真相"tab（在"章节"之后）：

```tsx
<TabsTrigger value="truth">真相</TabsTrigger>
```

```tsx
<TabsContent value="truth">
  <TruthPanel bookId={id} />
</TabsContent>
```

更新 `validTab` 函数：`["overview", "world", "characters", "volumes", "chapters", "truth"]`

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| Truth API 函数 | `web/src/api/truth.ts` | 已有 3 个函数，新增 history |
| TruthData 模型 | `web/src/api/truth.ts` + `models.py` | 已有接口，直接使用 |
| Tab 注册模式 | `BookDetailPage.tsx:82-89` | 复用 TabsTrigger/TabsContent 模式 |
| 面板布局 | `AuditResultPanel.tsx` | 复用 Card + 分类折叠模式 |
| Hook 模式 | `hooks/useChapters.ts` | 复用 useQuery 模式 |
| 搜索过滤 | 前端标准 `filter` | 纯前端过滤，无后端搜索 |
| `load_history` 逻辑 | `store.py:load_latest()` | 复用 glob + sorted 模式 |

**新写比例**：约 35%。API/hook/数据模型大部分已存在，新增的是展示层和一个 Store 方法。

---

## 验收标准

### 后端

- [ ] `TruthStore.load_history()` 按章节升序返回全部 truth 数据
- [ ] `GET /api/books/{book_id}/truth/history` 返回 `TruthDataResponse[]`
- [ ] `/history` 路由在 `/{chapter_no}` 之前注册
- [ ] 现有 412 tests 不退步

### 前端

- [ ] `BookDetailPage` 新增"真相"tab
- [ ] `TruthPanel` 加载 truth history 并按章节分组展示
- [ ] 5 个分类（事实/角色/关系/钩子/不可逆/备注）分别展示
- [ ] 不可逆事实高亮（重要性最高）
- [ ] 章节标签栏切换某章/全部
- [ ] 搜索框过滤 truth 条目
- [ ] 空 truth 优雅降级
- [ ] `useTruthHistory` + `useTruthByChapter` hooks

### 测试

- [ ] 后端：`TruthStore.load_history()` 测试（空书/多章 truth/排序）
- [ ] 后端：`GET /truth/history` API 测试
- [ ] 前端：`TruthPanel` 渲染测试（有多章 truth/空 truth/搜索过滤）
- [ ] 前端：`truthApi.history` 函数测试
- [ ] 462 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端 Store | `truth/store.py` | ~12 行 |
| 后端 API | `routes/truth.py` | ~5 行 |
| 后端测试 | `test_truth.py` | ~30 行 |
| 前端 API | `api/truth.ts` | ~1 行 |
| 前端 Hook | `hooks/useTruth.ts` | ~20 行 |
| 前端 TruthPanel | `truth/TruthPanel.tsx` | ~150 行 |
| 前端 BookDetailPage | `BookDetailPage.tsx` | ~8 行 |
| 前端测试 | `__tests__/` | ~50 行 |
| **合计** | **~8 个文件** | **~280 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做 Truth 编辑——truth 由管线自动提取，作者只看不动
- ❌ 不做 Truth 删除/回滚——属于 7B-2 快照管理范畴
- ❌ 不做后端全文搜索——truth 数据量小（每章几十条），前端过滤足够
- ❌ 不做 Truth diff（跨章变化对比）——后续迭代
- ❌ 不做 Truth 导出——truth 数据已在导出快照中
- ❌ 不改 TruthService/TruthExtractor 逻辑——纯展示层
