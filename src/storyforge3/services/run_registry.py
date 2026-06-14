from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from storyforge3.models import PipelineRunRecord, RunStatus, StageResult
from storyforge3.storage import BookStorage, StoragePaths

ACTIVE_STATUSES = {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN}
TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.RESUMABLE, RunStatus.CANCELLED}


class RunRegistry:
    """Process-local run registry with durable run records.

    Running tasks live only in this Python process. On startup, persisted records
    still marked pending/running/waiting are downgraded to resumable because the
    actual asyncio task cannot survive a backend restart.
    """

    def __init__(self, storage: BookStorage, paths: StoragePaths) -> None:
        self.storage = storage
        self.paths = paths
        self._records: dict[str, PipelineRunRecord] = {}
        self._started_monotonic: dict[tuple[str, str], float] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, book_id: str, chapter_no: int, *, mode: str, target_stages: list[str]) -> PipelineRunRecord:
        record = PipelineRunRecord(
            run_id=uuid4().hex,
            book_id=book_id,
            chapter_no=chapter_no,
            mode=mode,
            target_stages=list(target_stages),
            status=RunStatus.PENDING,
            current_stage=None,
            started_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._records[record.run_id] = record
        self._persist(record)
        return record

    def get(self, run_id: str) -> PipelineRunRecord | None:
        record = self._records.get(run_id)
        if record is not None:
            return record
        return self._find_record(run_id)

    def get_current(self, book_id: str, chapter_no: int) -> PipelineRunRecord | None:
        pointer = self.storage.read_json(self.paths.current_run_file(book_id, chapter_no))
        if not pointer:
            return None
        run_id = str(pointer.get("run_id") or "")
        if not run_id:
            return None
        return self.get(run_id)

    def mark_run_start(self, run_id: str) -> PipelineRunRecord:
        record = self._require(run_id)
        record = replace(record, status=RunStatus.RUNNING, updated_at=_now_iso())
        return self._save(record)

    def mark_stage_start(self, run_id: str, stage: str) -> PipelineRunRecord:
        record = self._require(run_id)
        started_at = _now_iso()
        stage_result = StageResult(stage=stage, status="running", started_at=started_at)
        stage_results = {**record.stage_results, stage: stage_result}
        self._started_monotonic[(run_id, stage)] = perf_counter()
        record = replace(
            record,
            status=RunStatus.RUNNING,
            current_stage=stage,
            updated_at=started_at,
            stage_results=stage_results,
            resume_from=stage,
        )
        return self._save(record)

    def mark_stage_complete(self, run_id: str, stage: str, summary: dict | None = None) -> PipelineRunRecord:
        record = self._require(run_id)
        previous = record.stage_results.get(stage)
        finished_at = _now_iso()
        duration_ms = self._duration_ms(run_id, stage)
        stage_result = StageResult(
            stage=stage,
            status="completed",
            started_at=previous.started_at if previous else finished_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            summary=summary,
        )
        stage_results = {**record.stage_results, stage: stage_result}
        record = replace(record, updated_at=finished_at, stage_results=stage_results, resume_from=None)
        return self._save(record)

    def mark_stage_skipped(self, run_id: str, stage: str, summary: dict | None = None) -> PipelineRunRecord:
        record = self._require(run_id)
        finished_at = _now_iso()
        stage_result = StageResult(
            stage=stage,
            status="skipped",
            started_at=finished_at,
            finished_at=finished_at,
            duration_ms=0,
            summary=summary,
        )
        stage_results = {**record.stage_results, stage: stage_result}
        record = replace(record, updated_at=finished_at, stage_results=stage_results)
        return self._save(record)

    def mark_stage_failed(self, run_id: str, stage: str, error_code: str, error_message: str) -> PipelineRunRecord:
        record = self._require(run_id)
        previous = record.stage_results.get(stage)
        finished_at = _now_iso()
        stage_result = StageResult(
            stage=stage,
            status="failed",
            started_at=previous.started_at if previous else finished_at,
            finished_at=finished_at,
            duration_ms=self._duration_ms(run_id, stage),
            error_code=error_code,
            error_message=error_message,
        )
        stage_results = {**record.stage_results, stage: stage_result}
        record = replace(
            record,
            status=RunStatus.FAILED,
            current_stage=stage,
            updated_at=finished_at,
            stage_results=stage_results,
            error_code=error_code,
            error_message=error_message,
            resume_from=stage,
        )
        return self._save(record)

    def complete(self, run_id: str) -> PipelineRunRecord:
        record = self._require(run_id)
        record = replace(
            record,
            status=RunStatus.COMPLETED,
            current_stage=None,
            updated_at=_now_iso(),
            error_code=None,
            error_message=None,
            resume_from=None,
        )
        return self._save(record)

    def fail(self, run_id: str, error_code: str, error_message: str, *, resume_from: str | None = None) -> PipelineRunRecord:
        record = self._require(run_id)
        record = replace(
            record,
            status=RunStatus.FAILED,
            updated_at=_now_iso(),
            error_code=error_code,
            error_message=error_message,
            resume_from=resume_from or record.current_stage,
        )
        return self._save(record)

    def cancel(self, run_id: str) -> PipelineRunRecord:
        record = self._require(run_id)
        task = self._tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
        record = replace(record, status=RunStatus.CANCELLED, current_stage=None, updated_at=_now_iso(), resume_from=None)
        return self._save(record)

    def attach_task(self, run_id: str, task: asyncio.Task) -> None:
        self._tasks[run_id] = task

    def detach_task(self, run_id: str) -> None:
        self._tasks.pop(run_id, None)

    def scan_resumable_runs(self) -> list[PipelineRunRecord]:
        recovered: list[PipelineRunRecord] = []
        for path in self.paths.books_root.glob("*/chapters/*/runs/*.json"):
            if path.name == "current_run.json":
                continue
            record = self._load_from_file(path)
            if record is None or record.status not in ACTIVE_STATUSES:
                continue
            resume_from = record.current_stage or (record.target_stages[0] if record.target_stages else None)
            record = replace(record, status=RunStatus.RESUMABLE, updated_at=_now_iso(), resume_from=resume_from)
            recovered.append(self._save(record))
        return recovered

    def _save(self, record: PipelineRunRecord) -> PipelineRunRecord:
        self._records[record.run_id] = record
        self._persist(record)
        return record

    def _persist(self, record: PipelineRunRecord) -> None:
        self.storage.write_json(self.paths.run_file(record.book_id, record.chapter_no, record.run_id), _record_to_dict(record))
        pointer_path = self.paths.current_run_file(record.book_id, record.chapter_no)
        current_pointer = self.storage.read_json(pointer_path) or {}
        if current_pointer.get("run_id") != record.run_id:
            self.storage.write_json(pointer_path, {"run_id": record.run_id})

    def _require(self, run_id: str) -> PipelineRunRecord:
        record = self.get(run_id)
        if record is None:
            raise KeyError(f"run not found: {run_id}")
        return record

    def _find_record(self, run_id: str) -> PipelineRunRecord | None:
        for path in self.paths.books_root.glob(f"*/chapters/*/runs/{run_id}.json"):
            record = self._load_from_file(path)
            if record is not None:
                self._records[record.run_id] = record
                return record
        return None

    def _load_from_file(self, path: Path) -> PipelineRunRecord | None:
        data = self.storage.read_json(path)
        if not data:
            return None
        return _record_from_dict(data)

    def _duration_ms(self, run_id: str, stage: str) -> int | None:
        started = self._started_monotonic.pop((run_id, stage), None)
        if started is None:
            return None
        return int((perf_counter() - started) * 1000)


def _record_to_dict(record: PipelineRunRecord) -> dict:
    data = asdict(record)
    data["status"] = record.status.value
    data["stage_results"] = {stage: asdict(result) for stage, result in record.stage_results.items()}
    return data


def _record_from_dict(data: dict) -> PipelineRunRecord:
    stage_results = {
        str(stage): StageResult(**payload)
        for stage, payload in (data.get("stage_results") or {}).items()
        if isinstance(payload, dict)
    }
    return PipelineRunRecord(
        run_id=str(data["run_id"]),
        book_id=str(data["book_id"]),
        chapter_no=int(data["chapter_no"]),
        mode=str(data.get("mode") or "full"),
        target_stages=[str(stage) for stage in data.get("target_stages", [])],
        status=RunStatus(str(data.get("status") or RunStatus.PENDING.value)),
        current_stage=data.get("current_stage"),
        started_at=str(data.get("started_at") or _now_iso()),
        updated_at=str(data.get("updated_at") or _now_iso()),
        stage_results=stage_results,
        llm_calls=list(data.get("llm_calls") or []),
        error_code=data.get("error_code"),
        error_message=data.get("error_message"),
        resume_from=data.get("resume_from"),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
