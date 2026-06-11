# Codex 指令：Phase 6B-2 — 短篇管线前端 + 前端 API 补齐

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 6B-1 完成（372 后端 tests, 34 前端 tests, ruff clean）

---

## 任务概述

Phase 6B-1 交付了短篇管线后端（8 个 API 端点 + ShortStoryService + prompt 模板）。本阶段交付短篇前端 UI 和补齐前端 API 缺口。

**三部分工作**：

1. 短篇前端页面（列表 + 详情 + 管线操作 + 正文预览）
2. 短篇前端 API + React Query hooks
3. 补齐 fanfic / daemon / export 前端 API 模块

**核心原则**：复用现有 UI 组件和模式（BookList/BookCard/CreateBookDialog/ChapterPipeline/ChapterEditor），不做设计创新，保持视觉一致性。

---

## Part 1：短篇前端页面

### 1.1 路由

在 `App.tsx` 中新增两个路由：

```
/shorts           → ShortsPage       （短篇列表 + 创建入口）
/shorts/:id       → ShortDetailPage  （短篇详情 + 管线操作）
```

放在 `/books` 路由旁边，同样的 `<AppLayout>` 包裹。

### 1.2 ShortsPage（短篇列表页）

**参考**：`BooksPage.tsx`（23 行）

```
组成：
- Header（"短篇小说" + 描述）
- CreateShortDialog（创建对话框）
- ShortList（短篇卡片列表）
```

**导航入口**：在 `AppLayout` 的侧边栏添加"短篇"导航项，图标用 `FileText`（Lucide），位置在"书籍"下方。

### 1.3 CreateShortDialog（短篇创建对话框）

**参考**：`CreateBookDialog.tsx`（105 行）

```
表单字段：
- title（必填，书名）
- genre（必填，下拉选择：xuanhuan/xianxia/urban/horror/sci-fi/other）
- target_chars（数字输入，默认 10000，范围 5000-20000）
- premise（多行文本，核心设定/一句话简介）
- style（单行文本，风格要求，可选）

提交后：
- 调用 shortStoriesApi.create()
- toast 成功提示
- 导航到 /shorts/{book_id}
```

### 1.4 ShortList + ShortCard

**参考**：`BookList.tsx`（37 行）+ `BookCard.tsx`（59 行）

```
ShortList：
- 复用 Skeleton + EmptyState + Grid 模式
- 无短篇时显示 EmptyState："还没有短篇小说，点击上方创建第一篇"

ShortCard：
- 标题 + 类型 badge
- 状态 badge（颜色映射：empty=gray, planned=blue, drafted=yellow, audited=orange, revised=green, exported=emerald）
- 字数：目标 / 实际
- 最后更新时间
- 点击跳转 /shorts/{book_id}
```

### 1.5 ShortDetailPage（短篇详情页）

**参考**：`BookDetailPage.tsx`（但简化为单页，不用 tab）

```
布局（自上而下）：

1. 标题栏
   - 短篇标题 + 状态 badge + 类型 badge
   - 返回按钮（← 短篇小说）
   - 目标字数 / 实际字数

2. ShortPipeline（管线操作面板）
   - 5 个步骤按钮：构思 → 起草 → 审计 → 修订 → 导出
   - "一键运行"按钮
   - 审计结果面板（复用 AuditResultPanel 或内联展示）
   - **参考 ChapterPipeline.tsx（152 行）的 step 状态逻辑**

3. 正文预览
   - 复用 ChapterEditor（readOnly={true}）
   - 无正文时显示 placeholder："等待起草..."
```

### 1.6 ShortPipeline（短篇管线面板）

**参考**：`ChapterPipeline.tsx`（152 行），简化版

```
步骤定义（对比长篇 6 步）：

const steps = [
  { key: "plan",   label: "构思", done: ["planned", "drafted", "audited", "revised", "exported"] },
  { key: "draft",  label: "起草", done: ["drafted", "audited", "revise", "exported"] },
  { key: "audit",  label: "审计", done: ["audited", "revised", "exported"] },
  { key: "revise", label: "修订", done: ["revised", "exported"] },
  { key: "export", label: "导出", done: ["exported"] },
];

操作：
- 每个步骤一个按钮，完成后显示 ✓
- "一键运行"按钮触发 runFullPipeline
- 忙碌时所有按钮 disabled，显示 spinner
- 成功/失败 toast 通知（复用 toast 模式）
- 审计结果保存到本地 state，在管线下方展示

状态判断：
- 从 ShortStoryResult.status 映射到当前步骤
- empty → 所有步骤未完成
- planned → plan 完成
- drafted → plan + draft 完成
- 以此类推
```

### 1.7 导出功能

```
短篇导出按钮：
- 弹出格式选择（tomato_txt / txt / md / epub / qidian_txt）
- 调用 shortStoriesApi.export(bookId, fmt)
- 成功后 toast 提示导出路径
- Tauri 模式下：调用 exportChapterDesktop() 的短篇等价（或复用）
```

---

## Part 2：短篇前端 API + React Query Hooks

### 2.1 `web/src/api/shorts.ts`（新建，~50 行）

**参考**：`api/books.ts`（29 行）+ `api/chapters.ts`（67 行）

```typescript
// TypeScript 类型
interface ShortStoryMeta {
  book_id: string;
  title: string;
  genre: string;
  status: string;
  target_chars: number;
  premise: string;
  style: string;
  actual_chars: number;
  created_at: string;
  updated_at: string;
}

interface ShortStoryPlan {
  book_id: string;
  premise: string;
  opening: string;
  climax: string;
  ending: string;
  characters: string;
  key_scenes: string[];
  must_keep: string[];
  must_avoid: string[];
}

interface CreateShortRequest {
  title: string;
  genre: string;
  target_chars?: number;
  premise?: string;
  style?: string;
}

// API 对象
export const shortStoriesApi = {
  create: (data: CreateShortRequest) =>
    api.post<ShortStoryMeta>("/short-stories", data),

  get: (bookId: string) =>
    api.get<ShortStoryResult>(`/short-stories/${bookId}`),

  plan: (bookId: string) =>
    api.post<ShortStoryPlan>(`/short-stories/${bookId}/plan`),

  draft: (bookId: string) =>
    api.post<{ text: string }>(`/short-stories/${bookId}/draft`),

  audit: (bookId: string) =>
    api.post<AuditResult>(`/short-stories/${bookId}/audit`),

  revise: (bookId: string) =>
    api.post<ShortStoryResult>(`/short-stories/${bookId}/revise`),

  export: (bookId: string, fmt: string = "tomato_txt") =>
    api.post<{ path: string }>(`/short-stories/${bookId}/export`, { fmt }),

  runFullPipeline: (bookId: string) =>
    api.post<ShortStoryResult>(`/short-stories/${bookId}/run`),
};
```

**重要**：响应格式遵循后端的 `ok` 信封（`{ ok: true, data: {...} }`）。`api.post` 已经自动解包信封。

### 2.2 `web/src/hooks/useShorts.ts`（新建，~60 行）

**参考**：`hooks/useBooks.ts`（25 行）+ `hooks/useChapters.ts`（54 行）

```typescript
// Query hooks
useShorts()             → UseQueryResult<ShortStoryMeta[]>
useShort(bookId)        → UseQueryResult<ShortStoryResult>

// Mutation hooks
useCreateShort()        → UseMutationResult
useShortPlan(bookId)    → UseMutationResult
useShortDraft(bookId)   → UseMutationResult
useShortAudit(bookId)   → UseMutationResult
useShortRevise(bookId)  → UseMutationResult
useShortExport(bookId)  → UseMutationResult
useShortRunFull(bookId) → UseMutationResult

// Query key factory
shortKey(bookId)        → ["short", bookId]
shortsKey()             → ["shorts"]
```

**Mutation 成功后失效**：
- 单个操作 → invalidateQueries `shortKey(bookId)`
- 创建 → invalidateQueries `shortsKey()`

**注意**：短篇列表没有独立的 list API 端点。需要变通处理：
- 方案 A：用 `booksApi.list()` 过滤出有 `short_story` 状态的（但后端 list 不返回短篇）
- 方案 B：暂不实现列表页的数据加载，只在详情页操作
- **推荐方案 C**：后端 `GET /api/short-stories` 返回的 `get_status()` 实际上可以当列表用，但当前后端只有单个 GET。可以在后端不改动的情况下，前端列表暂时通过其他方式获取（例如在 books 列表中标记短篇类型）

**最终决策**：短篇列表需要后端支持。6B-1 的后端有 `GET /api/short-stories/{book_id}` 但没有 `GET /api/short-stories`（列表）。

**两种路径**：
- 路径 A（推荐）：让 Codex 在后端补充一个 `GET /api/short-stories` 列表端点（~10 行代码），返回所有 short_story.json 存在的书籍元数据
- 路径 B：前端通过 `booksApi.list()` 获取所有书籍，然后逐个检查是否有 short_story.json（N+1 查询，不推荐）

**选择路径 A**。Codex 需要在 `ShortStoryService` 中添加 `list_stories()` 方法，并在路由中添加 `GET /api/short-stories` 端点。

### 2.3 短篇列表后端补充

在 `src/storyforge3/services/short_story_service.py` 中添加：

```python
def list_stories(self) -> list[ShortStoryMeta]:
    """List all short stories."""
    stories = []
    for book_dir in self.paths.books_root.iterdir():
        if not book_dir.is_dir():
            continue
        meta_path = book_dir / "short_story.json"
        if meta_path.exists():
            meta = self._load_meta(book_dir.name)
            if meta:
                stories.append(meta)
    return stories
```

在 `src/storyforge3/api/routes/short_story.py` 中添加：

```python
@router.get("")
async def list_short_stories(
    service: ShortStoryService = Depends(get_short_story_service),
):
    stories = service.list_stories()
    return ok([_meta_to_response(s) for s in stories])
```

**注意**：新端点 `GET /api/short-stories`（无 book_id 参数）要放在 `GET /api/short-stories/{book_id}` 之前，避免路由冲突。

同时更新 `ShortStoryServiceProtocol` 添加 `list_stories()` 方法签名。

---

## Part 3：前端 API 缺口补齐

### 3.1 `web/src/api/fanfic.ts`（新建，~30 行）

```typescript
export const fanficApi = {
  importCanon: (bookId: string, data: { source_text: string; source_name: string; mode: string }) =>
    api.post(`/books/${bookId}/fanfic/import`, data),

  getCanon: (bookId: string) =>
    api.get(`/books/${bookId}/fanfic/canon`),

  refreshCanon: (bookId: string, data: { source_text: string }) =>
    api.post(`/books/${bookId}/fanfic/refresh`, data),
};
```

### 3.2 `web/src/api/daemon.ts`（新建，~15 行）

```typescript
export const daemonApi = {
  start: (bookId: string) =>
    api.post(`/books/${bookId}/daemon/start`),
};
```

### 3.3 `web/src/api/exports.ts`（新建，~20 行）

```typescript
export const exportsApi = {
  exportBook: (bookId: string, fmt: string = "tomato_txt") =>
    api.post(`/books/${bookId}/export`, { fmt }),

  getExportFile: (bookId: string, filename: string) =>
    api.get(`/books/${bookId}/exports/${filename}`),
};
```

### 3.4 补齐 chapters.ts 缺失函数

在 `web/src/api/chapters.ts` 中补充：

```typescript
// 新增
llmAudit: (bookId: string, chapterNo: number) =>
  api.post(`/books/${bookId}/chapters/${chapterNo}/llm-audit`),

normalize: (bookId: string, chapterNo: number) =>
  api.post(`/books/${bookId}/chapters/${chapterNo}/normalize`),
```

### 3.5 补齐 truth.ts 缺失函数

在 `web/src/api/truth.ts` 中补充：

```typescript
// 新增
extract: (bookId: string, chapterNo: number) =>
  api.post(`/books/${bookId}/truth/extract`, { chapter_no: chapterNo }),
```

---

## 文件改动清单

### 前端新增（~500 行）

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| `web/src/api/shorts.ts` | 新建 | ~50 | 短篇 API 函数 |
| `web/src/api/fanfic.ts` | 新建 | ~30 | 同人 API 函数 |
| `web/src/api/daemon.ts` | 新建 | ~15 | 守护进程 API 函数 |
| `web/src/api/exports.ts` | 新建 | ~20 | 书级导出 API 函数 |
| `web/src/hooks/useShorts.ts` | 新建 | ~60 | 短篇 React Query hooks |
| `web/src/pages/ShortsPage.tsx` | 新建 | ~40 | 短篇列表页 |
| `web/src/pages/ShortDetailPage.tsx` | 新建 | ~100 | 短篇详情页（含管线 + 预览） |
| `web/src/components/shorts/ShortList.tsx` | 新建 | ~40 | 短篇卡片列表 |
| `web/src/components/shorts/ShortCard.tsx` | 新建 | ~60 | 短篇卡片 |
| `web/src/components/shorts/CreateShortDialog.tsx` | 新建 | ~100 | 短篇创建对话框 |
| `web/src/components/shorts/ShortPipeline.tsx` | 新建 | ~130 | 短篇管线面板 |
| `web/src/components/shorts/index.ts` | 新建 | ~5 | barrel export |

### 前端修改

| 文件 | 操作 | 说明 |
|------|------|------|
| `web/src/App.tsx` | 修改 | 添加 `/shorts` 和 `/shorts/:id` 路由 |
| `web/src/components/layout/AppLayout.tsx` | 修改 | 侧边栏添加"短篇"导航项 |
| `web/src/api/chapters.ts` | 修改 | 补充 `llmAudit` + `normalize` |
| `web/src/api/truth.ts` | 修改 | 补充 `extract` |

### 后端修改（小量）

| 文件 | 操作 | 行数 | 说明 |
|------|------|------|------|
| `src/storyforge3/services/short_story_service.py` | 修改 | +10 | `list_stories()` 方法 |
| `src/storyforge3/api/routes/short_story.py` | 修改 | +8 | `GET /api/short-stories` 端点 |
| `src/storyforge3/services/protocols.py` | 修改 | +2 | `list_stories()` 协议方法 |

---

## 测试

### 前端测试新增

| 文件 | 说明 |
|------|------|
| `tests/api_shorts.test.ts` | API 函数测试（mock fetch） |
| `tests/ShortPipeline.test.tsx` | 管线面板渲染 + 步骤状态测试 |

测试要点：
1. `shortStoriesApi.create()` 调用正确的 endpoint
2. `shortStoriesApi.runFullPipeline()` 调用正确的 endpoint
3. ShortPipeline 渲染 5 个步骤按钮
4. ShortPipeline 根据 status 正确标记完成状态
5. CreateShortDialog 表单验证（title 必填）

### 后端测试新增

| 文件 | 说明 |
|------|------|
| `tests/test_short_story_service.py` | 补充 `test_list_stories` |
| `tests/api/test_short_story.py` | 补充 `test_list_short_stories_200` |

### 验证命令

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 374+ tests
ruff check .
cd web
pnpm test                                         # 36+ tests
pnpm build                                        # 零错误
```

---

## 验收标准

### 短篇前端

- [ ] `/shorts` 路由可访问，显示短篇列表
- [ ] CreateShortDialog 可创建短篇（title/genre/target_chars/premise/style）
- [ ] `/shorts/:id` 路由可访问，显示短篇详情
- [ ] ShortPipeline 显示 5 个步骤（构思→起草→审计→修订→导出）
- [ ] 每个步骤按钮触发对应 API 调用
- [ ] "一键运行"按钮触发 runFullPipeline
- [ ] 正文预览复用 ChapterEditor（readOnly）
- [ ] 导出支持格式选择
- [ ] 侧边栏有"短篇"导航入口

### 短篇 API

- [ ] `shortStoriesApi` 覆盖全部 8 个后端端点
- [ ] `useShorts` / `useShort` 查询 hook 正确失效缓存
- [ ] 后端新增 `GET /api/short-stories` 列表端点
- [ ] ShortStoryServiceProtocol 包含 `list_stories()`

### API 缺口补齐

- [ ] `fanficApi` 覆盖 3 个同人端点
- [ ] `daemonApi` 覆盖 1 个守护进程端点
- [ ] `exportsApi` 覆盖 2 个导出端点
- [ ] `chaptersApi` 补充 `llmAudit` + `normalize`
- [ ] `truthApi` 补充 `extract`

### 隔离性

- [ ] 372 后端 tests 不退步（+2 新增列表测试 = 374）
- [ ] 34 前端 tests 不退步（+2 新增）
- [ ] ruff check clean
- [ ] pnpm build clean（仅保留既有的 CodeMirror chunk 警告）

---

## 不在 6B-2 范围内

| 功能 | 归属 | 原因 |
|------|------|------|
| 短篇可编辑模式 | 后续 | 先用只读预览 |
| 同人模式前端 UI | 后续 | 本阶段只补 API 函数 |
| 守护进程前端 UI | 后续 | 本阶段只补 API 函数 |
| MCP Server | 6E | 下一阶段 |

---

## 参考文件

### 必须读取（理解现有模式）

1. **`web/src/api/books.ts`** — API 函数模式
2. **`web/src/api/chapters.ts`** — 管线 API 函数模式
3. **`web/src/api/client.ts`** — 基础 API 客户端
4. **`web/src/hooks/useBooks.ts`** — React Query hooks 模式
5. **`web/src/hooks/useChapters.ts`** — 管线 mutation hooks 模式
6. **`web/src/components/books/BookList.tsx`** — 列表组件模式
7. **`web/src/components/books/BookCard.tsx`** — 卡片组件模式
8. **`web/src/components/books/CreateBookDialog.tsx`** — 创建对话框模式
9. **`web/src/components/chapters/ChapterPipeline.tsx`** — 管线面板模式（重点参考）
10. **`web/src/components/editor/ChapterEditor.tsx`** — 编辑器组件（复用只读模式）
11. **`web/src/pages/BooksPage.tsx`** — 页面组合模式
12. **`web/src/App.tsx`** — 路由配置
13. **`web/src/components/layout/AppLayout.tsx`** — 侧边栏导航

### 后端参考

14. **`src/storyforge3/services/short_story_service.py`** — 短篇 Service（6B-1 交付）
15. **`src/storyforge3/api/routes/short_story.py`** — 短篇 API 路由（6B-1 交付）
16. **`src/storyforge3/api/routes/fanfic.py`** — 同人 API 路由
17. **`src/storyforge3/api/routes/daemon.py`** — 守护进程 API 路由
18. **`src/storyforge3/api/routes/export.py`** — 导出 API 路由

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6B-2（短篇管线前端 + API 补齐）：

短篇前端页面：
- /shorts 路由：[状态]
- /shorts/:id 路由：[状态]
- CreateShortDialog：[状态 + 字段]
- ShortPipeline：[状态 + 步骤数]
- 正文预览：[状态 + 复用方式]
- 侧边栏导航：[状态]

短篇前端 API：
- shorts.ts：[状态 + 函数数]
- useShorts.ts：[状态 + hooks 数]
- 后端列表端点：[状态]

API 缺口补齐：
- fanfic.ts：[状态 + 函数数]
- daemon.ts：[状态 + 函数数]
- exports.ts：[状态 + 函数数]
- chapters.ts 补充：[状态 + 函数数]
- truth.ts 补充：[状态 + 函数数]

测试：
- 后端全量：[数量] passed
- 前端全量：[数量] passed
- ruff check：[状态]
- pnpm build：[状态]

改动文件列表：[...]
```
