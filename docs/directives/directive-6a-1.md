# Codex 指令：Phase 6A-1 — CodeMirror 编辑器

> 发出日期：2026-06-09
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5 完成（334 后端 tests, 14 前端 tests, ruff clean）

---

## 任务概述

将章节文本预览从 textarea 替换为 CodeMirror 6 编辑器。**代码直接移植 CC-Switch 的 `MarkdownEditor.tsx`**，不做从零编写。

**目标**：章节预览区具备行号、自动换行、暗色主题、只读/可编辑模式切换、中文字符计数。

---

## 核心约束：代码借鉴

**本指令的代码 95% 来自 CC-Switch `MarkdownEditor.tsx`（159 行，生产级）。**

源文件路径：`d:\python\Novel\cc-switch-main\src\components\MarkdownEditor.tsx`

你需要：
1. **读取** CC-Switch 源文件，理解其实现
2. **移植** 到 StoryForge3 前端，做最小改动
3. **不要从零编写** 编辑器逻辑

---

## 修改目标

### 1. 安装 CodeMirror 6 依赖

**文件**：`storyforge3/web/package.json`

参照 CC-Switch `d:\python\Novel\cc-switch-main\package.json` 的版本号，新增：

```json
{
  "codemirror": "^6.0.2",
  "@codemirror/lang-markdown": "^6.5.0",
  "@codemirror/theme-one-dark": "^6.1.3",
  "@codemirror/state": "^6.5.2",
  "@codemirror/view": "^6.38.2"
}
```

CC-Switch 用了 `basicSetup`（从 `codemirror` 导入），这个包也需要安装。如果 `codemirror` 已包含 `basicSetup` 则无需额外包。

安装命令：
```powershell
cd storyforge3/web
pnpm add codemirror @codemirror/lang-markdown @codemirror/theme-one-dark @codemirror/state @codemirror/view
```

### 2. 移植 ChapterEditor 组件

**文件**：`storyforge3/web/src/components/editor/ChapterEditor.tsx`（新建）

从 CC-Switch `MarkdownEditor.tsx` 移植，做以下调整：

**必须修改的点**：

| # | CC-Switch 原版 | StoryForge3 调整 |
|---|---------------|-----------------|
| 1 | `React.FC<MarkdownEditorProps>` | 普通函数签名 `function ChapterEditor({...}: ChapterEditorProps)` |
| 2 | `export default MarkdownEditor` | 具名导出 `export function ChapterEditor` |
| 3 | 字体 `ui-monospace, ...` | 改为中文友好字体 `"Microsoft YaHei", "PingFang SC", sans-serif` |
| 4 | border class `border-gray-800/200` | 改为 `border-zinc-800`（匹配 SF3 暗色主题） |
| 5 | `darkMode` prop 默认 `false` | 默认改为 `true`（SF3 全暗色） |
| 6 | 浅色模式分支 | 可以保留，但 SF3 当前不使用浅色模式 |

**Props 接口**：

```typescript
interface ChapterEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
}
```

**保留不变的**：
- `useRef` + `useEffect` 创建/销毁 EditorView 的模式
- `EditorState.create({ doc: value, extensions })` 初始化
- 外部 value 同步的第二个 `useEffect`
- `EditorView.lineWrapping` 自动换行
- `EditorView.updateListener` 监听文档变化
- 只读模式隐藏光标 + 高亮行的 theme

**新增**：
- 中文字符计数显示。在编辑器右下角叠加一个小计数器。

```typescript
function countChineseChars(text: string): number {
  const matches = text.match(/[一-鿿㐀-䶿]/g);
  return matches ? matches.length : 0;
}
```

### 3. 替换 ChapterPipeline 中的 textarea

**文件**：`storyforge3/web/src/components/chapters/ChapterPipeline.tsx`

将第 117-130 行的 textarea 替换为 ChapterEditor：

**当前代码（删除）**：
```tsx
<label className="grid gap-2">
  <span className="text-sm font-medium text-zinc-300">文本预览</span>
  <textarea
    aria-label="章节文本预览"
    readOnly
    value={result?.text ?? ""}
    className={cn(
      "h-52 resize-none rounded-md border border-zinc-800 bg-black/30 p-3 text-sm leading-6 text-zinc-300 outline-none",
      !result?.text && "text-zinc-600"
    )}
    placeholder="章节正文会在管线运行后显示。"
  />
</label>
```

**替换为**：
```tsx
<div className="space-y-2">
  <div className="flex items-center justify-between">
    <span className="text-sm font-medium text-zinc-300">文本预览</span>
    <span className="text-xs text-zinc-500">{countChineseChars(result?.text ?? "")} 字</span>
  </div>
  <ChapterEditor
    value={result?.text ?? ""}
    readOnly
    placeholder="章节正文会在管线运行后显示。"
    className="h-52"
  />
</div>
```

需要在文件顶部添加 import：
```typescript
import { ChapterEditor } from "@/components/editor/ChapterEditor";
```

以及 `countChineseChars` 辅助函数（可以放在 `ChapterPipeline.tsx` 内或提取到 `lib/utils.ts`）。

### 4. 测试

**文件**：`storyforge3/web/src/components/editor/ChapterEditor.test.tsx`（新建）

测试用例：

1. **`renders with value`**：传入文本，验证编辑器 DOM 挂载成功
2. **`renders in readOnly mode`**：readOnly=true，验证 `.cm-cursor` 隐藏
3. **`calls onChange when editing`**：readOnly=false，模拟输入，验证 onChange 回调
4. **`syncs external value`**：外部 value 变更后，编辑器内容更新
5. **`displays chinese char count`**：传入中文文本，验证字符计数正确

测试环境使用 vitest + jsdom（项目已配置）。CodeMirror 6 在 jsdom 中需要 mock `EditorView`，如果测试环境不支持完整 DOM 测量，可以用简单的渲染 + props 传递测试。

### 5. 路线图更新

**文件**：`storyforge3/docs/roadmap-phase5.md`

在文件末尾追加 Phase 6 路线图头部（阶段总览）：

```markdown
## Phase 6：从开发者工具到创作平台

### 阶段总览

| 子阶段 | 功能 | 借鉴来源 | 估算工期 |
|--------|------|----------|----------|
| 6A-1 | CodeMirror 编辑器 | CC-Switch MarkdownEditor (95%) | ~3 天 |
| 6D | Tauri 桌面端 | CC-Switch lib.rs 骨架 (40%) | ~8 天 |
| 6E | MCP Server | Letta MCP 客户端 (50%) | ~8 天 |
| 6C | 同人模式 | InkOS FanficCanonImporter (30%) | ~6 天 |
| 6B | 短篇管线 | 无现成代码 (10%) | ~10 天 |
```

---

## 技术约束

1. **直接移植，不从零写**：编辑器逻辑来自 CC-Switch，只做适配
2. **不改后端**：334 测试不退步，`ruff check .` clean
3. **保持暗色主题**：SF3 全暗色，不需要浅色模式
4. **中文字体优先**：编辑器字体栈以中文为主
5. **TypeScript strict**：与项目配置一致
6. **组件 ≤300 行**：超出则拆分
7. **中文 UI**：界面语言为中文

---

## 验收

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 334 tests 不退步
ruff check .                                       # clean
cd web
pnpm install                                       # 新依赖安装成功
pnpm build                                         # tsc + vite build 零错误
pnpm test                                          # 前端测试全绿
```

功能验收：
1. 管线运行后章节预览显示 CodeMirror 编辑器（非 textarea）
2. 编辑器有行号、自动换行、暗色主题
3. 只读模式下无光标、无高亮行
4. 右下角显示中文字符计数
5. CC-Switch MarkdownEditor 的核心逻辑完整保留
6. 全部 334 后端测试 + 前端测试通过
7. ruff check clean + pnpm build 零错误

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 6A-1（CodeMirror 编辑器）：
- CodeMirror 依赖安装：[完成状态 + 版本号]
- ChapterEditor 组件：[完成状态 + 借鉴来源说明]
- ChapterPipeline textarea 替换：[完成状态]
- 中文字符计数：[完成状态]
- 前端测试：[数量] passed
- 后端测试：[数量] passed
- pnpm build：[状态]
- ruff check：[状态]
- 改动文件列表：[...]
```

---

## 参考文件

### 必须读取（借鉴来源）

1. **`d:\python\Novel\cc-switch-main\src\components\MarkdownEditor.tsx`** — 直接移植源（159 行）
2. **`d:\python\Novel\cc-switch-main\package.json`** — CodeMirror 依赖版本号

### 需要修改

3. `storyforge3/web/src/components/chapters/ChapterPipeline.tsx` — 替换 textarea
4. `storyforge3/web/package.json` — 新增依赖

### 新建

5. `storyforge3/web/src/components/editor/ChapterEditor.tsx` — 从 CC-Switch 移植
6. `storyforge3/web/src/components/editor/ChapterEditor.test.tsx` — 测试

### 更新

7. `storyforge3/docs/roadmap-phase5.md` — Phase 6 路线图头部
