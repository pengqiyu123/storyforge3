# Codex 指令：Phase 10A-3 — SSE 进度前端 UI

> 发出日期：2026-06-11
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 10A-2 完成（后端流式输出 + SSE 进度事件可用）
> 战略来源：`docs/research/project-strategy.md` Phase A-2

## 任务概述

### 当前状态

- 前端已有 `usePipelineEvents` hook（`web/src/hooks/usePipelineEvents.ts`），监听 SSE 事件
- `ChapterPipeline` 组件（`web/src/components/chapters/ChapterPipeline.tsx`）使用 SSE 事件更新 `lastEvent` 状态（第 69-71 行），但只显示为纯文字
- 前端 `PipelineEvent` 类型只识别 3 种事件：`pipeline:start` / `pipeline:complete` / `pipeline:error`（第 7-14 行）
- Phase 10A-2 后端新增了 `llm:chunk` 和 `llm:progress` 两种事件类型
- 长操作期间用户只看到禁用的按钮，无进度信息

### 本阶段交付

**让用户在长操作期间看到实时进度。** 三个核心改动：

1. **扩展 SSE 事件类型**：前端 `PipelineEvent` 类型匹配后端新增的事件
2. **进度条组件**：显示"正在生成第 K/N 段"或"正在生成... 已输出 N 字"
3. **错误状态改进**：超时、重试、provider 错误的详细信息展示

## 核心决策

### 为什么不做逐 token 实时文本流

后端 `generate_text_stream()` 已实现逐 token yield，但将每个 token 实时推送到前端需要高频 SSE 事件（每秒 10-50 次），对 React 渲染造成压力。Phase A-3 先做段落级进度（`llm:progress`，每次生成一段才更新一次），用户体验已大幅提升。逐 token 流式作为后续增强。

### 进度条用确定进度还是不确定进度

- `ChunkedGenerator` 生成时有明确的段落数（completed/total），使用**确定进度条**
- 非 ChunkedGenerator 的单次 LLM 调用（如 plan、revise）无进度信息，使用**不确定进度条**（脉冲动画）
- 两种模式在同一个组件中切换

## Part 1：扩展 SSE 事件类型

### 1.1 更新 `PipelineEvent` 类型

修改 `web/src/hooks/usePipelineEvents.ts`：

```typescript
export interface PipelineEvent {
  type:
    | "pipeline:start"
    | "pipeline:progress"
    | "pipeline:complete"
    | "pipeline:error"
    | "audit:complete"
    | "llm:chunk"       // 新增
    | "llm:progress";   // 新增
  book_id: string;
  chapter_no: number;
  stage?: string;
  message?: string;
  detail?: Record<string, unknown> | null;
}
```

### 1.2 更新事件处理逻辑

在 `usePipelineEvents` hook 中，对新增事件类型做静默处理（不弹 toast），因为 `llm:progress` 会高频触发：

```typescript
source.onmessage = (message) => {
  const event = JSON.parse(message.data) as PipelineEvent;
  onEvent?.(event);
  queryClient.invalidateQueries({ queryKey: chapterStatusKey(bookId, chapterNo) });

  // 只对终态事件弹 toast，进度事件不弹
  if (event.type === "pipeline:error") {
    toast.error(event.message || "管线运行失败");
  } else if (event.type === "pipeline:complete") {
    toast.success(event.message || `${event.stage ?? "管线"}完成`);
  } else if (event.type === "pipeline:start") {
    toast.info(event.message || `${event.stage ?? "管线"}已启动`);
  }
  // llm:chunk, llm:progress, pipeline:progress, audit:complete → 不弹 toast
};
```

## Part 2：进度条组件

### 2.1 新建 `PipelineProgress` 组件

在 `web/src/components/chapters/PipelineProgress.tsx` 中创建：

```typescript
interface PipelineProgressProps {
  /** 当前阶段名称（如 "起草"、"修订"） */
  stage: string;
  /** 进度信息，来自 SSE 事件 */
  progress?: {
    completed: number;
    total: number;
  } | null;
  /** 是否正在运行 */
  active: boolean;
  /** 错误信息 */
  error?: string | null;
}
```

**UI 设计**：

1. **确定进度模式**（有 `progress` 数据）：
   ```
   ┌──────────────────────────────────────────────────────┐
   │ 正在起草...                                          │
   │ ████████████░░░░░░░░░░░░░░░░  3/5 段                 │
   │ 正在生成第 3/5 段                                     │
   └──────────────────────────────────────────────────────┘
   ```

2. **不确定进度模式**（无 `progress` 数据）：
   ```
   ┌──────────────────────────────────────────────────────┐
   │ 正在规划...                                          │
   │ ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░  (脉冲动画)              │
   └──────────────────────────────────────────────────────┘
   ```

3. **错误模式**：
   ```
   ┌──────────────────────────────────────────────────────┐
   │ ❌ 起草失败                                          │
   │ Provider 请求超时（300s），已重试 3 次                 │
   └──────────────────────────────────────────────────────┘
   ```

**样式要求**：
- 使用 Tailwind + shadcn/ui 的 Card 或原生 div
- 进度条用 `bg-zinc-800` 背景 + `bg-blue-500` 填充
- 确定模式：宽度百分比 = `completed / total * 100%`
- 不确定模式：使用 CSS 动画（`animate-pulse` 或自定义 shimmer）
- 颜色与现有暗色主题一致（`border-zinc-800/80 bg-zinc-950/80`）

### 2.2 在 ChapterPipeline 中集成

修改 `web/src/components/chapters/ChapterPipeline.tsx`：

1. 新增状态跟踪：

```typescript
const [pipelineStage, setPipelineStage] = useState<string | null>(null);
const [chunkProgress, setChunkProgress] = useState<{ completed: number; total: number } | null>(null);
```

2. 在 `usePipelineEvents` 回调中更新进度状态：

```typescript
usePipelineEvents(bookId, chapterNo, (event) => {
  setLastEvent(event.message || event.stage || "");

  if (event.type === "pipeline:start") {
    setPipelineStage(event.stage || null);
    setChunkProgress(null);
  } else if (event.type === "llm:progress" && event.detail) {
    setChunkProgress({
      completed: Number(event.detail.completed) || 0,
      total: Number(event.detail.total) || 0,
    });
  } else if (event.type === "pipeline:complete" || event.type === "pipeline:error") {
    setPipelineStage(null);
    setChunkProgress(null);
  }
});
```

3. 在管线按钮区域下方渲染 `PipelineProgress`：

```typescript
{isBusy && pipelineStage ? (
  <PipelineProgress
    stage={pipelineStage}
    progress={chunkProgress}
    active={isBusy}
    error={lastError || null}
  />
) : null}
```

4. 替换现有的 `lastEvent` 文字显示（第 260 行 `{lastEvent ? <span>...` ）为新的进度组件

## Part 3：错误状态改进

### 3.1 展示 provider 错误详情

当 `pipeline:error` 事件包含 `detail` 时，在错误面板中展示结构化信息：

```typescript
// 在 PipelineProgress 的错误模式中
if (error && event.detail) {
  // 展示：
  // - 错误类型（超时 / 连接失败 / 限流 / 格式错误）
  // - 重试次数
  // - 已耗时
}
```

### 3.2 Toast 错误信息分级

在 `usePipelineEvents` 中，对 `pipeline:error` 事件做分级展示：
- 超时错误：`"章节起草超时，请检查网络连接"`
- 限流错误：`"Provider 限流，请稍后重试"`
- 其他错误：直接展示 `event.message`

## Part 4：测试要求

### 4.1 单元测试

新增 `web/src/components/chapters/PipelineProgress.test.tsx`：

```typescript
// 1. test_renders_determinate_progress
//    传入 progress={{ completed: 3, total: 5 }}，验证进度条宽度和文字

// 2. test_renders_indeterminate_progress
//    不传 progress，验证脉冲动画类名

// 3. test_renders_error_state
//    传入 error="超时"，验证错误信息展示

// 4. test_disappears_when_not_active
//    active=false，验证不渲染
```

更新 `web/src/hooks/usePipelineEvents.test.tsx`：

```typescript
// 5. test_handles_llm_progress_event
//    模拟 llm:progress 事件，验证不弹 toast 但触发 onEvent 回调

// 6. test_handles_llm_chunk_event
//    模拟 llm:chunk 事件，验证不弹 toast 但触发 onEvent 回调

// 7. test_no_toast_for_progress_events
//    验证 llm:progress 事件不触发 toast（高频事件不应弹通知）
```

更新 `web/src/components/chapters/ChapterPipeline.test.tsx`：

```typescript
// 8. test_shows_pipeline_progress_when_busy
//    模拟 isBusy + pipelineStage，验证 PipelineProgress 渲染

// 9. test_updates_chunk_progress_from_sse
//    模拟 SSE llm:progress 事件，验证进度更新
```

### 4.2 测试工具

为 SSE 事件模拟提供工具函数（如尚不存在）：

```typescript
function createMockSSEEvent(
  type: string,
  overrides?: Partial<PipelineEvent>
): MessageEvent {
  return new MessageEvent("message", {
    data: JSON.stringify({
      type,
      book_id: "test-book",
      chapter_no: 1,
      ...overrides,
    }),
  });
}
```

## Part 5：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 | 新写比例 |
|---------|---------|---------|---------|
| SSE hook 事件处理 | `web/src/hooks/usePipelineEvents.ts` 已有逻辑 | 骨架移植：扩展现有类型和处理 | 30% |
| 进度条样式 | shadcn/ui Progress 组件（如果已安装）或 Tailwind 原生 | 模式复用：标准进度条 UI 模式 | 40% |
| 错误展示 | `ChapterPipeline.tsx` 第 262 行已有 `lastError` 面板 | 骨架移植：扩展现有错误面板 | 30% |
| 暗色主题样式 | `ChapterPipeline.tsx` 已有的 `border-zinc-800/80 bg-zinc-950/80` | 直接移植：复用现有配色 | ≤20% |

### 无直接来源说明

- `PipelineProgress` 组件：新组件，无现成来源。风险缓解：组件逻辑简单（条件渲染 + CSS 进度条），测试覆盖 4 个状态。
- 新写比例约 40%。

## 验收标准

### 功能检查

- [ ] `PipelineEvent` 类型包含 `llm:chunk` 和 `llm:progress`
- [ ] `PipelineProgress` 组件存在，支持确定/不确定/错误三种模式
- [ ] `ChapterPipeline` 在长操作期间显示 `PipelineProgress`
- [ ] `llm:progress` 事件更新进度条的 completed/total 数字
- [ ] `pipeline:start` 事件重置进度状态
- [ ] `pipeline:complete` / `pipeline:error` 事件清除进度状态
- [ ] `llm:progress` 和 `llm:chunk` 事件不弹 toast

### 向后兼容

- [ ] `pipeline:start` / `pipeline:complete` / `pipeline:error` 事件的 toast 行为不变
- [ ] 现有 62 前端测试全部通过
- [ ] `pnpm build` 通过（仅允许已知 CodeMirror chunk 警告）

### 测试覆盖

- [ ] ≥6 个新测试（PipelineProgress 4 + usePipelineEvents 3 + ChapterPipeline 2）
- [ ] 每个 `PipelineProgress` 模式有对应测试
- [ ] SSE 新事件的 toast 抑制有测试

### 质量门禁

- [ ] `pnpm test` 全绿（基线 62 + 新增 ≥6 = ≥68）
- [ ] `pnpm build` 通过
- [ ] 无新 `console.log` 残留
- [ ] 无新 `TODO` / `FIXME` 残留

### 文档更新

- [ ] `CLAUDE.md` 更新：Phase 10A-3 完成记录 + 前端进度 UI 说明

## 估算工作量

| 文件 | 估算行数 | 说明 |
|------|---------|------|
| `web/src/hooks/usePipelineEvents.ts` | ~15 行修改 | 类型扩展 + 事件处理更新 |
| `web/src/components/chapters/PipelineProgress.tsx` | ~80 行 | 新建 |
| `web/src/components/chapters/ChapterPipeline.tsx` | ~25 行修改 | 集成进度组件 |
| `web/src/components/chapters/PipelineProgress.test.tsx` | ~60 行 | 新建 |
| `web/src/hooks/usePipelineEvents.test.tsx` | ~30 行追加 | 新事件测试 |
| `web/src/components/chapters/ChapterPipeline.test.tsx` | ~25 行追加 | 进度集成测试 |
| **合计** | **~235 行** | 前端为主 |

## 不做的事（Out of Scope）

- ❌ 不做逐 token 实时文本流渲染（`llm:chunk` 事件类型定义了但本章不消费）
- ❌ 不修改后端代码（Phase 10A-2 已完成）
- ❌ 不修改编辑器组件（ChapterEditor 不变）
- ❌ 不修改 MCP Server
- ❌ 不添加 shadcn/ui Progress 组件（如未安装，用原生 div + Tailwind 实现）
- ❌ 不做 WebSocket 替代 SSE（SSE 已满足单向推送需求）
