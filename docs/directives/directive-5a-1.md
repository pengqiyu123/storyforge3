# Codex 指令：Phase 5A-1 — 前端 Scaffold + Book 管理

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 4 完成（301 tests, ruff clean）

---

## 任务概述

从零搭建 StoryForge3 的 React 前端项目，交付第一个可用页面（Book 列表 + 创建）。

**重要**：本任务是前端项目初始化。前端代码放在 `storyforge3/web/` 目录下，与 Python 后端同仓库共存。

---

## 背景

### 后端 API 已就绪

StoryForge3 的 FastAPI 后端提供以下 API（全部可用）：

| 端点 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 创建书籍 | POST | `/api/books` | 创建新书 |
| 书籍列表 | GET | `/api/books` | 返回所有书籍 |
| 书籍详情 | GET | `/api/books/{id}` | 单本书详情 |
| 更新状态 | PATCH | `/api/books/{id}/status` | 更新书籍状态 |
| 健康检查 | GET | `/api/health` | 服务健康状态 |
| Provider 列表 | GET | `/api/providers` | 可用 AI Provider |
| SSE 事件 | GET | `/api/events` | 实时事件流 |

响应信封格式：
```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

错误信封：
```json
{
  "ok": false,
  "data": null,
  "error": { "code": "BOOK_NOT_FOUND", "message": "..." }
}
```

### 技术栈参考

同 workspace 的 `cc-switch-main/` 项目已验证以下技术栈：

- **React 18** + TypeScript
- **Vite 7** 构建工具
- **Tailwind CSS** 样式
- **shadcn/ui** 组件库（基于 Radix UI）
- **TanStack Query** 服务端状态管理
- **Lucide React** 图标
- **Sonner** Toast 通知
- **pnpm** 包管理

**请参考 `cc-switch-main/` 的 package.json 和组件结构作为基准。**

---

## 修改目标

### 1. 创建前端项目

在 `storyforge3/web/` 下初始化 Vite + React + TypeScript 项目：

```bash
cd storyforge3
mkdir web
cd web
pnpm init
# 或使用 Vite 脚手架
pnpm create vite . --template react-ts
```

**package.json 核心依赖**：

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "@tanstack/react-query": "^5.0.0",
    "@radix-ui/react-dialog": "^1.0.0",
    "@radix-ui/react-dropdown-menu": "^2.0.0",
    "@radix-ui/react-tabs": "^1.0.0",
    "@radix-ui/react-slot": "^1.0.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",
    "lucide-react": "^0.400.0",
    "sonner": "^2.0.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vite": "^7.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "autoprefixer": "^10.0.0",
    "postcss": "^8.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "vitest": "^3.0.0",
    "@testing-library/react": "^16.0.0"
  }
}
```

版本号可根据实际最新版调整。

### 2. 项目结构

```
storyforge3/web/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx                      # 入口
│   ├── App.tsx                       # 路由 + 布局
│   ├── globals.css                   # Tailwind 导入 + CSS 变量
│   ├── api/
│   │   ├── client.ts                 # 封装 fetch，处理信封格式
│   │   └── books.ts                  # Book API 函数
│   ├── components/
│   │   ├── ui/                       # shadcn/ui 基础组件
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── input.tsx
│   │   │   ├── label.tsx
│   │   │   ├── select.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── skeleton.tsx
│   │   │   └── toast.tsx (Sonner wrapper)
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx         # 侧边栏 + 顶栏 + 内容区
│   │   │   ├── Sidebar.tsx           # 导航菜单
│   │   │   └── Header.tsx            # 顶栏
│   │   └── books/
│   │       ├── BookCard.tsx          # 书籍卡片
│   │       ├── BookList.tsx          # 书籍列表
│   │       └── CreateBookDialog.tsx  # 创建书籍表单
│   ├── hooks/
│   │   └── useBooks.ts               # TanStack Query hooks
│   ├── pages/
│   │   ├── DashboardPage.tsx         # / — 仪表盘（简单版）
│   │   └── BooksPage.tsx             # /books — 书籍管理
│   └── lib/
│       └── utils.ts                  # cn() 等工具函数
└── public/
    └── favicon.svg
```

### 3. API 客户端

**`src/api/client.ts`**：

```typescript
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const envelope: ApiEnvelope<T> = await res.json();
  if (!envelope.ok) {
    throw new Error(envelope.error?.message || "请求失败");
  }
  return envelope.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};
```

**`src/api/books.ts`**：

```typescript
import { api } from "./client";

export interface Book {
  book_id: string;
  title: string;
  genre: string;
  platform: string;
  status: string;
  target_chapters: number;
  chapter_word_count: number;
  current_chapter: number;
  created_at: string;
  updated_at: string;
}

export interface CreateBookRequest {
  title: string;
  genre: string;
  platform: string;
  target_chapters: number;
  chapter_word_count: number;
}

export const booksApi = {
  list: () => api.get<Book[]>("/api/books"),
  get: (id: string) => api.get<Book>(`/api/books/${id}`),
  create: (data: CreateBookRequest) => api.post<Book>("/api/books", data),
  updateStatus: (id: string, status: string) =>
    api.patch<Book>(`/api/books/${id}/status`, { status }),
};
```

### 4. TanStack Query Hooks

**`src/hooks/useBooks.ts`**：

```typescript
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { booksApi, type CreateBookRequest } from "../api/books";

export function useBooks() {
  return useQuery({
    queryKey: ["books"],
    queryFn: booksApi.list,
  });
}

export function useCreateBook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateBookRequest) => booksApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["books"] }),
  });
}
```

### 5. 页面实现

#### DashboardPage（简单版）

展示书籍数量 + 快速操作入口。不需要图表，简洁即可。

#### BooksPage

- 顶部：标题 "我的小说" + "创建新书" 按钮
- 内容：书籍卡片网格（grid layout）
- 每张卡片：标题、类型、状态徽章、当前章/目标章、字数
- 点击 "创建新书" 弹出 Dialog 表单
- 创建成功后列表自动刷新

### 6. Vite 代理配置

**`vite.config.ts`**：

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

这样开发时前端请求 `/api/*` 自动代理到 FastAPI 后端。

### 7. UI 设计要求

**不要做成模板风格**。参考以下设计方向：

- **编辑/杂志风格**：有层次感的排版，不是千篇一律的卡片网格
- **深色为主**：写作者通常在夜间工作，默认深色主题
- **中文优先**：所有 UI 文案用中文
- **状态色语义化**：incubating=灰色, active=绿色, completed=蓝色, archived=橙色
- **卡片有呼吸感**：不是紧贴的网格，间距拉开

**绝对避免**：
- 默认 Tailwind 蓝紫色方案
- 千篇一律的 hero section
- 无层次的平铺列表
- 纯灰色背景无纹理

---

## 技术约束

1. **TypeScript strict 模式**
2. **shadcn/ui 组件手写**（不使用 CLI 安装，直接写组件代码，参考 cc-switch-main 的组件模式）
3. **组件 ≤300 行**：超出则拆分
4. **不引入 Plate.js 或 CodeMirror**：本阶段只用原生 textarea
5. **不引入状态管理库**（除了 TanStack Query）：UI 状态用 React state
6. **pnpm** 包管理
7. **Vitest** 测试框架（本阶段不强求测试覆盖，但 scaffold 需配置好）

---

## 验收

```powershell
cd storyforge3/web
pnpm install
pnpm dev           # 启动开发服务器
pnpm build         # 生产构建无错误
pnpm typecheck     # TypeScript 编译无错误
```

功能验收：
1. `pnpm dev` 启动后，浏览器打开显示 Dashboard 页面
2. 点击 "我的小说" 进入 Book 列表页
3. 点击 "创建新书"，填写表单，提交成功
4. 列表自动刷新显示新书
5. 深色主题默认开启
6. 无 console 错误

后端验收：
```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 301 测试不退步
```

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5A-1（前端 Scaffold + Book 管理）：
- 项目初始化：[完成状态]
- API 客户端：[完成状态]
- Book 列表页：[完成状态]
- Book 创建表单：[完成状态]
- 深色主题：[完成状态]
- pnpm build：[通过/失败]
- TypeScript 编译：[通过/失败]
- 新增文件数：N
- 后端测试：301 passed [是/否]
```

---

## 参考文件

读取以下文件作为技术参考：

1. `d:\python\Novel\cc-switch-main\package.json` — 依赖版本参考
2. `d:\python\Novel\cc-switch-main\src\components\ui\` — shadcn/ui 组件写法参考
3. `d:\python\Novel\cc-switch-main\vite.config.ts` — Vite 配置参考
4. `d:\python\Novel\storyforge3\src\storyforge3\api\routes\books.py` — 后端 Book API 路由
5. `d:\python\Novel\storyforge3\src\storyforge3\api\errors.py` — 错误信封格式
