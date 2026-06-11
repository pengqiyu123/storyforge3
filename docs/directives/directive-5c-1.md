# Codex 指令：Phase 5C-1 — JSONL 审计日志

> 发出日期：2026-06-08
> 产品经理：Claude Code PM
> 执行者：Codex
> 前置条件：Phase 5A 完成（301 后端测试, 14 前端测试, ruff clean）

---

## 任务概述

为每次管线运行（plan/draft/audit/revise/approve/export）写入结构化 JSONL 记录。这是 Phase 5C 的第一步，为后续 Service 对齐和快照功能提供可审计基础。

**目标**：每次管线操作自动产生一条 JSONL 记录，包含完整的运行上下文，可供事后分析。

---

## 当前状态

### 已有基础设施

1. **`LLMCallRecord`** (`models.py`): task_name, model, prompt_version, input_tokens, output_tokens, latency_ms, success, error
2. **`_persist_diagnostics()`** (`workflow.py:344-364`): 失败时写 diagnostics/ 目录（last_draft.md, audit.json, error.txt）
3. **`ContextPackage.sources_summary()`** (`context/context_package.py:46-56`): 返回上下文源元数据
4. **`ChapterStateMachine.history()`** (`state/machine.py`): 状态转换历史
5. **`_append_last_call()`** (`workflow.py:407-410`): 累积 LLMCallRecord

### 缺失

- 没有 `logging/` 模块
- 没有结构化 JSONL 写入
- LLMCallRecord 仅存内存，进程退出即丢失
- 无运行时间统计

---

## 修改目标

### 1. 新建 JSONL 日志模块

**文件**：`src/storyforge3/logging/__init__.py`（空导出）
**文件**：`src/storyforge3/logging/pipeline_logger.py`

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PipelineRunRecord:
    """Single pipeline operation record."""

    # Identity
    book_id: str
    chapter_no: int
    task: str                          # "plan" | "draft" | "audit" | "revise" | "approve" | "export" | "full_pipeline"

    # Timing
    timestamp: str                     # ISO 8601 UTC
    started_at: str | None = None      # ISO 8601 UTC
    finished_at: str | None = None     # ISO 8601 UTC
    duration_ms: float | None = None

    # Result
    status: str = ""                   # "success" | "failure"
    error: str | None = None

    # Context
    llm_calls: list[dict] = field(default_factory=list)    # serialized LLMCallRecord
    context_sources: list[dict] = field(default_factory=list)  # from ContextPackage.sources_summary()
    status_before: str | None = None
    status_after: str | None = None

    # Audit specifics (only for audit tasks)
    audit_passed: bool | None = None
    audit_blocking: int | None = None
    audit_warnings: int | None = None


class PipelineLogger:
    """Append JSONL records for pipeline operations."""

    def __init__(self, books_dir: str | Path) -> None:
        self._books_dir = Path(books_dir)

    def _log_path(self, book_id: str) -> Path:
        """Return the JSONL file path for a book."""
        return self._books_dir / book_id / "runs" / "pipeline.jsonl"

    def append(self, record: PipelineRunRecord) -> Path:
        """Append a record to the book's JSONL log. Returns the log path."""
        path = self._log_path(record.book_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        line = json.dumps(asdict(record), ensure_ascii=False, default=str) + "\n"

        # Atomic append: write to temp then replace (for safety under concurrency)
        tmp_path = path.with_suffix(".jsonl.tmp")
        with open(tmp_path, "a", encoding="utf-8") as f:
            f.write(line)
        # On Windows, rename fails if target exists, so just use append directly
        # Simple append is safe enough for JSONL logs (one line per write)
        return path

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def read_records(self, book_id: str, *, limit: int = 100) -> list[PipelineRunRecord]:
        """Read the most recent N records from a book's JSONL log."""
        path = self._log_path(book_id)
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-limit:] if len(lines) > limit else lines

        records = []
        for line in recent:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(PipelineRunRecord(**{k: v for k, v in data.items() if k in PipelineRunRecord.__dataclass_fields__}))
            except (json.JSONDecodeError, TypeError):
                continue  # skip malformed lines
        return records
```

### 2. 在 workflow.py 中添加日志钩子

**文件**：`src/storyforge3/workflow.py`

在 `ChapterWorkflow` 中注入 `PipelineLogger` 并在每个关键步骤完成时写记录。

**具体改动**：

2a. `ChapterWorkflow.__init__` 接受可选 `logger: PipelineLogger | None = None`

2b. 新增辅助方法 `_log_run`:

```python
def _log_run(
    self,
    task: str,
    *,
    status: str,
    error: str | None = None,
    started_at: str | None = None,
    status_before: str | None = None,
    status_after: str | None = None,
    audit_passed: bool | None = None,
    audit_blocking: int | None = None,
    audit_warnings: int | None = None,
    context_sources: list[dict] | None = None,
) -> None:
    if not self._logger:
        return

    record = PipelineRunRecord(
        book_id=self.book_id,
        chapter_no=self.chapter_no,
        task=task,
        timestamp=PipelineLogger.now_iso(),
        started_at=started_at,
        finished_at=PipelineLogger.now_iso(),
        duration_ms=None,  # 可后续补充
        status=status,
        error=error,
        llm_calls=[asdict(c) for c in self.llm_calls],
        context_sources=context_sources or [],
        status_before=status_before,
        status_after=status_after,
        audit_passed=audit_passed,
        audit_blocking=audit_blocking,
        audit_warnings=audit_warnings,
    )
    self._logger.append(record)
```

2c. 在以下位置调用 `_log_run`：

| 位置 | task | 触发条件 |
|------|------|----------|
| `step_plan()` 完成后 | `"plan"` | 成功或异常 |
| `step_draft()` 完成后 | `"draft"` | 成功或异常 |
| `step_audit()` 完成后 | `"audit"` | 成功或异常（附带 audit_passed/blocking/warnings） |
| `step_revise()` 完成后 | `"revise"` | 成功或异常 |
| `step_approve()` 完成后 | `"approve"` | 成功 |
| `step_export()` 完成后 | `"export"` | 成功 |
| `run()` 完成后 | `"full_pipeline"` | 成功或异常 |

**关键**：不要改变现有流程逻辑，只在关键节点追加日志调用。日志失败不能阻塞主流程（catch + pass）。

### 3. API dep 注入

**文件**：`src/storyforge3/api/deps.py`

新增 `get_pipeline_logger` 依赖：

```python
def get_pipeline_logger(config: StoryForge3Config = Depends(get_config)) -> PipelineLogger:
    return PipelineLogger(config.books_dir)
```

在 `get_chapter_service` 中将 logger 注入 ChapterWorkflow。

### 4. 测试

**文件**：`tests/test_pipeline_logger.py`

测试用例：

1. **`test_append_creates_jsonl`**：append 一条记录后，文件存在且可解析
2. **`test_append_multiple_records`**：追加多条记录，每行一条 JSON
3. **`test_read_records_returns_most_recent`**：写入 5 条，limit=3 返回最后 3 条
4. **`test_read_records_empty_file`**：文件不存在返回空列表
5. **`test_record_serialization_roundtrip`**：PipelineRunRecord → JSON → 解析回 PipelineRunRecord
6. **`test_malformed_line_skipped`**：read_records 跳过格式错误的行
7. **`test_workflow_logs_on_draft_success`**：mock draft 成功，验证 jsonl 文件写入
8. **`test_workflow_logs_on_audit_with_details`**：mock audit 返回结果，验证 audit_passed/blocking/warnings 记录
9. **`test_log_failure_does_not_block_pipeline`**：logger.append 抛异常时，管线继续运行

---

## 技术约束

1. **日志失败不阻塞主流程**：`_log_run` 内部 try/except，异常静默
2. **简单追加模式**：不做文件锁或并发控制，JSONL 单行追加天然安全
3. **不引入新依赖**：只用 stdlib（json, dataclasses, datetime, pathlib）
4. **不改变现有测试**：所有 301 后端测试必须通过
5. **不改变 API 契约**：不新增 API 端点
6. **中文注释**：公共方法有 docstring

---

## 验收

```powershell
cd storyforge3
.\.venv\Scripts\python.exe -m pytest tests/ -q   # 301 + 新增测试通过
ruff check .                                       # clean
```

功能验收：
1. 管线运行后 `{book_id}/runs/pipeline.jsonl` 存在
2. 每行是合法 JSON，包含 book_id / chapter_no / task / timestamp / status
3. draft/audit/revise 步骤均产生记录
4. audit 记录包含 audit_passed / audit_blocking / audit_warnings
5. llm_calls 字段包含 LLM 调用详情
6. logger 异常不影响管线运行
7. 全部 301 + 新增测试通过

---

## 完成后回报格式

```
给 ClaudeCode 产品经理的执行结果：

Phase 5C-1（JSONL 审计日志）：
- PipelineLogger 模块：[完成状态]
- workflow.py 日志钩子：[完成状态]
- API dep 注入：[完成状态]
- 新增测试数：N
- 全量测试：[301+N] passed
- ruff check：[clean/有警告]
- 改动文件列表：[...]
```

---

## 参考文件

1. `src/storyforge3/workflow.py` — 管线主循环，添加日志钩子
2. `src/storyforge3/models.py` — LLMCallRecord 定义
3. `src/storyforge3/context/context_package.py` — sources_summary()
4. `src/storyforge3/state/machine.py` — 状态转换历史
5. `src/storyforge3/storage.py` — 原子写入模式参考
6. `src/storyforge3/api/deps.py` — API 依赖注入
