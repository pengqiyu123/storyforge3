# P-UI-FIX-1：前端可见性修复

> PM 指令 | 2026-06-16
> 优先级：P0（阻塞生产结果查看）
> 预计工时：1-2 天
> 前置：无
> 调研依据：`docs/research/frontend-stage-display-and-docs-gap-report.md`

---

## 问题陈述

当前前端所有已导出章节（ch1-ch3）在展开详情后，起草 tab 显示"尚未起草"，审计/修订/批准 tab 显示占位符。已生产的 3 章内容无法在前端查看。

根因：`ChapterCard.tsx` 使用 reconcile 摘要数据构建 `fallbackResult()`，硬编码 `text: ""`，不调用返回真实正文的 `GET /status` API。同时，已实现的 `AuditResultPanel` 和 `RevisionDiffPanel` 组件未挂载。

## 目标

1. 所有已生产章节的正文可在前端正常显示和编辑
2. 审计结果面板（AuditResultPanel）在审计 tab 中展示
3. 修订 diff 面板（RevisionDiffPanel）在修订 tab 中展示
4. 批准 tab 显示批准状态记录（轻量）

## 改动范围

### Step 1：ChapterCard 接入真实数据（核心修复）

**文件**：`web/src/components/chapters/ChapterCard.tsx`

**改动**：
- 在 `ChapterCard` 组件内调用 `useChapterStatus(bookId, chapterNo)`（来自 `hooks/useChapters.ts:13`）
- 将 `fallbackResult` 替换为真实 `ChapterResult`（fallback 保留作为加载中/错误时的降级）
- `ChapterCardProps` 需要新增 `bookId` prop（当前已有）

**伪代码**：
```typescript
import { useChapterStatus } from "@/hooks/useChapters";

export function ChapterCard({ bookId, chapter }: ChapterCardProps) {
  const [open, setOpen] = useState(false);
  const chapterNo = chapter.chapter_no;
  const statusQuery = useChapterStatus(bookId, chapterNo);
  // 优先使用真实 API 数据，fallback 保留
  const result = statusQuery.data ?? fallbackResult(bookId, chapter);
  // ...其余不变
}
```

**注意事项**：
- `useChapterStatus` 在 `enabled` 条件满足时才会请求，展开 card 后才触发（符合预期）
- 首次展开时 `statusQuery.data` 为 undefined，fallbackResult 提供降级 UI
- `useChapterStatus` 已处理 404（返回 empty result），无需额外处理

### Step 2：挂载 AuditResultPanel 和 RevisionDiffPanel

**文件**：`web/src/components/chapters/ChapterPipeline.tsx`

**改动 A — import**：
```typescript
import { AuditResultPanel } from "@/components/chapters/AuditResultPanel";
import { RevisionDiffPanel } from "@/components/chapters/RevisionDiffPanel";
```

**改动 B — 新增 props 接收 auditResult**：
`ChapterPipelineProps` 新增可选 `auditResult?: AuditResult | null`，从父组件传入。

**改动 C — 替换 PlaceholderView（L258-260）**：

L258（audit tab）：
```tsx
{activeStage === "audit" ? (
  result.audit_result ? (
    <AuditResultPanel result={result.audit_result} />
  ) : (
    <PlaceholderView label="审计结果" status={status} readyAt={["audited", "needs_revision", "revised", "approved", "exported"]} />
  )
) : null}
```

L259（revise tab）：
```tsx
{activeStage === "revise" ? (
  result.revision_diff ? (
    <RevisionDiffPanel diff={result.revision_diff} />
  ) : (
    <PlaceholderView label="修订 diff" status={status} readyAt={["revised", "approved", "exported"]} />
  )
) : null}
```

L260（approve tab）— 替换为轻量批准记录视图：
```tsx
{activeStage === "approve" ? (
  ["approved", "exported"].includes(status) ? (
    <div className="rounded-md border border-zinc-800/80 bg-zinc-950/80 p-4 text-sm text-zinc-300">
      <p className="font-medium text-zinc-100">批准记录</p>
      <p className="mt-1 text-zinc-500">本章已批准。Truth 提取和导出已自动执行。</p>
    </div>
  ) : (
    <PlaceholderView label="批准记录" status={status} readyAt={["approved", "exported"]} />
  )
) : null}
```

### Step 3：后端 GET /status 扩展 audit_result 字段

**文件**：
- `src/storyforge3/services/chapter_service.py`（`get_status()` 方法）
- `src/storyforge3/models.py`（`ChapterResult` dataclass）
- `web/src/api/chapters.ts`（TypeScript 类型）

**改动 A — models.py**：
`ChapterResult` 新增字段：
```python
audit_result: AuditResult | None = None
```

**改动 B — chapter_service.py `get_status()`**：
在状态为 `AUDITED`/`NEEDS_REVISION`/`REVISED`/`APPROVED`/`TRUTH_COMMITTED`/`EXPORTED` 时，加载持久化的 AuditResult：

```python
def get_status(self, book_id: str, chapter_no: int) -> ChapterResult:
    # ...现有逻辑...
    result = ChapterResult(...)
    
    # 加载审计结果
    if status in (ChapterStatus.AUDITED, ChapterStatus.NEEDS_REVISION,
                  ChapterStatus.REVISED, ChapterStatus.APPROVED,
                  ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED):
        result.audit_result = self._load_audit_result(book_id, chapter_no)
    
    return result
```

`_load_audit_result()` 从 `books/{book_id}/chapters/{chapter_no:04d}/audit_result.json` 加载。AuditResult 在 `step_audit()` 阶段已持久化（验证此文件路径是否正确，如不正确则调整为实际路径）。

**改动 C — chapters.ts TypeScript 类型**：
```typescript
export interface ChapterResult {
  // ...现有字段...
  audit_result?: AuditResult | null;
}
```

### Step 4（可选增强）：批准 tab 显示 truth 统计

如果 `GET /status` 已返回 truth 相关信息（`ChapterResult` 的 truth 字段），批准 tab 可显示 truth 条目数。此为锦上添花，不影响主线。

## 验收标准

| # | 验收项 | 验证方法 |
|---|--------|---------|
| V1 | ch1-ch3 展开后，起草 tab 显示真实正文（非"尚未起草"） | 前端手动验证 |
| V2 | 字数统计显示正确数字 | 前端手动验证 |
| V3 | 编辑按钮可点击，编辑器显示真实内容 | 前端手动验证 |
| V4 | 审计 tab 显示 AuditResultPanel（规则列表） | 前端手动验证 |
| V5 | 修订 tab 显示 RevisionDiffPanel（diff 对照） | 前端手动验证 |
| V6 | 批准 tab 显示批准状态记录（非 PlaceholderView） | 前端手动验证 |
| V7 | `GET /status` 返回 `audit_result` 字段 | curl/API 测试 |
| V8 | 后端全量测试通过 | `pytest` |
| V9 | 前端类型检查通过 | `npx tsc --noEmit` |
| V10 | 未展开的章节卡片不受影响（不触发 status 请求） | 前端手动验证 |

## 不在本指令范围

- ~~P1 ChapterPanel 重设计~~（后续迭代）
- ~~异步 Run 模型~~（后续迭代）
- ~~Truth 摘要面板~~（需独立设计）
- ~~导出历史记录~~（需后端扩展）
- ~~A-L 架构优化项~~（全部延期）
- ~~世界构建/角色管理 UI~~（P2 功能）

## 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| `useChapterStatus` 在 card 列表中每个 item 都触发请求 | 性能：N 个章节 = N 个并发 status 请求 | `enabled` 条件控制；React Query 自动去重和缓存 |
| audit_result 文件路径与实际不一致 | audit tab 无法加载 | Codex 需确认 audit 产物持久化路径 |
| ChapterResult 新增字段导致序列化问题 | API 兼容性 | 字段为 Optional，无数据时返回 null，不影响现有逻辑 |
