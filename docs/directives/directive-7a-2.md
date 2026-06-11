# Codex 指令：Phase 7A-2 — 审计问题定位 + 编辑器高亮

> 发出日期：2026-06-10
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 7A-1 完成（447 tests: 403 后端 + 44 前端, ruff clean）

---

## 任务概述

让作者能从审计结果跳转到正文中的问题位置。当前 `AuditResultPanel` 只显示 `rule_id` + `message`，无法定位到编辑器中的对应文本。本阶段实现"点击问题 → 高亮定位"的最小闭环。

**当前状态**：
- 36 个机械审计规则中 ~10 个天然与段落相关（`golden_three_hook`、`cliffhanger`、`info_dump` 等）
- `MechanicalContext` 已有 `paragraphs: tuple[str, ...]`（段落分割基础设施工就绪）
- 修订补丁系统（`revision_patch.py:_window_for_rule()`）已证明段落级定位可行
- `AuditResultPanel` 展示 rule_id + message，但不可点击，不显示 detail
- `ChapterEditor` 无高亮/装饰能力，无 `forwardRef`
- API 审计响应（`AuditResponse`）不返回 `rule_results`（仅聚合的 issue ID 列表）

**核心原则**：
1. **能定位的规则就定位，不能定位的优雅降级为普通问题项**
2. 不改所有 36 条规则——只增强天然与段落相关的 ~10 条
3. 高亮粒度：段落级（不是字符级），足够作者一眼看到问题位置
4. 前端不重复计算段落分割——用后端提供的 `snippet` 文本匹配

---

## Part 1：后端 — 审计规则增加定位信息

### 1.1 规则 detail 扩展

对以下 ~10 条天然段落相关的规则，在 `detail` dict 中增加两个字段：

```python
detail = {
    # ... 现有字段 (observed, found 等) 不变 ...
    "paragraph_indices": [0, 1, 2],     # 出问题的段落索引列表（0-based）
    "snippet": "第一段的实际文本...",      # 第一个问题段落的原文（截断到 200 字符）
}
```

**需要增强的规则**（位于 `src/storyforge3/audit/rules.py`）：

| 规则 | 定位方式 | snippet 来源 |
|------|---------|-------------|
| `golden_three_hook` | paragraphs[0:3] | 前 3 段合并，截断 |
| `cliffhanger_presence` | paragraphs[-3:] | 末 3 段合并，截断 |
| `info_dump` | 最长段落 index | 最长段落原文，截断 |
| `max_paragraph_length` | 最长段落 index | 最长段落原文，截断 |
| `paragraph_count` | 全文（不定位） | 不提供 |
| `pacing_flat` | 连续平静段落的 index 列表 | 第一个平静段落 |
| `repeated_phrase` | 重复短语所在段落 index 列表 | 首次出现的段落 |
| `forbidden_patterns` | 匹配到违禁词的段落 index | 匹配段落 |
| `internal_engine_terms` | 匹配到引擎术语的段落 index | 匹配段落 |
| `unbalanced_quote_or_bracket` | 不平衡的段落 index | 不平衡段落 |

**snippet 截断规则**：

```python
def _truncate_snippet(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
```

放在 `rules.py` 内作为模块级辅助函数。

**实现方式**：在 `make_result()` 调用处增加 `paragraph_indices` 和 `snippet`。不改 `RuleResult` 模型——`detail: dict` 已经是灵活容器。

### 1.2 API 响应增强

**`AuditResponse`** 模型（`routes/chapters.py`）新增 `rule_results` 字段：

```python
class AuditResponse(BaseModel):
    chapter_no: int
    passed: bool
    blocking_issues: list[str]
    warnings: list[str]
    info: list[str]
    rule_results: list[RuleResultResponse] = []   # 新增

class RuleResultResponse(BaseModel):
    rule_id: str
    passed: bool
    severity: str
    category: str
    message: str
    detail: dict = {}
```

**映射逻辑**：在现有审计端点中，从 `AuditResult.rule_results` 映射到 `RuleResultResponse` 列表。

### 1.3 哪些规则不改

以下规则是全文密度/比率型，没有有意义的段落定位——**不改**：

`ai_tell_density`, `hedge_density`, `action_sentence_ratio`, `dialogue_density`, `didactic_words`, `explanatory_patterns`, `meta_patterns`, `report_terms`, `template_emotion`, `show_dont_tell`, `surprise_word_density`, `vague_word_density`, `sentence_start_repetition`, `paragraph_ending_repetition`, `scene_anchor_presence`, `conflict_presence`, `sensory_detail_presence`, `character_name_consistency`, `chapter_length`, `word_count`, `title_presence`

这些规则的 `detail` 不变，前端处理时无 `paragraph_indices` 则不可点击——优雅降级。

---

## Part 2：前端 — 审计面板交互 + 编辑器高亮

### 2.1 AuditResultPanel 增强

**当前**：静态展示 `rule_id` + `message` + severity badge。

**改为**：

1. 新增 prop：

```typescript
interface AuditResultPanelProps {
  result?: AuditResult | null;
  onLocateIssue?: (rule: RuleResult) => void;  // 新增：点击问题回调
}
```

2. `RuleRow` 改为可点击（有 `paragraph_indices` 的规则）：
   - 有 `paragraph_indices` → 添加 `cursor-pointer` + hover 样式 + 点击调用 `onLocateIssue(rule)`
   - 无 `paragraph_indices` → 保持当前样式，不可点击
   - 可点击的规则显示一个小定位图标（`Crosshair` 或 `MapPin`，来自 Lucide）

3. 显示 `detail.snippet`（如果有）：在失败规则的 message 下方，小字灰色展示 snippet 片段

### 2.2 ChapterEditor 高亮支持

**当前**：纯展示/编辑组件，无外部高亮接口。

**改为**：

1. 新增 prop：

```typescript
interface ChapterEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
  highlights?: HighlightRange[];  // 新增
  scrollToOffset?: number;        // 新增：滚动到指定字符偏移
}

interface HighlightRange {
  from: number;    // 起始字符偏移
  to: number;      // 结束字符偏移
  severity: "BLOCKING" | "WARNING";
}
```

2. 使用 CodeMirror `Decoration` + `StateField` 实现高亮：

```typescript
import { Decoration, type DecorationSet, EditorView } from "@codemirror/view";
import { StateField } from "@codemirror/state";

// 创建高亮装饰
const highlightField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update: (decorations, tr) => {
    // 如果文本变了（编辑模式），重新映射位置
    return tr.docChanged ? decorations.map(tr.changes) : decorations;
  },
});

// 根据 highlights prop 创建装饰集
function buildDecorations(view: EditorView, ranges: HighlightRange[]): DecorationSet {
  const widgets = ranges.map(({ from, to, severity }) =>
    Decoration.mark({
      class: severity === "BLOCKING" ? "cm-audit-blocking" : "cm-audit-warning",
    }).range(Math.min(from, view.state.doc.length), Math.min(to, view.state.doc.length))
  );
  return Decoration.set(widgets, true);
}
```

3. **CSS 样式**（添加到 `ChapterEditor.tsx` 的 `baseTheme` 中）：

```typescript
".cm-audit-blocking": { backgroundColor: "rgba(239, 68, 68, 0.15)", borderBottom: "2px solid #ef4444" },
".cm-audit-warning": { backgroundColor: "rgba(245, 158, 11, 0.15)", borderBottom: "2px solid #f59e0b" },
```

4. **滚动支持**：当 `scrollToOffset` 变化时，使用 `EditorView.dispatch({ effects: EditorView.scrollIntoView(pos, { y: "center" }) })` 滚动到目标位置。

5. **实现方式**：使用 `useEffect` 监听 `highlights` 变化，重新构建 decoration set 并 dispatch 到 editor view。editor view 的 ref 已存在（`editorRef`），可直接 dispatch。

### 2.3 ChapterPipeline 编排

`ChapterPipeline` 连接 `AuditResultPanel` 的点击事件和 `ChapterEditor` 的高亮：

1. 新增状态：

```typescript
const [activeHighlights, setActiveHighlights] = useState<HighlightRange[]>([]);
const [scrollToOffset, setScrollToOffset] = useState<number | undefined>();
```

2. 处理 `onLocateIssue`：

```typescript
function handleLocateIssue(rule: RuleResult) {
  const indices = (rule.detail?.paragraph_indices as number[]) ?? [];
  const text = editing ? editText : (result?.text ?? "");

  // 将段落索引转换为字符偏移
  const ranges = paragraphIndicesToRanges(text, indices);
  setActiveHighlights(
    ranges.map(r => ({
      ...r,
      severity: rule.severity === "BLOCKING" ? "BLOCKING" : "WARNING",
    }))
  );

  // 滚动到第一个高亮位置
  if (ranges.length > 0) {
    setScrollToOffset(ranges[0].from);
  }
}
```

3. 辅助函数 `paragraphIndicesToRanges`：

```typescript
function paragraphIndicesToRanges(text: string, indices: number[]): { from: number; to: number }[] {
  const paragraphs = text.split(/\n{2,}/);  // 与后端分割方式一致
  let offset = 0;
  const ranges: { from: number; to: number }[] = [];

  for (let i = 0; i < paragraphs.length; i++) {
    const para = paragraphs[i];
    if (indices.includes(i)) {
      ranges.push({ from: offset, to: offset + para.length });
    }
    offset += para.length;
    // 计算 \n\n 分隔符的长度
    if (i < paragraphs.length - 1) {
      const remaining = text.slice(offset);
      const match = remaining.match(/^\n{2,}/);
      offset += match ? match[0].length : 2;
    }
  }
  return ranges;
}
```

**注意**：这个函数的段落分割逻辑需要与后端 `MechanicalContext` 的分割逻辑对齐。验收时需要确认。如果分割方式不一致，可以改为用 `snippet` 文本搜索定位。

4. 传递给 ChapterEditor：

```tsx
<ChapterEditor
  value={editing ? editText : currentText}
  readOnly={!editing}
  onChange={setEditText}
  highlights={activeHighlights}
  scrollToOffset={scrollToOffset}
  placeholder="章节正文会在管线运行后显示。"
  className="h-52"
/>
```

5. 传递给 AuditResultPanel：

```tsx
<AuditResultPanel result={lastAudit} onLocateIssue={handleLocateIssue} />
```

6. **清除高亮**：当执行新的管线操作（draft/audit/revise）时，清除 `activeHighlights` 和 `scrollToOffset`。

### 2.4 TypeScript 类型更新

在 `web/src/api/chapters.ts` 更新：

```typescript
export interface AuditResult {
  chapter_no: number;
  passed: boolean;
  blocking_issues: string[];
  warnings: string[];
  info: string[];
  rule_results?: RuleResult[];  // 已有，现在后端会实际填充
}
```

无需修改 `RuleResult`——`detail: Record<string, unknown>` 已经可以包含 `paragraph_indices` 和 `snippet`。

---

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| 段落级定位 | `audit/revision_patch.py:_window_for_rule()` | 已证明可行的段落提取模式 |
| 段落分割 | `audit/context.py:MechanicalContext.paragraphs` | 复用已有分割基础 |
| CodeMirror Decoration | CM6 官方 `Decoration.mark()` API | 标准 API，无需第三方库 |
| 滚动到位置 | CM6 `EditorView.scrollIntoView()` | 标准 API |
| 段落偏移计算 | 后端 `split_paragraphs()` 逻辑 | 前端对齐分割方式 |

**新写比例**：约 40%。段落分割基础、规则逻辑、CodeMirror 框架均已存在，新增的是连接层。

---

## 验收标准

### 后端

- [ ] ~10 条段落相关规则在 `detail` 中包含 `paragraph_indices` 和 `snippet`
- [ ] `AuditResponse` 包含 `rule_results` 列表
- [ ] `RuleResultResponse` 模型包含完整字段
- [ ] 密度型规则不包含 `paragraph_indices`（优雅降级）
- [ ] 现有 403 tests 不退步

### 前端

- [ ] `AuditResultPanel` 有 `paragraph_indices` 的规则行可点击，显示定位图标
- [ ] 点击可定位规则 → `ChapterEditor` 高亮对应段落并滚动到位置
- [ ] BLOCKING 问题红色高亮，WARNING 问题黄色高亮
- [ ] 无 `paragraph_indices` 的规则行不可点击（灰色，无图标）
- [ ] snippet 在失败规则下方灰色展示
- [ ] 新管线操作清除高亮
- [ ] `ChapterEditor` 支持 `highlights` + `scrollToOffset` props

### 测试

- [ ] 后端：至少 3 条规则测试确认 `paragraph_indices` 和 `snippet` 存在且正确
- [ ] 后端：`AuditResponse` 包含 `rule_results` 的 API 测试
- [ ] 前端：`AuditResultPanel` 点击交互测试
- [ ] 前端：`ChapterEditor` 高亮渲染测试
- [ ] 前端：`paragraphIndicesToRanges` 辅助函数测试
- [ ] 447 基线 tests 不退步

### 质量

- [ ] `ruff check .` clean
- [ ] `pnpm build` clean（除已知 CodeMirror chunk 警告）
- [ ] `pnpm test` 全绿

---

## 估算工作量

| 部分 | 文件 | 预估行数 |
|------|------|---------|
| 后端规则增强 | `audit/rules.py` | ~40 行（10 规则各加 ~4 行） |
| 后端辅助函数 | `audit/rules.py` | ~5 行（_truncate_snippet） |
| 后端 API 响应 | `routes/chapters.py` | ~25 行（RuleResultResponse + 映射） |
| 后端测试 | `test_audit/` + `test_chapters.py` | ~40 行 |
| 前端 AuditResultPanel | `AuditResultPanel.tsx` | ~30 行（交互 + snippet 展示） |
| 前端 ChapterEditor | `ChapterEditor.tsx` | ~50 行（decoration + scroll + CSS） |
| 前端 ChapterPipeline | `ChapterPipeline.tsx` | ~40 行（编排 + 辅助函数） |
| 前端测试 | `__tests__/` | ~50 行 |
| **合计** | **~8 个文件** | **~280 行** |

---

## 不做的事（Out of Scope）

- ❌ 不改全文密度型规则（它们没有有意义的段落定位）
- ❌ 不做字符级精确定位（段落级足够，后续可迭代）
- ❌ 不做 LLM 审计问题的定位（`LLMAuditIssue` 无位置信息，结构完全不同）
- ❌ 不做多规则同时高亮（一次只高亮一个规则的段落）
- ❌ 不做高亮持久化（切换规则或操作后高亮清除）
- ❌ 不改审计规则的核心逻辑（只加 detail 字段）
