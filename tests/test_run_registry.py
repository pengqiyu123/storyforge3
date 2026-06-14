from __future__ import annotations

import asyncio
import json
from pathlib import Path

from storyforge3.models import RunStatus
from storyforge3.services.run_registry import RunRegistry
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


def test_run_registry_persists_stage_results_and_current_pointer(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    registry = RunRegistry(BookStorage(paths.books_root), paths)

    record = registry.start("book", 3, mode="full", target_stages=["plan", "draft"])
    registry.mark_stage_start(record.run_id, "plan")
    registry.mark_stage_complete(record.run_id, "plan", {"goal": "推进主线"})
    registry.complete(record.run_id)

    loaded = registry.get_current("book", 3)
    assert loaded is not None
    assert loaded.run_id == record.run_id
    assert loaded.status == RunStatus.COMPLETED
    assert loaded.stage_results["plan"].status == "completed"
    assert loaded.stage_results["plan"].summary == {"goal": "推进主线"}

    current_run = json.loads((tmp_path / "book" / "chapters" / "0003" / "runs" / "current_run.json").read_text(encoding="utf-8"))
    assert current_run == {"run_id": record.run_id}


def test_run_registry_marks_running_records_resumable_on_startup_scan(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    registry = RunRegistry(BookStorage(paths.books_root), paths)
    record = registry.start("book", 4, mode="full", target_stages=["plan", "draft", "audit"])
    registry.mark_stage_start(record.run_id, "draft")

    recovered = RunRegistry(BookStorage(paths.books_root), paths)
    recovered.scan_resumable_runs()

    loaded = recovered.get_current("book", 4)
    assert loaded is not None
    assert loaded.status == RunStatus.RESUMABLE
    assert loaded.current_stage == "draft"
    assert loaded.resume_from == "draft"


def test_run_registry_cancel_marks_record_cancelled(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    registry = RunRegistry(BookStorage(paths.books_root), paths)
    record = registry.start("book", 5, mode="single", target_stages=["draft"])

    registry.cancel(record.run_id)

    loaded = registry.get_current("book", 5)
    assert loaded is not None
    assert loaded.status == RunStatus.CANCELLED
