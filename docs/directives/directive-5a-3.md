# Codex 指令：Phase 5A-3 — Dashboard 增强 + 视觉打磨

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5A-2 完成（9 tests, tsc/build 通过, 301 后端测试不退步）

---

## 任务概述

5A-1 搭了 scaffold，5A-2 做了核心功能页。5A-3 是打磨阶段：升级 Dashboard 为真正的信息中枢、增强审计结果可视化、添加主题切换，并做一轮全局视觉打磨。

**本阶段不是堆功能，而是让已有功能好用、好看、完整。**

---

## 当前已有基础

5A-1 和 5A-2 已经交付：
- Dashboard 页面（基础版：书籍数量、连载中数量、可用能力数）
- Book 列表/创建/详情
- Book Detail 5 个 Tab（概览/世界观/角色/卷规划/章节）
- Chapter Pipeline（6 步操作 + 全流程 + SSE + 文本预览）
- Loading skeleton（BookList）、Empty state（BookList、CharacterList、VolumeList）
- Toast 通知（CreateBookDialog、WorldEditor、VolumeList、ChapterPipeline、SSE hook）
- 深色主题（amber + zinc）

---

## 修改目标

### 1. Dashboard 增强

**文件**：`src/pages/DashboardPage.tsx`（已有，重写）

当前 Dashboard 只有静态指标卡片。升级为：

#### 1a. Provider 健康状态卡片

调用 `GET /api/providers` 和 `GET /api/health`：

```typescript
// 已有 API 端点
// GET /api/health → { status: "ok", default_model: "...", books_dir: "..." }
// GET /api/providers → [{ id, provider_key, label, base_url, model_id, enabled }]
```

展示：
- Provider 名称 + model_id
- 在线状态指示灯（绿点 = 配置存在，灰点 = 未配置）
- 当前活跃 provider 标记

#### 1b. 最近活动流

基于 `useBooks()` 的书籍列表，展示最近创建/更新的书籍（按 `updated_at` 降序，取前 5 条）。每条显示：书名、状态、更新时间。

不需要新的 API，现有 `GET /api/books` 已返回 `updated_at`。

#### 1c. 快速操作卡片

保留现有 Dashboard 的「打开我的小说」入口，额外添加：
- 「构建世界观」→ 导航到最近 active 书籍的世界观 Tab
- 「运行全流程」→ 导航到最近 active 书籍的章节 Tab

### 2. API 客户端补充

**文件**：`src/api/health.ts`（新增）

```typescript
import { api } from "./client";

export interface HealthStatus {
  status: string;
  default_model: string;
  books_dir: string;
}

export interface Provider {
  id: string;
  provider_key: string;
  label: string;
  base_url: string;
  model_id: string;
  enabled: boolean;
}

export const healthApi = {
  check: () => api.get<HealthStatus>("/api/health"),
  providers: () => api.get<Provider[]>("/api/providers"),
};
```

**文件**：`src/hooks/useHealth.ts`（新增）

```typescript
export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: healthApi.check });
}
export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: healthApi.providers });
}
```

### 3. 审计结果可视化

**文件**：`src/components/chapters/AuditResultPanel.tsx`（新增）

在 ChapterPipeline 的文本预览上方，添加审计结果面板（仅当章节状态为 `audited`、`needs_revision`、`revised` 时显示）。

目前 ChapterPipeline 没有单独获取审计结果的 API 调用。但实际上 `POST /api/books/{id}/chapters/{no}/audit` 返回 `AuditResult`。在管线操作中，audit 步骤的 mutation 返回值就是 AuditResult。

**方案**：在 ChapterPipeline 中缓存最近一次 audit mutation 的返回值，传给 AuditResultPanel 展示。

```typescript
interface AuditResultPanelProps {
  result?: AuditResult | null;
}
```

展示内容：
- 总体结果：passed → 绿色 "通过" / failed → 红色 "未通过"
- 规则列表：每条规则一行
  - ✅ 通过 → zinc 文字
  - ⚠️ Warning → amber 文字
  - 🚫 Blocking → red 文字 + message
- 统计：N passed / M warnings / K blocking

不需要新的 API，复用 audit mutation 的返回值。

### 4. 主题切换

**文件**：`src/components/ui/theme-toggle.tsx`（新增）

#### 设计决策

**不做浅色主题**。理由：
- 目标用户是网文作者，主要在夜间写作
- 浅色主题工作量巨大（所有组件要维护两套颜色），收益低
- 维护成本 vs 使用频率不成比例

**改为**：添加「写作模式」切换——在当前深色主题基础上，增加一个「专注模式」：
- 隐藏侧边栏，只保留内容区
- 增大文字行高和间距
- 背景更暗（纯黑）

```typescript
// 简单的 context + localStorage
interface FocusMode {
  enabled: boolean;
  toggle: () => void;
}
```

在 Header 右侧添加专注模式开关按钮。

### 5. 全局打磨

#### 5a. BookDetailPage loading 状态

当前只有文字 "正在读取书籍..."，改为 Skeleton 组件（和 BookList 一致）。

#### 5b. ChapterPipeline 错误反馈增强

当前 mutation 失败后 toast 显示 error.message。在管线操作按钮下方添加错误详情行：

```
[规划] [起草] [审计] [修订] [批准] [导出]
❌ 审计失败: 规则 golden_three_hook 未通过（修订模式: spot_fix）
```

只在有错误时显示，3 秒后自动消失。

#### 5c. 侧边栏导航高亮修复

当前 Sidebar 的 `NavLink` 用 `isActive` 判断高亮。确认：
- `/books` 高亮「我的小说」
- `/books/{id}` 也高亮「我的小说」（`end` prop 控制）

#### 5d. 响应式补充

- BookDetailPage 的 Tabs 在移动端（< 640px）改为水平滚动
- ChapterPipeline 步骤按钮在移动端改为 3×2 grid

### 6. 项目结构变化

```
storyforge3/web/src/
├── api/
│   └── health.ts                    # 新增
├── hooks/
│   ├── useHealth.ts                 # 新增
│   └── useFocusMode.ts             # 新增（专注模式 context）
├── components/
│   ├── ui/
│   │   └── theme-toggle.tsx        # 新增（专注模式切换按钮）
│   └── chapters/
│       └── AuditResultPanel.tsx     # 新增
└── pages/
    └── DashboardPage.tsx            # 重写增强
```

---

## UI 设计要求

延续 amber + zinc 深色主题：

- **Dashboard 布局**：上半区大卡片（欢迎/快速操作），下半区双列（Provider 状态 + 最近活动）
- **Provider 卡片**：紧凑行，左侧绿点/灰点，右侧 model_id
- **审计面板**：紧凑规则列表，每条一行，icon + message
- **专注模式**：过渡动画 300ms ease-out，侧边栏 slide-out
- **所有新增组件**：与 5A-1/5A-2 风格一致，使用同一套 Card/Badge/Button

---

## 技术约束

1. **不做浅色主题**：只做专注模式（深色基础上隐藏侧边栏）
2. **组件 ≤300 行**
3. **TypeScript strict**
4. **不引入新依赖**：专注模式用 React Context + CSS transition
5. **中文 UI**
6. **审计面板**：纯展示组件，数据从父组件传入

---

## 验收

```powershell
cd storyforge3/web
pnpm typecheck     # TypeScript 编译无错误
pnpm build         # 生产构建无错误
pnpm test          # 所有前端测试通过
```

功能验收：
1. Dashboard 展示 Provider 状态 + 最近活动
2. 章节审计后面板展示规则列表
3. 专注模式开关可用（隐藏侧边栏）
4. BookDetail loading 使用 Skeleton
5. 侧边栏导航高亮正确
6. 移动端 Tabs 水平滚动、Pipeline 步骤自适应
7. 无 console 错误

后端验收：
```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 301 测试不退步
```

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5A-3（Dashboard + Polish）：
- Dashboard 增强（Provider + 活动流）：[完成状态]
- 审计结果面板：[完成状态]
- 专注模式：[完成状态]
- 全局打磨（loading/error/导航/响应式）：[完成状态]
- pnpm build：[通过/失败]
- TypeScript 编译：[通过/失败]
- 新增文件数：N
- 前端测试数：M
- 后端测试：301 passed [是/否]
```

---

## 参考文件

读取以下文件：

1. `storyforge3/web/src/pages/DashboardPage.tsx` — 已有 Dashboard
2. `storyforge3/web/src/components/chapters/ChapterPipeline.tsx` — 审计结果展示位置
3. `storyforge3/web/src/components/layout/Sidebar.tsx` — 导航高亮
4. `storyforge3/web/src/components/layout/Header.tsx` — 专注模式开关位置
5. `storyforge3/web/src/components/layout/AppLayout.tsx` — 专注模式隐藏侧边栏
6. `storyforge3/src/storyforge3/api/routes/health.py` — Health API
7. `storyforge3/src/storyforge3/api/routes/providers.py` — Provider API
