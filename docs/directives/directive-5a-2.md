# Codex 指令：Phase 5A-2 — Book Detail + Chapter Pipeline UI

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5A-1 完成（31 前端文件, 4 tests, tsc/build 通过, 301 后端测试不退步）

---

## 任务概述

在 5A-1 的前端 scaffold 基础上，构建 Book 详情页（多 Tab 布局）和 Chapter 管线操作界面。这是用户与引擎交互的核心页面——世界观编辑、角色管理、章节生产流水线都在这里完成。

---

## 后端 API 已就绪

以下 API 全部可用（Phase 4C 已验证）：

### World

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 构建世界观 | POST | `/api/books/{id}/world` | 从类型和种子生成 |
| 获取世界观 | GET | `/api/books/{id}/world` | 返回 WorldConfig |
| 更新世界观 | PUT | `/api/books/{id}/world` | 更新 setting/power_system/core_conflict/rules |

### Characters

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 创建角色 | POST | `/api/books/{id}/characters` | 单个角色 |
| 批量创建 | POST | `/api/books/{id}/characters/batch` | 多个角色 |
| 角色列表 | GET | `/api/books/{id}/characters` | 所有角色 |
| 角色关系 | GET | `/api/books/{id}/characters/relationships` | 关系网络 |
| 更新角色 | PATCH | `/api/books/{id}/characters/{name}` | 更新字段 |

### Volumes

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 规划卷 | POST | `/api/books/{id}/volumes` | 生成卷大纲 |
| 卷列表 | GET | `/api/books/{id}/volumes` | 所有卷 |
| 卷详情 | GET | `/api/books/{id}/volumes/{volume_no}` | 单卷 |
| 更新卷 | PUT | `/api/books/{id}/volumes/{volume_no}` | 更新卷大纲 |

### Chapters（核心管线）

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 章节规划 | POST | `/api/books/{id}/chapters/{no}/plan` | 生成 ChapterIntent |
| 章节起草 | POST | `/api/books/{id}/chapters/{no}/draft` | 从 intent 起草 |
| 机械审计 | POST | `/api/books/{id}/chapters/{no}/audit` | 36 条机械规则 |
| LLM 审计 | POST | `/api/books/{id}/chapters/{no}/llm-audit` | 4 维度 LLM 审计 |
| 长度归一化 | POST | `/api/books/{id}/chapters/{no}/normalize` | 归一化字数 |
| 修订 | POST | `/api/books/{id}/chapters/{no}/revise` | 5 种模式修订 |
| 批准 | POST | `/api/books/{id}/chapters/{no}/approve` | 批准进入导出 |
| 导出 | POST | `/api/books/{id}/chapters/{no}/export` | 单章导出 |
| 全流程 | POST | `/api/books/{id}/chapters/{no}/run` | 一键运行完整管线 |
| 章节状态 | GET | `/api/books/{id}/chapters/{no}/status` | 当前状态 |

### Truth

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 最新 Truth | GET | `/api/books/{id}/truth/latest` | 最新章节的 truth |
| 章节 Truth | GET | `/api/books/{id}/truth/{no}` | 指定章节 truth |
| 提取 Truth | POST | `/api/books/{id}/truth/extract` | 从文本提取 |

### SSE 实时事件

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 事件流 | GET | `/api/events?book_id={id}&chapter_no={no}` | 实时管线事件 |

### 响应格式

所有端点统一信封：`{"ok": true, "data": ..., "error": null}`

### 关键数据模型

```typescript
// WorldConfig
interface WorldConfig {
  book_id: string;
  setting: string;           // 世界观设定
  power_system: string;      // 力量体系
  core_conflict: string;     // 核心冲突
  rules: string[];           // 世界规则
}

// Character
interface Character {
  book_id: string;
  name: string;
  role: "PROTAGONIST" | "MAJOR" | "MINOR";
  profile: string;
  personality: string;
  abilities: string[];
  arc_direction: string;
}

// Relationship
interface Relationship {
  character_a: string;
  character_b: string;
  relation_type: string;
  description: string;
}

// VolumeOutline
interface VolumeOutline {
  book_id: string;
  volume_no: number;
  title: string;
  chapter_count: number;
  synopsis: string;
  key_scenes: string[];
  rhythm_curve: string[];
}

// ChapterResult (状态查询)
interface ChapterResult {
  book_id: string;
  chapter_no: number;
  status: "EMPTY" | "PLANNED" | "DRAFTED" | "SETTLED" | "AUDITED" | "NEEDS_REVISION" | "REVISED" | "APPROVED" | "EXPORTED" | "NEEDS_REVIEW";
  title: string;
  text: string;
}

// ChapterIntent (规划结果)
interface ChapterIntent {
  chapter_no: number;
  goal: string;
  outline_node: string;
  arc_context: string;
  must_keep: string[];
  must_avoid: string[];
  style_emphasis: string[];
}

// AuditResult
interface AuditResult {
  chapter_no: number;
  passed: boolean;
  blocking_issues: string[];
  warnings: string[];
  info: string[];
  rule_results: RuleResult[];
}

// RuleResult
interface RuleResult {
  rule_id: string;
  passed: boolean;
  severity: "INFO" | "WARNING" | "BLOCKING";
  category: "INTEGRITY" | "AI_TELL" | "STYLE" | "STRUCTURE" | "META";
  message: string;
  detail: Record<string, unknown>;
}

// TruthData
interface TruthData {
  chapter_no: number;
  source: string;
  fact_assertions: string[];
  character_updates: Record<string, unknown>[];
  relationship_updates: Record<string, unknown>[];
  hook_updates: Record<string, unknown>[];
  irreversible_facts: string[];
  notes: string[];
}

// PipelineEvent (SSE)
interface PipelineEvent {
  type: "pipeline:start" | "pipeline:complete" | "pipeline:error";
  book_id: string;
  chapter_no: number;
  stage: string;
  message: string;
  detail: Record<string, unknown> | null;
}
```

---

## 修改目标

### 1. 新增路由

在 `App.tsx` 中添加 `/books/:id` 路由，指向 `BookDetailPage`。

### 2. Book 详情页布局

**文件**：`src/pages/BookDetailPage.tsx`

使用 Tabs 布局（Radix Tabs），5 个标签页：

```
概览 | 世界观 | 角色 | 卷规划 | 章节
```

#### 概览 Tab

展示 Book 元数据 + 快速操作：
- 书名、类型、平台、状态
- 当前章节 / 目标章节（进度条）
- 快速操作按钮：「构建世界观」「规划卷」「运行全流程」

#### 世界观 Tab

**文件**：`src/components/world/WorldEditor.tsx`

- 展示 WorldConfig（setting / power_system / core_conflict / rules）
- 「构建世界观」按钮 → 调用 `POST /api/books/{id}/world`（需要 genre + seed_brief 输入）
- 编辑模式：textarea 编辑各字段 → `PUT /api/books/{id}/world` 保存
- 只读模式：首次构建前显示引导文案

#### 角色 Tab

**文件**：`src/components/characters/CharacterList.tsx` + `CreateCharacterDialog.tsx`

- 角色卡片列表（name / role badge / profile 摘要）
- 「添加角色」按钮 → Dialog 表单
- 点击角色卡片展开详情（profile / personality / abilities / arc_direction）

#### 卷规划 Tab

**文件**：`src/components/volumes/VolumeList.tsx`

- 卷列表（volume_no / title / chapter_count / synopsis）
- 「规划卷」按钮 → 输入 volume_count 和 total_chapters
- 点击单卷展示 key_scenes 和 rhythm_curve

#### 章节 Tab（核心重点）

**文件**：`src/components/chapters/ChapterList.tsx` + `ChapterCard.tsx` + `ChapterPipeline.tsx`

章节列表 + 管线操作，这是本阶段最重要的交付。

### 3. API 客户端扩展

新增以下 API 文件：

**`src/api/world.ts`**：
```typescript
export const worldApi = {
  get: (bookId: string) => api.get<WorldConfig>(`/api/books/${bookId}/world`),
  build: (bookId: string, genre: string, seedBrief: string) =>
    api.post<WorldConfig>(`/api/books/${bookId}/world`, { genre, seed_brief: seedBrief }),
  update: (bookId: string, world: Partial<WorldConfig>) =>
    api.put<WorldConfig>(`/api/books/${bookId}/world`, world),
};
```

**`src/api/characters.ts`**：
```typescript
export const charactersApi = {
  list: (bookId: string) => api.get<Character[]>(`/api/books/${bookId}/characters`),
  create: (bookId: string, spec: string) =>
    api.post<Character>(`/api/books/${bookId}/characters`, { spec }),
  createBatch: (bookId: string, specs: string[]) =>
    api.post<Character[]>(`/api/books/${bookId}/characters/batch`, { specs }),
  relationships: (bookId: string) =>
    api.get<Relationship[]>(`/api/books/${bookId}/characters/relationships`),
  update: (bookId: string, name: string, updates: Record<string, string>) =>
    api.patch<Character>(`/api/books/${bookId}/characters/${encodeURIComponent(name)}`, updates),
};
```

**`src/api/volumes.ts`**：
```typescript
export const volumesApi = {
  list: (bookId: string) => api.get<VolumeOutline[]>(`/api/books/${bookId}/volumes`),
  plan: (bookId: string, volumeCount: number, totalChapters: number) =>
    api.post<VolumeOutline[]>(`/api/books/${bookId}/volumes`, { volume_count: volumeCount, total_chapters: totalChapters }),
  get: (bookId: string, volumeNo: number) =>
    api.get<VolumeOutline>(`/api/books/${bookId}/volumes/${volumeNo}`),
  update: (bookId: string, volumeNo: number, outline: Partial<VolumeOutline>) =>
    api.put<VolumeOutline>(`/api/books/${bookId}/volumes/${volumeNo}`, outline),
};
```

**`src/api/chapters.ts`**：
```typescript
export const chaptersApi = {
  getStatus: (bookId: string, chapterNo: number) =>
    api.get<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/status`),
  plan: (bookId: string, chapterNo: number) =>
    api.post<ChapterIntent>(`/api/books/${bookId}/chapters/${chapterNo}/plan`),
  draft: (bookId: string, chapterNo: number) =>
    api.post<string>(`/api/books/${bookId}/chapters/${chapterNo}/draft`),
  audit: (bookId: string, chapterNo: number) =>
    api.post<AuditResult>(`/api/books/${bookId}/chapters/${chapterNo}/audit`),
  revise: (bookId: string, chapterNo: number, mode: string = "auto") =>
    api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/revise`, { mode }),
  approve: (bookId: string, chapterNo: number) =>
    api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/approve`),
  runFullPipeline: (bookId: string, chapterNo: number) =>
    api.post<ChapterResult>(`/api/books/${bookId}/chapters/${chapterNo}/run`),
};
```

**`src/api/truth.ts`**：
```typescript
export const truthApi = {
  latest: (bookId: string) => api.get<TruthData>(`/api/books/${bookId}/truth/latest`),
  byChapter: (bookId: string, chapterNo: number) =>
    api.get<TruthData>(`/api/books/${bookId}/truth/${chapterNo}`),
};
```

### 4. TanStack Query Hooks

**`src/hooks/useWorld.ts`**：
- `useWorld(bookId)` — query world config
- `useBuildWorld(bookId)` — mutation: build world
- `useUpdateWorld(bookId)` — mutation: update world

**`src/hooks/useCharacters.ts`**：
- `useCharacters(bookId)` — query character list
- `useCreateCharacter(bookId)` — mutation: create character
- `useCharacterRelationships(bookId)` — query relationships

**`src/hooks/useVolumes.ts`**：
- `useVolumes(bookId)` — query volume list
- `usePlanVolumes(bookId)` — mutation: plan volumes

**`src/hooks/useChapters.ts`**：
- `useChapterStatus(bookId, chapterNo)` — query single chapter status
- `useChapterPlan(bookId)` — mutation: plan a chapter
- `useChapterDraft(bookId)` — mutation: draft a chapter
- `useChapterAudit(bookId)` — mutation: audit a chapter
- `useChapterRevise(bookId)` — mutation: revise a chapter
- `useChapterApprove(bookId)` — mutation: approve a chapter
- `useRunFullPipeline(bookId)` — mutation: run full pipeline

### 5. 章节管线 UI 设计

这是本阶段的核心交付。设计要求：

#### ChapterList

- 每章一行卡片，展示：章节号、标题（或"未命名"）、状态徽章
- 状态徽章颜色：
  - EMPTY → 锌灰
  - PLANNED → 靛蓝
  - DRAFTED → 琥珀
  - AUDITED → 翠绿
  - NEEDS_REVISION / NEEDS_REVIEW → 红色
  - REVISED → 青色
  - APPROVED → 天蓝
  - EXPORTED → 翠绿实心
- 点击卡片展开该章节的管线操作面板

#### ChapterPipeline（展开面板）

```
┌─ 第 3 章 ─────────────────────────────────────────────┐
│ 状态: REVISED                                          │
│                                                        │
│ [规划] → [起草] → [审计] → [修订] → [批准] → [导出]  │
│            ✓       ✓       ✓       ←当前              │
│                                                        │
│ [▶ 运行全流程]  [刷新状态]                              │
│                                                        │
│ ┌── 文本预览 ──────────────────────────────────────┐   │
│ │ （只读 textarea，展示章节文本）                    │   │
│ └──────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

- 每个管线步骤是一个按钮，点击调用对应 API
- 已完成步骤显示 ✓ 标记
- 当前步骤按钮高亮
- 「运行全流程」调用 `POST /run`，执行完整管线
- 文本预览：只读 textarea（200px 高度），展示 ChapterResult.text
- 操作期间按钮显示 loading 状态

#### SSE 实时更新

当任何管线操作触发时，监听 SSE 事件：

```typescript
function usePipelineEvents(bookId?: string, chapterNo?: number) {
  // 连接 GET /api/events?book_id=X&chapter_no=Y
  // 收到事件后 invalidate 对应 query key
  // 显示 sonner toast 提示
}
```

SSE event 格式：
```json
{
  "type": "pipeline:start" | "pipeline:complete" | "pipeline:error",
  "book_id": "...",
  "chapter_no": 3,
  "stage": "draft",
  "message": "开始起草第 3 章...",
  "detail": null
}
```

### 6. 项目结构新增

```
storyforge3/web/src/
├── api/
│   ├── client.ts          # 已有
│   ├── books.ts           # 已有
│   ├── world.ts           # 新增
│   ├── characters.ts      # 新增
│   ├── volumes.ts         # 新增
│   ├── chapters.ts        # 新增
│   └── truth.ts           # 新增
├── hooks/
│   ├── useBooks.ts        # 已有
│   ├── useWorld.ts        # 新增
│   ├── useCharacters.ts   # 新增
│   ├── useVolumes.ts      # 新增
│   ├── useChapters.ts     # 新增
│   └── usePipelineEvents.ts  # 新增（SSE hook）
├── components/
│   ├── ui/                # 已有，可能需要新增 Tabs 组件
│   │   └── tabs.tsx       # 新增（基于 Radix Tabs）
│   ├── books/             # 已有
│   │   └── BookCard.tsx   # 已有，添加 Link 到 /books/:id
│   ├── world/
│   │   └── WorldEditor.tsx      # 新增
│   ├── characters/
│   │   ├── CharacterList.tsx     # 新增
│   │   └── CreateCharacterDialog.tsx  # 新增
│   ├── volumes/
│   │   └── VolumeList.tsx        # 新增
│   └── chapters/
│       ├── ChapterList.tsx       # 新增
│       ├── ChapterCard.tsx       # 新增
│       └── ChapterPipeline.tsx   # 新增
└── pages/
    ├── DashboardPage.tsx   # 已有
    ├── BooksPage.tsx       # 已有
    └── BookDetailPage.tsx  # 新增
```

### 7. BookCard 改造

已有 `BookCard.tsx` 需要添加导航：
- 点击卡片 → 导航到 `/books/{book_id}`
- 用 `react-router-dom` 的 `Link` 或 `useNavigate`

### 8. API 客户端扩展

在 `client.ts` 中添加 `put` 方法：
```typescript
put: <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
```

---

## UI 设计要求

延续 5A-1 的深色主题 + amber 强调色：

- **Tabs 组件**：下划线风格，激活标签 amber 色
- **ChapterCard**：紧凑行布局，状态徽章左对齐
- **ChapterPipeline**：步骤条（step bar）使用圆形节点 + 连线，已完成步骤 amber 实心
- **WorldEditor**：双列布局，左列标签右列 textarea
- **CharacterList**：卡片网格，role 用 Badge 区分（主角 amber，主要 zinc，次要 zinc/50% 透明度）
- **VolumeList**：时间线风格或紧凑列表
- **Loading 状态**：所有 mutation 操作期间按钮显示 spinner + disabled
- **错误展示**：mutation 失败 → sonner error toast

---

## 技术约束

1. **组件 ≤300 行**：超出则拆分
2. **TypeScript strict**：所有新文件必须有类型标注
3. **API 客户端统一走 `client.ts`**：不直接使用 fetch
4. **SSE 用原生 `EventSource`**：不引入第三方库
5. **不引入状态管理库**：TanStack Query + React state
6. **中文 UI**：所有文案中文
7. **管线操作串行**：同章节的多个操作必须等前一个完成才能发下一个（按钮 disabled 控制）

---

## 验收

```powershell
cd storyforge3/web
pnpm typecheck     # TypeScript 编译无错误
pnpm build         # 生产构建无错误
pnpm test          # 所有前端测试通过
```

功能验收：
1. Book 列表卡片可点击 → 导航到 `/books/{id}`
2. Book 详情页展示 5 个 Tab
3. 世界观 Tab：显示 WorldConfig 或引导构建
4. 角色 Tab：显示角色列表 + 创建按钮
5. 章节 Tab：显示章节列表，每章有状态徽章
6. 章节管线操作：点击「规划」→ 调用 API → 状态刷新
7. 章节全流程：点击「运行全流程」→ loading → 完成后状态更新
8. SSE 事件：管线运行中 toast 显示进度
9. 文本预览：展开面板显示章节文本

后端验收：
```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 301 测试不退步
```

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5A-2（Book Detail + Chapter Pipeline）：
- Book 详情页（5 Tab）：[完成状态]
- 世界观编辑器：[完成状态]
- 角色管理：[完成状态]
- 卷规划：[完成状态]
- 章节列表 + 管线操作：[完成状态]
- SSE 实时更新：[完成状态]
- 文本预览：[完成状态]
- pnpm build：[通过/失败]
- TypeScript 编译：[通过/失败]
- 新增文件数：N
- 前端测试数：M
- 后端测试：301 passed [是/否]
```

---

## 参考文件

读取以下文件作为技术参考：

1. `storyforge3/web/src/api/client.ts` — 已有 API 客户端，扩展 put 方法
2. `storyforge3/web/src/components/ui/` — 已有 shadcn/ui 组件
3. `storyforge3/web/src/hooks/useBooks.ts` — 已有 TanStack Query hooks 模式
4. `storyforge3/src/storyforge3/api/routes/` — 后端所有 API 路由
5. `storyforge3/src/storyforge3/models.py` — 后端数据模型
6. `storyforge3/src/storyforge3/services/protocols.py` — Service 协议定义
