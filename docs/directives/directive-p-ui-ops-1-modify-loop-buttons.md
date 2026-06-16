# P-UI-OPS-1：前端暴露修改闭环操作按钮

> 指令编号：P-UI-OPS-1
> 下发时间：2026-06-16
> 下发人：ZCode（PM）
> 执行人：Trae
> 优先级：P0

---

## 1. 问题陈述

后端已实现修改闭环（P-LIFECYCLE-1）：re-plan、re-audit、unexport。但前端 ChapterPipeline 是纯只读 viewer，用户无法通过 UI 触发这些操作。

当前用户手动编辑正文后想重新审计，需要找 agent 调 API。取消导出更是完全不可操作。

**这不是"给生产管线加 UI 按钮"**——生产（plan→draft→audit→export）仍然由 agent 驱动。**这是给"修改后的重新验证"和"导出回退"加 UI 入口**。编辑正文已经有 UI 按钮，重新审计和取消导出应该也有。

## 2. 目标

在 ChapterPipeline 中添加三个操作按钮，让用户能直接在 UI 上触发修改闭环：

1. **重新审计**（re-audit）：用户手动编辑正文保存后，出现"重新审计"按钮
2. **取消导出**（unexport）：章节状态为 `exported` 时，出现"取消导出"按钮
3. **重新规划**（re-plan）：章节状态为 `planned`/`drafted`/`needs_review`/`needs_revision`/`revised` 时，出现"重新规划"按钮

## 3. UI 设计

### 3.1 按钮位置

**不要在 stage tabs 区域加**——那些是查看 tab，不应该变成操作触发器。

按钮放在 **CardHeader 的操作栏**（和状态 badge 同一行）：

```
┌─────────────────────────────────────────────────────┐
│ 第 4 章                    [已导出] 5895字          │
│                              [取消导出] [重新审计]   │
├─────────────────────────────────────────────────────┤
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

### 3.2 按钮出现条件

| 按钮 | 出现条件 | label |
|------|----------|-------|
| **重新审计** | `needs_review`（用户刚编辑保存后） | "重新审计" |
| **取消导出** | `exported` | "取消导出" |
| **重新规划** | `planned` / `drafted` / `needs_review` / `needs_revision` / `revised` | "重新规划" |

### 3.3 交互流程

**重新审计**：
1. 用户点击"重新审计"→ 调用 `POST /api/books/{book_id}/chapters/{chapter_no}/re-audit`
2. 按钮变为 loading 状态（"审计中..."）
3. 成功 → 刷新章节状态，显示审计结果
4. 失败 → 显示错误信息（复用现有 `lastError` 机制）

**取消导出**：
1. 用户点击"取消导出"→ 调用 `POST /api/books/{book_id}/chapters/{chapter_no}/unexport`
2. 成功 → 状态回退到 `approved`，按钮消失，状态 badge 更新
3. 无需确认弹窗（不删数据，随时可以重新 export）

**重新规划**：
1. 用户点击"重新规划"→ 调用 `POST /api/books/{book_id}/chapters/{chapter_no}/re-plan`
2. 按钮变为 loading 状态（"规划中..."）
3. 成功 → plan 数据刷新（`useChapterPlanState` 重新获取）
4. 失败 → 显示错误信息

### 3.4 样式

- 使用现有 `Button` 组件，`variant="outline"`，`size="sm"`
- 操作按钮用 `variant="secondary"`（蓝色调），与查看 tab 区分
- 重新审计按钮旁边可以加一个小提示："编辑正文后可重新审计"

## 4. 改动范围

| 文件 | 改动 |
|------|------|
| `web/src/hooks/useChapters.ts` | 新增 `useRePlan`、`useReAudit`、`useUnexport` hooks |
| `web/src/api/chapters.ts` | 新增 `rePlan`、`reAudit`、`unexport` API 函数 |
| `web/src/components/chapters/ChapterPipeline.tsx` | 在 CardHeader 中添加操作按钮 |

### 4.1 API 层

```typescript
// chapters.ts
export async function rePlan(bookId: string, chapterNo: number): Promise<ChapterIntent> {
  const { data } = await apiClient.post(`/books/${bookId}/chapters/${chapterNo}/re-plan`);
  return data.data;
}

export async function reAudit(bookId: string, chapterNo: number): Promise<AuditResult> {
  const { data } = await apiClient.post(`/books/${bookId}/chapters/${chapterNo}/re-audit`);
  return data.data;
}

export async function unexport(bookId: string, chapterNo: number): Promise<ChapterResult> {
  const { data } = await apiClient.post(`/books/${bookId}/chapters/${chapterNo}/unexport`);
  return data.data;
}
```

### 4.2 Hooks 层

```typescript
// useChapters.ts
export function useRePlan(bookId: string, chapterNo: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rePlan(bookId, chapterNo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chapterKey(bookId, chapterNo) });
      queryClient.invalidateQueries({ queryKey: planKey(bookId, chapterNo) });
    },
  });
}

export function useReAudit(bookId: string, chapterNo: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => reAudit(bookId, chapterNo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chapterKey(bookId, chapterNo) });
    },
  });
}

export function useUnexport(bookId: string, chapterNo: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unexport(bookId, chapterNo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chapterKey(bookId, chapterNo) });
    },
  });
}
```

### 4.3 ChapterPipeline 改动

在 CardHeader 的右侧操作区，根据状态渲染按钮：

```tsx
{/* 操作按钮 */}
{status === "exported" ? (
  <Button variant="secondary" size="sm" onClick={handleUnexport} disabled={unexportOp.isPending}>
    {unexportOp.isPending ? "取消中..." : "取消导出"}
  </Button>
) : null}

{["planned", "drafted", "needs_review", "needs_revision", "revised"].includes(status) ? (
  <Button variant="secondary" size="sm" onClick={handleRePlan} disabled={rePlanOp.isPending}>
    {rePlanOp.isPending ? "规划中..." : "重新规划"}
  </Button>
) : null}

{["needs_review", "drafted", "audited", "approved", "truth_committed", "exported"].includes(status) ? (
  <Button variant="secondary" size="sm" onClick={handleReAudit} disabled={reAuditOp.isPending}>
    {reAuditOp.isPending ? "审计中..." : "重新审计"}
  </Button>
) : null}
```

## 5. 验收标准

- [ ] `exported` 状态章节显示"取消导出"按钮
- [ ] 点击"取消导出"→ API 调用成功 → 状态变为 `approved` → 按钮消失
- [ ] `needs_review` 状态显示"重新审计"和"重新规划"按钮
- [ ] 点击"重新审计"→ API 调用成功 → 状态变为 `audited`（如果通过）或 `needs_revision`（如果不通过）
- [ ] 点击"重新规划"→ API 调用成功 → plan 数据刷新
- [ ] 按钮在 loading 时禁用，显示"审计中..."/"规划中..."/"取消中..."
- [ ] API 调用失败时显示错误信息
- [ ] 前端测试全量通过（≥112 passed）
- [ ] 前端 typecheck 通过
- [ ] 前端 build 通过
- [ ] 不影响现有的编辑正文 / 保存功能

## 6. 不在本指令范围

- ❌ 不加生产管线按钮（plan/draft/audit/revise/approve/export 仍由 agent 驱动）
- ❌ 不改后端 API
- ❌ 不加确认弹窗（unexport 不删数据，无需确认）
- ❌ 不修改 stage tabs 区域

## 7. 风险

- 极低风险：只在前端加按钮调用已有 API，不改任何后端逻辑
- 需注意 mutation 的 `onSuccess` 正确 invalidate 相关 query，确保 UI 状态刷新
