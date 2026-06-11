from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PipelineRunRecord:
    """Single pipeline operation record."""

    book_id: str
    chapter_no: int
    task: str
    timestamp: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: float | None = None
    status: str = ""
    error: str | None = None
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    context_sources: list[dict[str, Any]] = field(default_factory=list)
    status_before: str | None = None
    status_after: str | None = None
    audit_passed: bool | None = None
    audit_blocking: int | None = None
    audit_warnings: int | None = None


class PipelineLogger:
    """Append JSONL records for pipeline operations."""

    def __init__(self, books_dir: str | Path) -> None:
        self._books_dir = Path(books_dir)

    def append(self, record: PipelineRunRecord) -> Path:
        """Append a record to the book's JSONL log and return the log path."""
        path = self._log_path(record.book_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(record), ensure_ascii=False, default=str) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return path

    def read_records(self, book_id: str, *, limit: int = 100) -> list[PipelineRunRecord]:
        """Read the most recent records from a book's JSONL log."""
        path = self._log_path(book_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        recent = lines[-limit:] if limit > 0 else []
        records: list[PipelineRunRecord] = []
        allowed = PipelineRunRecord.__dataclass_fields__
        for line in recent:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                records.append(PipelineRunRecord(**{key: value for key, value in data.items() if key in allowed}))
            except (json.JSONDecodeError, TypeError):
                continue
        return records

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as an ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    def _log_path(self, book_id: str) -> Path:
        return self._books_dir / book_id / "runs" / "pipeline.jsonl"
