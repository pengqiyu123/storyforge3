# 指令 P1-1b：章节产物一致性诊断 + truth 防御测试

> 下发 Codex。前置：P1-1 完成（532 passed）。
> 目标：兑现 PM 对 Trae 分析的承诺（见 `reviews/codex-current-status.md` §F 附加项 7/8）——让系统能识别"有产物无 state"的幽灵章节（如《别打了》ch3/ch4），并补 truth retriever 防御测试断言。完成后回报。

## 背景

P1-1 让 RunRecord 成为运行真相源，但**历史产物与状态机的分裂**仍未解决：`book.json.current_chapter=2`，但 ch3/ch4 有 truth+export+snapshot 却无正文、无 state（"幽灵章节"）。这是 RunRecord 缺失时代遗留的不一致。本阶段引入 reconciliation 诊断，让系统第一次能"看见并报告"自己的不一致，而非静默忽略。

## 任务

### 1. `ChapterReconciler`（新文件 `src/storyforge3/services/chapter_reconciler.py`）

扫描 book 所有章节，对照 6 类产物报告一致性。

**扫描范围**：取 `chapters/` `plans/` `truth/` `exports/` `state` `runs/` 六处产物的最大章节号 `N`，扫描 `1..N` 全部章节（即使无正文也要扫，这样 ch3/ch4 会被发现）。

**每章报告字段**：

```python
@dataclass(frozen=True)
class ChapterConsistency:
    chapter_no: int
    has_text: bool        # chapters/XXXX.md
    has_plan: bool        # plans/XXXX.json
    has_truth: bool       # truth/chapter-XXXX.json
    has_export: bool      # exports/chapter-XXXX.txt
    has_state: bool       # chapter_states.json 有该章记录
    has_run: bool         # runs/ 有该章运行记录
    state_status: str | None  # 状态机里的 status（无则 None）
    status: str           # "consistent" | "inconsistent"
    inconsistent_reasons: tuple[str, ...]
```

**inconsistent 规则**（基于《别打了》ch3/ch4 实证）：

| reason | 触发条件 | 含义 |
|--------|---------|------|
| `export_without_state` | has_export 且 not has_state | 导出了但状态机无记录（ch3/ch4） |
| `export_without_text` | has_export 且 not has_text | 导出了但正文文件丢失（ch3/ch4） |
| `truth_without_state` | has_truth 且 not has_state | 有 truth 但无状态（未来泄漏风险信号） |
| `orphan_state` | has_state(approved/exported) 且 not has_text | 状态在但正文没了 |

**注意**：`approved` 但 `not has_export` **不算 inconsistent**（approved 不强制导出，ch2 即如此）。只标记上述 4 类真正异常。

**返回**：

```python
@dataclass(frozen=True)
class BookReconciliation:
    book_id: str
    chapters: tuple[ChapterConsistency, ...]
    inconsistent_count: int
    max_chapter: int
```

### 2. `GET /api/books/{book_id}/reconcile` 端点

**文件**：`src/storyforge3/api/routes/books.py`（或 chapters.py）

```python
@router.get("/{book_id}/reconcile")
async def reconcile_book(book_id, service = Depends(...)):
    return ok(_reconciliation_to_response(reconciler.reconcile(book_id)))
```

返回 `BookReconciliation` 序列化。无产物时返回空 chapters（不报错）。

### 3. truth retriever 防御测试

**文件**：`tests/test_truth_retriever.py`（新或已有）

`retriever.py:49/56/64` 已是严格 `< chapter_no` 过滤（代码正确）。补测试断言该不变量：

```python
def test_retrieve_excludes_current_and_future_chapters():
    """生成第 N 章时，truth 召回集合 chapter_no 必须严格 < N。"""
    # 构造 book 含 ch1/ch2/ch3 truth
    # 对 chapter_no=3 调 retrieve_for_prompt
    # 断言返回的每个 entry.chapter_no < 3（不含 3，不含 4+）
```

至少 2 个测试：单章召回边界 + 多章召回全部 < 目标。

## Part 3：借鉴来源

| 借鉴内容 | 来源文件 | 借鉴方式 |
|---------|---------|---------|
| **完整性校验模式**（file_sha + semantic_sha + manifest 比对） | `storyforge2/engine/services/export_service.py:51-87` verify_export_integrity | **模式复用** → ChapterConsistency 的多维度对照思路 |
| **文件扫描收集** | `storyforge3/snapshot.py:109-119` `_collect_files` + `list_snapshots` glob | **直接复用** → reconcile 的 6 类产物 glob 扫描 |
| **glob 目录扫描** | `storyforge3/truth/store.py:53-63` `load_history` | **模式复用** → 按章节号扫描升序 |
| **truth 过滤不变量** | `storyforge3/truth/retriever.py:49/56/64` | **直接复用** → 防御测试断言的目标代码（已正确，补测试） |

**新写比例**：约 **40%**。文件扫描/glob 模式全部复用 SF3 既有；新写的是 inconsistent 规则判定 + ChapterConsistency dataclass + 端点包装。

## 验收门禁

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q     # ≥532 + 新增 reconcile/truth 测试
.\.venv\Scripts\python.exe -m ruff check .              # clean
```

手动：
- `GET /api/books/{book_id}/reconcile` 对《别打了》返回 ch3/ch4 标记 `inconsistent`（reasons 含 `export_without_state` + `export_without_text` + `truth_without_state`），ch1/ch2 `consistent`。
- `inconsistent_count >= 2`。
- truth 防御测试通过（召回集合严格 < 目标章）。

## 必须覆盖的测试

- ChapterReconciler 单元测试：consistent 章 / 各类 inconsistent / 无产物书。
- `GET /reconcile` API 测试。
- truth retriever 防御测试（2+ 个：边界 + 多章）。
- **用《别打了》真实数据**（ch3/ch4 幽灵章节）作为集成验收样本——可在测试 fixture 里构造同等异常图景。

## 红线

- ❌ 不破坏 532 基线。
- ❌ reconcile **只读诊断**，不修改任何产物/state（不清理 ch3/ch4，由 PM 验收后决定）。
- ❌ 不改 truth retriever 过滤逻辑（已正确），只补测试。
- ❌ approved 未 export 不算 inconsistent（避免误报 ch2）。

## 回报

- commit hash（建议 `feat(reconcile): chapter consistency diagnosis + truth retrieval guard tests`）
- pytest + ruff 结果
- 对《别打了》一次 `GET /reconcile` 输出（展示 ch3/ch4 inconsistent + reasons）

## 不做的事（Out of Scope）

- ❌ 不做 reconciliation 前端展示（P1-2 Run Viewer 时附带）
- ❌ 不清理/修复 ch3/ch4 幽灵章节（PM 验收 reconcile 准确性后再决定）
- ❌ 不做自动修复（只诊断，不 heal）
- ❌ 不改 book.json.current_chapter（等 reconcile + PM 确认真实进度后再定）
