from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from storyforge3.models import ChapterStatus
from storyforge3.storage import BookStorage, StoragePaths


@dataclass(frozen=True)
class ChapterConsistency:
    chapter_no: int
    has_text: bool
    has_plan: bool
    has_truth: bool
    has_export: bool
    has_state: bool
    has_run: bool
    state_status: str | None
    status: str
    inconsistent_reasons: tuple[str, ...]


@dataclass(frozen=True)
class BookReconciliation:
    book_id: str
    chapters: tuple[ChapterConsistency, ...]
    inconsistent_count: int
    max_chapter: int


class ChapterReconciler:
    """Read-only chapter artifact consistency scanner."""

    def __init__(self, storage: BookStorage, paths: StoragePaths) -> None:
        self.storage = storage
        self.paths = paths

    def reconcile(self, book_id: str) -> BookReconciliation:
        book_dir = self.paths.book_dir(book_id)
        text_chapters = _numbered_files(book_dir / "chapters", "*.md")
        plan_chapters = _numbered_files(book_dir / "plans", "*.json")
        truth_chapters = _chapter_prefixed_files(book_dir / "truth", "*.json")
        export_chapters = _export_chapter_files(book_dir / "exports")
        state_statuses = self._state_statuses(book_id)
        run_chapters = self._new_run_chapters(book_id) | self._legacy_run_chapters(book_id)
        all_chapters = text_chapters | plan_chapters | truth_chapters | export_chapters | set(state_statuses) | run_chapters
        if not all_chapters:
            return BookReconciliation(book_id=book_id, chapters=(), inconsistent_count=0, max_chapter=0)

        max_chapter = max(all_chapters)
        chapters = tuple(
            self._chapter_consistency(
                chapter_no,
                text_chapters=text_chapters,
                plan_chapters=plan_chapters,
                truth_chapters=truth_chapters,
                export_chapters=export_chapters,
                state_statuses=state_statuses,
                run_chapters=run_chapters,
            )
            for chapter_no in range(1, max_chapter + 1)
        )
        return BookReconciliation(
            book_id=book_id,
            chapters=chapters,
            inconsistent_count=sum(1 for chapter in chapters if chapter.status == "inconsistent"),
            max_chapter=max_chapter,
        )

    def _chapter_consistency(
        self,
        chapter_no: int,
        *,
        text_chapters: set[int],
        plan_chapters: set[int],
        truth_chapters: set[int],
        export_chapters: set[int],
        state_statuses: dict[int, str],
        run_chapters: set[int],
    ) -> ChapterConsistency:
        has_text = chapter_no in text_chapters
        has_truth = chapter_no in truth_chapters
        has_export = chapter_no in export_chapters
        state_status = state_statuses.get(chapter_no)
        has_state = state_status is not None
        reasons = _inconsistent_reasons(
            has_text=has_text,
            has_truth=has_truth,
            has_export=has_export,
            has_state=has_state,
            state_status=state_status,
        )
        return ChapterConsistency(
            chapter_no=chapter_no,
            has_text=has_text,
            has_plan=chapter_no in plan_chapters,
            has_truth=has_truth,
            has_export=has_export,
            has_state=has_state,
            has_run=chapter_no in run_chapters,
            state_status=state_status,
            status="inconsistent" if reasons else "consistent",
            inconsistent_reasons=reasons,
        )

    def _state_statuses(self, book_id: str) -> dict[int, str]:
        data = self.storage.read_json(self.paths.chapter_states(book_id)) or {}
        statuses: dict[int, str] = {}
        prefix = f"{book_id}:"
        for key, record in data.items():
            if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(record, dict):
                continue
            try:
                chapter_no = int(key.removeprefix(prefix))
            except ValueError:
                continue
            status = record.get("status")
            if isinstance(status, str) and status:
                statuses[chapter_no] = status
        return statuses

    def _new_run_chapters(self, book_id: str) -> set[int]:
        chapters: set[int] = set()
        chapter_root = self.paths.book_dir(book_id) / "chapters"
        if not chapter_root.exists():
            return chapters
        for path in sorted(chapter_root.glob("*/runs/*.json")):
            if path.name == "current_run.json":
                continue
            try:
                chapters.add(int(path.parent.parent.name))
            except ValueError:
                continue
        return chapters

    def _legacy_run_chapters(self, book_id: str) -> set[int]:
        path = self.paths.book_dir(book_id) / "runs" / "pipeline.jsonl"
        if not path.is_file():
            return set()
        chapters: set[int] = set()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return chapters
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("book_id") != book_id:
                continue
            try:
                chapters.add(int(data.get("chapter_no")))
            except (TypeError, ValueError):
                continue
        return chapters


def _inconsistent_reasons(
    *,
    has_text: bool,
    has_truth: bool,
    has_export: bool,
    has_state: bool,
    state_status: str | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if has_export and not has_state:
        reasons.append("export_without_state")
    if has_export and not has_text:
        reasons.append("export_without_text")
    if has_truth and not has_state:
        reasons.append("truth_without_state")
    if has_state and not has_text and state_status in _ORPHAN_STATE_STATUSES:
        reasons.append("orphan_state")
    return tuple(reasons)


def _numbered_files(root: Path, pattern: str) -> set[int]:
    if not root.exists():
        return set()
    chapters: set[int] = set()
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        try:
            chapters.add(int(path.stem))
        except ValueError:
            continue
    return chapters


def _chapter_prefixed_files(root: Path, pattern: str) -> set[int]:
    if not root.exists():
        return set()
    chapters: set[int] = set()
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        chapter_no = _chapter_no_from_prefixed_name(path)
        if chapter_no is not None:
            chapters.add(chapter_no)
    return chapters


def _export_chapter_files(root: Path) -> set[int]:
    if not root.exists():
        return set()
    chapters: set[int] = set()
    for path in sorted(root.glob("chapter-*")):
        if not path.is_file() or not _is_chapter_export_file(path):
            continue
        chapter_no = _chapter_no_from_prefixed_name(path)
        if chapter_no is not None:
            chapters.add(chapter_no)
    return chapters


def _is_chapter_export_file(path: Path) -> bool:
    name = path.name
    return (
        name.endswith(".txt")
        or name.endswith(".md")
        or name.endswith(".epub")
    ) and not name.endswith(".tmp")


def _chapter_no_from_prefixed_name(path: Path) -> int | None:
    name = path.name
    if not name.startswith("chapter-"):
        return None
    digits = []
    for char in name[len("chapter-") :]:
        if not char.isdigit():
            break
        digits.append(char)
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


_ORPHAN_STATE_STATUSES = {
    ChapterStatus.APPROVED.value,
    ChapterStatus.TRUTH_COMMITTED.value,
    ChapterStatus.EXPORTED.value,
}
