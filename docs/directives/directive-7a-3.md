# Codex 指令：Phase 7A-3 — 修订 Diff 展示

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7A-2 完成（453 tests: 406 后端 + 47 前端, ruff clean）

---

## 任务概述

让作者在执行"修订"后，立即看到**这次修订到底改了什么**。当前 `ChapterPipeline` 可以点 revise，但前端看不到 before/after 差异。更关键的是，`ChapterService.revise()` 目前仍是占位实现——只返回原文 + `revision_mode=...` 元信息，没有真正产出修订后的正文。

**当前状态**：
- `ChapterWorkflow.step_revise()` 有真实修订逻辑（patch revise / rework 分流）
- `ChapterService.revise()` 未复用上述逻辑，只返回占位 `ChapterResult`
- `/api/books/{id}/chapters/{no}/revise` 返回的 `ChapterResult` 没有 before/after diff 数据
- `ChapterPipeline` 执行 revise 后只有 toast，无"改了哪里"的可视化
- 无 diff 生成或展示基础设施
- 现有前端无 diff 依赖

**本阶段交付**：

1. 后端：让 `ChapterService.revise()` 执行真实修订，保存修订前快照，返回结构化 diff
2. API：`revise` 响应携带 `revision_diff`
3. 前端：`ChapterPipeline` 修订完成后展示 before/after 差异面板

---

## 核心决策

### 决策 1：修订前快照 `.before.md` + revise 响应内联 diff

**为什么不走单独 `GET /diff` 端点**：

1. before/after 在"执行修订的瞬间"最可靠，跟 revise 响应一起返回最简单
2. 单独 `/diff` 端点需要额外持久化"上一次修订前文本"，增加存储与一致性问题
3. 前端真实需求是"点完修订立刻看变化"

**但仍然保存快照**：修订前把当前正文写入 `{no}.before.md`，这样手动编辑保存后也有回溯能力。快照是 7B 版本回滚的前置基础设施。

**结论**：revise → `ChapterResult` + `revision_diff` 单响应模式，附带 `.before.md` 快照。

### 决策 2：Diff 粒度采用段落块 diff

中文网文修订更适合段落块比较。字符级 diff 噪声大，行级 diff 与中文 prose 段落结构不对齐。

**结论**：
- 后端按段落切分（复用 `split_paragraphs()`）
- 用 `difflib.SequenceMatcher` 比较段落数组
- 只返回发生变化的 block（replace / insert / delete）

### 决策 3：Diff 不持久化到数据库，只展示"最近一次修订"

一旦作者继续编辑、再次修订、重新起草，旧 diff 就清除。历史版本追踪属于 7B 快照/回滚范畴。

---

## Part 1：后端 — 真实修订产物 + 结构化 Diff

### 1.1 修正 `ChapterService.revise()` — 从占位到真实实现

**文件**：`src/storyforge3/services/chapter_service.py`

当前 `revise()` 只做 mode 推荐返回占位结果。**必须复用 `ChapterWorkflow` 的修订逻辑**，不另起一套。

**实现步骤**：

```python
async def revise(self, book_id: str, chapter_no: int, mode: str = "auto") -> ChapterResult:
    # 1. 读取当前正文和审计结果
    text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
    if text is None:
        raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
    audit = self.audit_runner.run_audit(chapter_no, text)

    if audit.passed:
        return ChapterResult(book_id, chapter_no, self._workflow_status(book_id, chapter_no),
                             f"第{chapter_no}章", text, audit=audit,
                             error="audit_passed_no_revision_needed")

    # 2. 保存修订前快照
    before_text = text
    before_path = self.paths.chapter_file(book_id, chapter_no).with_suffix(".before.md")
    self.storage.write_text(before_path, before_text)

    # 3. 构造 workflow 并执行一次修订
    workflow = ChapterWorkflow(self.config, client=self.llm,
                               registry=self.prompt_registry, logger=self.pipeline_logger)
    ctx = await workflow.step_import(book_id)

    # 确定 mode
    failed = self.revision_recommender.failed_results(audit.rule_results)
    if mode == "auto":
        selected_mode = self.revision_recommender.recommend(
            failed, blocking_count=len(audit.blocking_issues), revision_round=0)
    else:
        selected_mode = RevisionMode(mode)

    revised_text = await workflow.step_revise(ctx, chapter_no, before_text, audit, revision_round=0)

    # 4. 写回修订后正文
    self.storage.write_text(self.paths.chapter_file(book_id, chapter_no), revised_text)

    # 5. 状态机推进
    from storyforge3.state.machine import ChapterStateMachine
    ChapterStateMachine(self.paths.chapter_states(book_id)).force_needs_review(
        book_id, chapter_no, reason="revised")

    # 6. 重新审计（用于 UI 参考）
    revised_audit = self.audit_runner.run_audit(chapter_no, revised_text)

    # 7. 构造 diff
    diff = build_revision_diff(before_text, revised_text)

    return ChapterResult(book_id, chapter_no, ChapterStatus.REVISED,
                         f"第{chapter_no}章", revised_text,
                         audit=revised_audit,
                         revision_diff=diff,
                         error=f"revision_mode={selected_mode.value}")
```

**关键约束**：
- 复用 `ChapterWorkflow.step_import()` + `step_revise()`，**不重写 prompt/patch 分流**
- 一次 revise = 一次修订 pass，不做自动多轮（多轮由用户手动再点 revise）
- 修订后状态设为 `REVISED`（通过 `force_needs_review`），不走完整管线

**注意**：`step_import()` 需要 LLM 调用（加载 world/characters/truth）。`step_revise()` 也需要 LLM 调用。这意味着 revise 端点可能耗时较长（与 draft 相当），前端需显示 loading 态（已有 `isBusy` 状态）。

### 1.2 `update_text()` 也保存快照

在 `chapter_service.py:update_text()` 的 `self.storage.write_text(...)` 之前添加：

```python
# 保存修改前快照
before_path = self.paths.chapter_file(book_id, chapter_no).with_suffix(".before.md")
self.storage.write_text(before_path, current.text)
```

确保手动编辑和 LLM 修订都有快照（7B 回滚的基础设施）。

### 1.3 数据模型新增 `RevisionDiff`

**文件**：`src/storyforge3/models.py`

```python
@dataclass(frozen=True)
class RevisionDiffBlock:
    kind: str  # "replace" | "insert" | "delete"
    before_text: str = ""
    after_text: str = ""


@dataclass(frozen=True)
class RevisionDiffSummary:
    changed_blocks: int
    added_blocks: int
    removed_blocks: int
    before_chars: int
    after_chars: int


@dataclass(frozen=True)
class RevisionDiff:
    unit: str  # 固定 "paragraph"
    summary: RevisionDiffSummary
    blocks: tuple[RevisionDiffBlock, ...]
```

在 `ChapterResult` 增加：

```python
revision_diff: RevisionDiff | None = None
```

**约束**：不修改 `ChapterResult.error` 的现有编码方式。

### 1.4 段落 diff 构造器

**新文件**：`src/storyforge3/audit/revision_diff.py`

```python
from __future__ import annotations

import difflib
from storyforge3.audit.chinese_text import count_chinese_chars, split_paragraphs
from storyforge3.models import RevisionDiff, RevisionDiffBlock, RevisionDiffSummary


def build_revision_diff(before_text: str, after_text: str) -> RevisionDiff:
    """比较修订前后文本，返回段落级 diff。"""
    before_paras = split_paragraphs(before_text)
    after_paras = split_paragraphs(after_text)

    matcher = difflib.SequenceMatcher(None, before_paras, after_paras)
    blocks: list[RevisionDiffBlock] = []
    changed = added = removed = 0

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            continue
        elif opcode == "replace":
            blocks.append(RevisionDiffBlock(
                kind="replace",
                before_text="\n\n".join(before_paras[i1:i2]),
                after_text="\n\n".join(after_paras[j1:j2]),
            ))
            changed += 1
        elif opcode == "insert":
            blocks.append(RevisionDiffBlock(
                kind="insert",
                after_text="\n\n".join(after_paras[j1:j2]),
            ))
            added += 1
        elif opcode == "delete":
            blocks.append(RevisionDiffBlock(
                kind="delete",
                before_text="\n\n".join(before_paras[i1:i2]),
            ))
            removed += 1

    return RevisionDiff(
        unit="paragraph",
        summary=RevisionDiffSummary(
            changed_blocks=changed,
            added_blocks=added,
            removed_blocks=removed,
            before_chars=count_chinese_chars(before_text),
            after_chars=count_chinese_chars(after_text),
        ),
        blocks=tuple(blocks),
    )
```

**借鉴**：`split_paragraphs()` 来自 `audit/chinese_text.py`（已有），`count_chinese_chars()` 也已有。`difflib.SequenceMatcher` 是标准库。

### 1.5 API 响应增强

**文件**：`src/storyforge3/api/routes/chapters.py`

新增 Pydantic 模型：

```python
class RevisionDiffBlockResponse(BaseModel):
    kind: str
    before_text: str = ""
    after_text: str = ""


class RevisionDiffSummaryResponse(BaseModel):
    changed_blocks: int
    added_blocks: int
    removed_blocks: int
    before_chars: int
    after_chars: int


class RevisionDiffResponse(BaseModel):
    unit: str
    summary: RevisionDiffSummaryResponse
    blocks: list[RevisionDiffBlockResponse] = Field(default_factory=list)
```

在 `_result_to_response()` 中映射 `result.revision_diff`：

```python
revision_diff = _diff_to_response(result.revision_diff) if result.revision_diff else None
```

**映射函数**：

```python
def _diff_to_response(diff: RevisionDiff) -> RevisionDiffResponse:
    return RevisionDiffResponse(
        unit=diff.unit,
        summary=RevisionDiffSummaryResponse(**asdict(diff.summary)),
        blocks=[RevisionDiffBlockResponse(**asdict(b)) for b in diff.blocks],
    )
```

**范围**：
- `POST /revise` 返回 `revision_diff`
- `GET /status` 可携带 `revision_diff=None`（不持久化 diff 到 status 查询）
- `ChapterStatusResponse` 新增可选字段 `revision_diff: RevisionDiffResponse | None = None`

### 1.6 Protocol 同步

`ChapterServiceProtocol.revise()` 返回类型不变（仍是 `ChapterResult`），因为 `revision_diff` 已嵌入 `ChapterResult`。无需新增方法。

---

## Part 2：前端 — 修订差异面板

### 2.1 API 类型增强

**文件**：`web/src/api/chapters.ts`

```typescript
export interface RevisionDiffBlock {
  kind: "replace" | "insert" | "delete";
  before_text: string;
  after_text: string;
}

export interface RevisionDiffSummary {
  changed_blocks: number;
  added_blocks: number;
  removed_blocks: number;
  before_chars: number;
  after_chars: number;
}

export interface RevisionDiff {
  unit: "paragraph" | string;
  summary: RevisionDiffSummary;
  blocks: RevisionDiffBlock[];
}
```

`ChapterResult` 新增：

```typescript
revision_diff?: RevisionDiff | null;
```

### 2.2 新增 `RevisionDiffPanel` 组件

**新文件**：`web/src/components/chapters/RevisionDiffPanel.tsx`

**布局**：

```
┌─────────────────────────────────────────────┐
│ 修订变更                    [收起 ✕]        │
│ 改动 2 段 · 新增 1 段 · 删除 0 段          │
│ 2450 → 2518 字 (+68)                        │
├──────────────────┬──────────────────────────┤
│    修订前        │      修订后              │
│  (红色背景)      │    (绿色背景)            │
│  "原文段落..."   │    "修改后段落..."       │
├──────────────────┼──────────────────────────┤
│  (灰色占位)      │    (绿色背景)            │
│                  │    "新增段落..."          │
└──────────────────┴──────────────────────────┘
```

**核心渲染逻辑**：

```tsx
interface RevisionDiffPanelProps {
  diff: RevisionDiff;
  onClose?: () => void;
}

export function RevisionDiffPanel({ diff, onClose }: RevisionDiffPanelProps) {
  const { summary, blocks } = diff;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between py-2 px-4">
        <div className="flex items-center gap-3">
          <CardTitle className="text-sm">修订变更</CardTitle>
          {summary && (
            <div className="flex gap-3 text-xs text-muted-foreground">
              {summary.changed_blocks > 0 && <span>改动 {summary.changed_blocks} 段</span>}
              {summary.added_blocks > 0 && <span className="text-green-600">新增 {summary.added_blocks} 段</span>}
              {summary.removed_blocks > 0 && <span className="text-red-600">删除 {summary.removed_blocks} 段</span>}
              <span>{summary.before_chars} → {summary.after_chars} 字</span>
            </div>
          )}
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onClose}>
            <X className="h-3 w-3" />
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-3 pt-0">
        {blocks.length === 0 ? (
          <p className="text-sm text-muted-foreground">无变更</p>
        ) : (
          <div className="space-y-2">
            {blocks.map((block, i) => (
              <DiffBlock key={i} block={block} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

**单个 DiffBlock**：

```tsx
function DiffBlock({ block }: { block: RevisionDiffBlock }) {
  const hasBefore = block.kind === "replace" || block.kind === "delete";
  const hasAfter = block.kind === "replace" || block.kind === "insert";

  return (
    <div className="grid grid-cols-2 gap-2">
      {/* 左列：修订前 */}
      <div className={cn(
        "rounded-md p-2 text-sm border",
        hasBefore
          ? "bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-900"
          : "bg-muted/30 border-muted"
      )}>
        {hasBefore ? (
          <pre className="whitespace-pre-wrap font-sans">{block.before_text}</pre>
        ) : (
          <span className="text-muted-foreground text-xs italic">（无）</span>
        )}
      </div>

      {/* 右列：修订后 */}
      <div className={cn(
        "rounded-md p-2 text-sm border",
        hasAfter
          ? "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-900"
          : "bg-muted/30 border-muted"
      )}>
        {hasAfter ? (
          <pre className="whitespace-pre-wrap font-sans">{block.after_text}</pre>
        ) : (
          <span className="text-muted-foreground text-xs italic">（删除）</span>
        )}
      </div>
    </div>
  );
}
```

**UI 约束**：
- 不做逐字符高亮
- 不引入新依赖
- 使用现有 `Card` / `Button` / Tailwind 样式体系
- `<pre className="whitespace-pre-wrap font-sans">` 保持段落换行
- 深色模式适配（`dark:` 前缀）

### 2.3 ChapterPipeline 串联

**文件**：`web/src/components/chapters/ChapterPipeline.tsx`

新增状态：

```typescript
const [lastRevisionDiff, setLastRevisionDiff] = useState<RevisionDiff | null>(null);
```

在 `runAction()` 中：

```typescript
// 修订成功时设置 diff
if (isChapterResult(value) && value.revision_diff) {
  setLastRevisionDiff(value.revision_diff);
} else if (label !== "修订") {
  // 非 revise 操作清除 diff
  setLastRevisionDiff(null);
}
```

**类型守卫**（在 ChapterPipeline 内或 `api/chapters.ts` 中）：

```typescript
function isChapterResult(value: unknown): value is ChapterResult {
  return typeof value === "object" && value !== null && "book_id" in value && "chapter_no" in value;
}
```

### 2.4 Diff 清除规则

以下场景清除 diff：

1. 执行 `plan` / `draft` / `audit` / `approve` / `export` / `run full pipeline`
2. 点击"编辑"
3. 保存人工修改
4. 放弃人工修改

再次点 revise 时，旧 diff 被新 diff 替换。

### 2.5 挂载位置

顺序：错误提示 → `AuditResultPanel` → **`RevisionDiffPanel`** → 文本预览/编辑器

作者先看"审计为什么修"，再看"修了什么"，最后看正文。

```tsx
{lastRevisionDiff && (
  <RevisionDiffPanel
    diff={lastRevisionDiff}
    onClose={() => setLastRevisionDiff(null)}
  />
)}
```

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| 真实修订执行 | `workflow.py:step_revise()` | 直接复用，不重写 prompt/patch 分流 |
| 段落分割 | `audit/chinese_text.py:split_paragraphs()` | diff 以段落为单位 |
| 原子写入 | `workflow.py:_atomic_write_text()` | 保存 `.before.md` 快照 |
| 中文字符计数 | `audit/chinese_text.py:count_chinese_chars()` | diff summary |
| 面板状态编排 | `ChapterPipeline.tsx` | 沿用 `lastAudit` / `clearAuditFocus()` 模式 |
| UI 视觉风格 | `AuditResultPanel.tsx` | 相同 Card/Badge/深色语义 |

**新写比例**：约 45%。后端 revise 逻辑复用 workflow，diff 构造器新写但极简（~40 行），前端面板复用 UI 体系。

---

## 验收标准

### 后端

- [ ] `ChapterService.revise()` 不再是占位实现，真正执行修订并写回正文
- [ ] 修订前保存 `.before.md` 快照
- [ ] `update_text()` 也在修改前保存 `.before.md` 快照
- [ ] `ChapterResult` 包含 `revision_diff`
- [ ] `build_revision_diff()` 只输出 replace/insert/delete block
- [ ] `POST /revise` 响应包含 `revision_diff`（summary + blocks）
- [ ] `GET /status` 保持兼容（`revision_diff = null`）
- [ ] 现有 406 tests 不退步

### 前端

- [ ] revise 成功后显示 `RevisionDiffPanel`
- [ ] 面板展示改动摘要（段落数 + 字数变化）
- [ ] replace / insert / delete 三类 block 有正确视觉语义（左红右绿）
- [ ] 新操作 / 编辑 / 保存 / 放弃时清除旧 diff
- [ ] 无 diff 时不渲染空壳面板
- [ ] 深色模式正确适配

### 测试

- [ ] 后端：`build_revision_diff()` 单元测试（replace / insert / delete / no-op）
- [ ] 后端：`ChapterService.revise()` 集成测试（确认写回新正文 + 返回 diff + 保存快照）
- [ ] 后端：`POST /revise` API 测试（响应含 diff summary + blocks）
- [ ] 前端：`RevisionDiffPanel` 渲染测试（三类 block + 无 diff 降级）
- [ ] 前端：`chaptersApi` 类型守卫测试
- [ ] 453 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端 revise 真实实现 | `chapter_service.py` | ~40 行 |
| 后端 diff dataclass | `models.py` | ~30 行 |
| 后端 diff 构造器 | `audit/revision_diff.py` | ~45 行 |
| 后端 API 模型/映射 | `routes/chapters.py` | ~35 行 |
| 后端测试 | `test_revision_diff.py` + `test_chapters.py` | ~70 行 |
| 前端类型 | `api/chapters.ts` | ~20 行 |
| Diff 组件 | `RevisionDiffPanel.tsx` | ~80 行 |
| Pipeline 编排 | `ChapterPipeline.tsx` | ~20 行 |
| 前端测试 | `__tests__/` | ~50 行 |
| **合计** | **~9 个文件** | **~390 行** |

---

## 不做的事（Out of Scope）

- ❌ 不做字符级 inline diff——段落块 diff 足够
- ❌ 不做历史 diff 持久化——只展示最近一次修订
- ❌ 不做 diff 下载/导出
- ❌ 不做"任意两版本比较"
- ❌ 不做 `GET /diff` 端点——diff 内联在 revise 响应中
- ❌ 不改 `ShortStoryService`——短篇 diff 后续单独处理
- ❌ 不把 revise endpoint 改造成 full pipeline——truth / export 不在 revise 内执行
- ❌ 不清理 `ChapterResult.error` 中的 `revision_mode=...` 编码方式（小债另开）
