# Codex 指令：Phase 4A — 原子写入 + 失败持久化

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 3 P0 已通过（3/3 E2E，266 测试，ruff clean）

---

## 任务概述

两个独立任务，按顺序完成。每个任务完成后确保 `ruff check .` 和 `pytest` 全绿。

---

## 任务 1：原子写入（storage.py）

### 当前问题

`src/storyforge3/storage.py` 的 `BookStorage.write_text()` 和 `write_json()` 直接调用 `path.write_text()`，如果写入中途崩溃（断电、磁盘满、进程 killed），目标文件会被截断为 0 字节或只写入一半。

### 修改目标

修改 `write_text` 和 `write_json` 使用 temp+rename 模式：

```python
def write_text(self, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)  # os.replace，原子操作
    except BaseException:
        # 清理临时文件
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

def write_json(self, path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
```

### 测试要求

新增 `tests/test_storage_atomic.py`：

1. **test_write_text_atomic_on_success**：写入后目标文件存在，临时文件不存在
2. **test_write_text_preserves_old_on_failure**：模拟 write_text 中途失败（monkeypatch Path.write_text 在 tmp 文件上 raise），验证原文件内容不变
3. **test_write_json_atomic_on_success**：同上，JSON 版
4. **test_write_json_preserves_old_on_failure**：同上，JSON 版
5. **test_write_text_creates_parent_dirs**：验证新目录结构下仍能写入

### 验收

```powershell
ruff check src/storyforge3/storage.py
.\.venv\Scripts\python.exe -m pytest tests/test_storage_atomic.py -v
.\.venv\Scripts\python.exe -m pytest -q   # 全量 266+ 测试不退步
```

---

## 任务 2：失败时持久化中间产物（workflow.py）

### 当前问题

`src/storyforge3/workflow.py` 的 `ChapterWorkflow.run()` 在失败时通过 `_needs_review()` 返回 `ChapterResult`，但 **不持久化任何中间产物**。E2E 脚本 `scripts/e2e_multi_chapter.py` 有自己的 `_write_chapter_diagnostics()` 方法，但这是 E2E 专用的，引擎本身不提供此能力。

这意味着：
- 非 E2E 消费者（CLI、未来的 API）在失败时拿不到诊断信息
- 失败后无法 post-mortem 审计结果和最后一次 draft

### 修改目标

在 `ChapterWorkflow` 中新增 `_persist_diagnostics()` 方法，在 `_needs_review()` 被调用时自动写出中间产物。

**新增方法**：

```python
def _persist_diagnostics(
    self,
    book_id: str,
    chapter_no: int,
    text: str,
    audit: AuditResult | None,
    error: str,
) -> None:
    """Write diagnostics on failure for post-mortem analysis."""
    diag_dir = Path(self.config.books_dir) / book_id / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    prefix = diag_dir / f"chapter_{chapter_no}"

    # Last draft/revision text
    if text:
        (prefix.with_name(f"chapter_{chapter_no}_last_draft.md")).write_text(text, encoding="utf-8")

    # Audit result
    if audit is not None:
        audit_path = prefix.with_name(f"chapter_{chapter_no}_audit.json")
        audit_path.write_text(
            json.dumps(asdict(audit), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # Error summary
    error_path = prefix.with_name(f"chapter_{chapter_no}_error.txt")
    error_path.write_text(error, encoding="utf-8")
```

**修改 `_needs_review()`**：

在 `self.state_machine.force_needs_review(...)` 之后、return 之前，调用 `self._persist_diagnostics()`：

```python
def _needs_review(
    self,
    book_id: str,
    chapter_no: int,
    title: str,
    text: str,
    error: str,
    audit: AuditResult | None,
    truth: TruthData | None,
    llm_calls: list[LLMCallRecord],
) -> ChapterResult:
    self.state_machine.force_needs_review(book_id, chapter_no, error)
    self._persist_diagnostics(book_id, chapter_no, text, audit, error)  # ← 新增
    return ChapterResult(...)
```

**新增 import**：`from dataclasses import asdict`（已有 `json` import）

### 测试要求

新增 `tests/test_workflow_diagnostics.py`：

1. **test_diagnostics_written_on_revision_exhausted**：模拟 audit 2 轮不过，验证 `diagnostics/chapter_1_last_draft.md` 和 `chapter_1_audit.json` 和 `chapter_1_error.txt` 都被写入
2. **test_diagnostics_written_on_exception**：模拟 draft 阶段抛异常，验证 `chapter_1_error.txt` 被写入（last_draft 可能空）
3. **test_no_diagnostics_on_success**：正常通过时，验证 `diagnostics/` 目录不存在或为空
4. **test_diagnostics_audit_json_valid**：验证 audit.json 可被 `json.loads()` 解析

测试策略：mock `ChapterWorkflow` 的依赖（LLM、audit_runner 等），不需要真实 LLM 调用。

### 验收

```powershell
ruff check src/storyforge3/workflow.py
.\.venv\Scripts\python.exe -m pytest tests/test_workflow_diagnostics.py -v
.\.venv\Scripts\python.exe -m pytest -q   # 全量 266+ 测试不退步
```

---

## 完成后回报格式

完成后请回报：

```
给 ClaudeCode 产品经理的执行结果：

Phase 4A 任务 1（原子写入）：
- [状态]
- 新增测试数：N
- 全量测试：N passed

Phase 4A 任务 2（失败持久化）：
- [状态]
- 新增测试数：N
- 全量测试：N passed
- ruff check：[clean / 有 warnings]
```
