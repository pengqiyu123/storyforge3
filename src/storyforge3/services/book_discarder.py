from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from storyforge3.models import BookMeta, BookStatus
from storyforge3.services.book_service import BookService
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.database import TruthEntry
from storyforge3.truth.store import TruthStore


class BookDiscardSafetyError(RuntimeError):
    pass


class RestoreConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class BookDiscardPreview:
    book_id: str
    files: tuple[str, ...]
    file_count: int
    size_bytes: int
    truth_db_rows: int
    backed_up_to: str | None


@dataclass(frozen=True)
class BookDiscardResult:
    book_id: str
    backup_id: str | None
    backed_up_to: str | None
    files: tuple[str, ...]
    file_count: int
    size_bytes: int
    truth_db_rows: int


class BookDiscarder:
    """Book-level discard with a mandatory trash backup before removal."""

    def __init__(
        self,
        storage: BookStorage,
        paths: StoragePaths,
        *,
        truth_store: TruthStore | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.storage = storage
        self.paths = paths
        self.truth_store = truth_store or TruthStore(str(paths.books_root))
        self._now = now or (lambda: datetime.now(timezone.utc))

    def preview(self, book_id: str) -> BookDiscardPreview:
        plan = self._plan(book_id, validate_safety=False)
        backup_dir = self._next_backup_dir(book_id) if plan.has_work else None
        return BookDiscardPreview(
            book_id=book_id,
            files=plan.files,
            file_count=len(plan.files),
            size_bytes=plan.size_bytes,
            truth_db_rows=len(plan.truth_rows),
            backed_up_to=str(backup_dir) if backup_dir is not None else None,
        )

    def discard(self, book_id: str) -> BookDiscardResult:
        plan = self._plan(book_id, validate_safety=True)
        backup_dir = self._next_backup_dir(book_id) if plan.has_work else None
        backup_id = backup_dir.name if backup_dir is not None else None
        if backup_dir is not None:
            self._backup(plan, backup_dir)
            self.truth_store.delete_by_book(book_id)
            shutil.rmtree(plan.book_dir)
        return BookDiscardResult(
            book_id=book_id,
            backup_id=backup_id,
            backed_up_to=str(backup_dir) if backup_dir is not None else None,
            files=plan.files,
            file_count=len(plan.files),
            size_bytes=plan.size_bytes,
            truth_db_rows=len(plan.truth_rows),
        )

    def restore(self, book_id: str, backup_id: str) -> BookMeta:
        backup_dir = self._backup_dir(backup_id)
        return self._restore_from_dir(book_id, backup_id, backup_dir)

    def restore_backup(self, backup_id: str) -> BookMeta:
        backup_dir = self._backup_dir(backup_id)
        book_id = self._book_id_from_backup(backup_dir)
        return self._restore_from_dir(book_id, backup_id, backup_dir)

    def _backup_dir(self, backup_id: str) -> Path:
        if not _safe_backup_id(backup_id):
            raise ValueError(f"Invalid backup id: {backup_id}")
        backup_dir = self.paths.books_root / "_trash" / backup_id
        if not backup_dir.is_dir():
            raise FileNotFoundError(f"book backup not found: {backup_id}")
        return backup_dir

    def _restore_from_dir(self, book_id: str, backup_id: str, backup_dir: Path) -> BookMeta:
        target_dir = self.paths.book_dir(book_id)
        if target_dir.exists():
            raise RestoreConflictError(f"book already exists: {book_id}")
        source_book_id = self._book_id_from_backup(backup_dir)
        if source_book_id != book_id:
            raise ValueError(f"backup {backup_id} belongs to {source_book_id}, not {book_id}")
        shutil.copytree(backup_dir, target_dir, ignore=shutil.ignore_patterns("truth_db_rows.json"))
        self._restore_truth_rows(backup_dir)
        meta = BookService(self.storage, self.paths)._load_meta(self.storage.read_json(self.paths.book_meta(book_id)) or {})
        return meta

    def _plan(self, book_id: str, *, validate_safety: bool) -> "_BookDiscardPlan":
        book_dir = self.paths.book_dir(book_id)
        if not (book_dir / "book.json").is_file():
            raise FileNotFoundError(f"book not found: {book_id}")
        meta = BookService(self.storage, self.paths)._load_meta(self.storage.read_json(self.paths.book_meta(book_id)) or {})
        if validate_safety:
            self._validate_safety(book_id, meta)
        files = tuple(_relative(path, book_dir) for path in _book_files(book_dir))
        size_bytes = sum((book_dir / relative).stat().st_size for relative in files)
        truth_rows = tuple(self.truth_store.database.query_by_book(book_id))
        return _BookDiscardPlan(
            book_id=book_id,
            book_dir=book_dir,
            meta=meta,
            files=files,
            size_bytes=size_bytes,
            truth_rows=truth_rows,
        )

    def _validate_safety(self, book_id: str, meta: BookMeta) -> None:
        if meta.status != BookStatus.ACTIVE:
            return
        active_statuses = {
            "planned",
            "drafted",
            "settled",
            "audited",
            "needs_revision",
            "revised",
            "approved",
            "truth_committed",
            "needs_review",
        }
        state_path = self.paths.chapter_states(book_id)
        state = _read_json_object(state_path)
        blocking = sorted(
            key
            for key, value in state.items()
            if isinstance(value, dict) and key.startswith(f"{book_id}:") and str(value.get("status", "")) in active_statuses
        )
        if blocking:
            raise BookDiscardSafetyError(f"active book has unfinished chapters: {', '.join(blocking)}")

    def _next_backup_dir(self, book_id: str) -> Path:
        root = self.paths.books_root / "_trash"
        stamp = self._now().astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"{book_id}_{stamp}"
        index = 0
        while True:
            suffix = "" if index == 0 else f"_{index:03d}"
            candidate = root / f"{base}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def _backup(self, plan: "_BookDiscardPlan", backup_dir: Path) -> None:
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plan.book_dir, backup_dir)
        if plan.truth_rows:
            _write_json(backup_dir / "truth_db_rows.json", [_truth_entry_to_dict(row) for row in plan.truth_rows])

    def _book_id_from_backup(self, backup_dir: Path) -> str:
        data = self.storage.read_json(backup_dir / "book.json")
        if not data:
            raise FileNotFoundError(f"book backup has no book.json: {backup_dir.name}")
        return str(data.get("book_id") or "")

    def _restore_truth_rows(self, backup_dir: Path) -> None:
        rows_path = backup_dir / "truth_db_rows.json"
        if not rows_path.is_file():
            return
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            return
        entries = [_truth_entry_from_dict(item) for item in rows if isinstance(item, dict)]
        if not entries:
            return
        book_id = entries[0].book_id
        self.truth_store.delete_by_book(book_id)
        chapters = sorted({entry.chapter_no for entry in entries})
        for chapter_no in chapters:
            self.truth_store.database.insert_entries(book_id, chapter_no, [entry for entry in entries if entry.chapter_no == chapter_no])


@dataclass(frozen=True)
class _BookDiscardPlan:
    book_id: str
    book_dir: Path
    meta: BookMeta
    files: tuple[str, ...]
    size_bytes: int
    truth_rows: tuple[TruthEntry, ...]

    @property
    def has_work(self) -> bool:
        return bool(self.files or self.truth_rows)


def _book_files(book_dir: Path) -> list[Path]:
    return sorted(path for path in book_dir.rglob("*") if path.is_file())


def _safe_backup_id(backup_id: str) -> bool:
    return bool(backup_id) and "/" not in backup_id and "\\" not in backup_id and ".." not in backup_id


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _truth_entry_to_dict(entry: TruthEntry) -> dict:
    return {
        "id": entry.id,
        "book_id": entry.book_id,
        "chapter_no": entry.chapter_no,
        "category": entry.category,
        "content": entry.content,
        "importance": entry.importance,
        "related_chapters": list(entry.related_chapters),
        "created_at": entry.created_at,
    }


def _truth_entry_from_dict(data: dict) -> TruthEntry:
    return TruthEntry(
        id=None,
        book_id=str(data.get("book_id", "")),
        chapter_no=int(data.get("chapter_no", 0)),
        category=str(data.get("category", "")),
        content=str(data.get("content", "")),
        importance=float(data.get("importance", 0.5)),
        related_chapters=tuple(int(value) for value in data.get("related_chapters", ()) if str(value).isdigit()),
        created_at=str(data.get("created_at", "")),
    )


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
