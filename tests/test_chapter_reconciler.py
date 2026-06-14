from __future__ import annotations

import json
from pathlib import Path

from storyforge3.models import ChapterStatus
from storyforge3.services.chapter_reconciler import ChapterReconciler
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.storage import BookStorage, StoragePaths


def test_reconciler_marks_consistent_and_ghost_chapters(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    storage = BookStorage(paths.books_root)
    root = paths.book_dir("book")
    _write_text(root, 1)
    _write_plan(root, 1)
    _write_truth(root, 1)
    _write_export(root, 1)
    _advance(paths, "book", 1, ChapterStatus.EXPORTED)
    _write_legacy_run(root, 1)

    _write_text(root, 2)
    _write_plan(root, 2)
    _write_truth(root, 2)
    _advance(paths, "book", 2, ChapterStatus.APPROVED)

    _write_truth(root, 3)
    _write_export(root, 3)
    _write_legacy_run(root, 3)

    result = ChapterReconciler(storage, paths).reconcile("book")

    assert result.max_chapter == 3
    assert result.inconsistent_count == 1
    by_chapter = {item.chapter_no: item for item in result.chapters}
    assert by_chapter[1].status == "consistent"
    assert by_chapter[1].has_run is True
    assert by_chapter[2].status == "consistent"
    assert by_chapter[2].has_export is False
    assert by_chapter[2].state_status == "approved"
    assert by_chapter[3].status == "inconsistent"
    assert by_chapter[3].inconsistent_reasons == (
        "export_without_state",
        "export_without_text",
        "truth_without_state",
    )


def test_reconciler_detects_each_inconsistent_rule(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    storage = BookStorage(paths.books_root)
    root = paths.book_dir("book")
    _write_export(root, 1)
    _write_text(root, 2)
    _write_truth(root, 2)
    _write_export(root, 2)
    _advance(paths, "book", 2, ChapterStatus.TRUTH_COMMITTED)
    _write_plan(root, 3)
    _advance(paths, "book", 3, ChapterStatus.APPROVED)

    result = ChapterReconciler(storage, paths).reconcile("book")

    by_chapter = {item.chapter_no: item for item in result.chapters}
    assert by_chapter[1].inconsistent_reasons == ("export_without_state", "export_without_text")
    assert by_chapter[2].status == "consistent"
    assert by_chapter[3].inconsistent_reasons == ("orphan_state",)


def test_reconciler_ignores_export_temp_and_sidecar_files(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)
    root = paths.book_dir("book")
    _write_book_artifact(root, "exports", "chapter-0001.txt.tmp", "partial")
    _write_book_artifact(root, "exports", "chapter-0002.meta.json", "{}")
    _write_export(root, 3)

    result = ChapterReconciler(BookStorage(paths.books_root), paths).reconcile("book")

    assert result.max_chapter == 3
    by_chapter = {item.chapter_no: item for item in result.chapters}
    assert by_chapter[1].has_export is False
    assert by_chapter[2].has_export is False
    assert by_chapter[3].has_export is True


def test_reconciler_returns_empty_for_book_without_artifacts(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path)

    result = ChapterReconciler(BookStorage(paths.books_root), paths).reconcile("missing")

    assert result.book_id == "missing"
    assert result.max_chapter == 0
    assert result.inconsistent_count == 0
    assert result.chapters == ()


def _write_text(root: Path, chapter_no: int) -> None:
    path = root / "chapters" / f"{chapter_no:04d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"第{chapter_no}章正文", encoding="utf-8")


def _write_plan(root: Path, chapter_no: int) -> None:
    path = root / "plans" / f"{chapter_no:04d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chapter_no": chapter_no}, ensure_ascii=False), encoding="utf-8")


def _write_truth(root: Path, chapter_no: int) -> None:
    path = root / "truth" / f"chapter-{chapter_no:04d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chapter_no": chapter_no}, ensure_ascii=False), encoding="utf-8")


def _write_export(root: Path, chapter_no: int) -> None:
    path = root / "exports" / f"chapter-{chapter_no:04d}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"第{chapter_no}章导出", encoding="utf-8")


def _write_book_artifact(root: Path, subdir: str, name: str, content: str) -> None:
    path = root / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_legacy_run(root: Path, chapter_no: int) -> None:
    path = root / "runs" / "pipeline.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"book_id": "book", "chapter_no": chapter_no, "task": "run"}, ensure_ascii=False) + "\n")


def _advance(paths: StoragePaths, book_id: str, chapter_no: int, status: ChapterStatus) -> None:
    machine = ChapterStateMachine(paths.chapter_states(book_id))
    for next_status in (
        ChapterStatus.PLANNED,
        ChapterStatus.DRAFTED,
        ChapterStatus.AUDITED,
        ChapterStatus.APPROVED,
        ChapterStatus.TRUTH_COMMITTED,
        ChapterStatus.EXPORTED,
    ):
        machine.advance(book_id, chapter_no, next_status)
        if next_status == status:
            return
