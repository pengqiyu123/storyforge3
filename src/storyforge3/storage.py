from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class StoragePaths:
    """Centralized path resolution for book data."""

    books_root: Path

    def book_dir(self, book_id: str) -> Path:
        return self.books_root / book_id

    def book_meta(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "book.json"

    def world_config(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "world.json"

    def characters(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "characters.json"

    def relationships(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "relationships.json"

    def volumes(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "volumes.json"

    def context(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "context.md"

    def chapter_file(self, book_id: str, chapter_no: int) -> Path:
        return self.book_dir(book_id) / "chapters" / f"{chapter_no:04d}.md"

    def chapter_dir(self, book_id: str, chapter_no: int) -> Path:
        return self.book_dir(book_id) / "chapters" / f"{chapter_no:04d}"

    def run_dir(self, book_id: str, chapter_no: int) -> Path:
        return self.chapter_dir(book_id, chapter_no) / "runs"

    def audit_result_file(self, book_id: str, chapter_no: int) -> Path:
        return self.chapter_dir(book_id, chapter_no) / "audit_result.json"

    def run_file(self, book_id: str, chapter_no: int, run_id: str) -> Path:
        return self.run_dir(book_id, chapter_no) / f"{run_id}.json"

    def current_run_file(self, book_id: str, chapter_no: int) -> Path:
        return self.run_dir(book_id, chapter_no) / "current_run.json"

    def plan_file(self, book_id: str, chapter_no: int) -> Path:
        return self.book_dir(book_id) / "plans" / f"{chapter_no:04d}.json"

    def truth_file(self, book_id: str, chapter_no: int) -> Path:
        return self.book_dir(book_id) / "truth" / f"chapter-{chapter_no:04d}.json"

    def export_file(self, book_id: str, chapter_no: int, fmt: str) -> Path:
        extension = "txt" if fmt in {"txt", "tomato", "tomato_txt"} else fmt
        return self.book_dir(book_id) / "exports" / f"chapter-{chapter_no:04d}.{extension}"

    def chapter_states(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "state" / "chapter_states.json"


class BookStorage:
    """JSON and text file I/O for book data."""

    def __init__(self, books_root: Path | str) -> None:
        self.books_root = Path(books_root)

    def read_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: dict) -> None:
        self._atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))

    def read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_text(self, path: Path, text: str) -> None:
        self._atomic_write_text(path, text)

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            BookStorage._replace_with_retry(tmp, path)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _replace_with_retry(tmp: Path, path: Path) -> None:
        attempts = 5
        for attempt in range(attempts):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def list_book_ids(self) -> list[str]:
        if not self.books_root.exists():
            return []
        return sorted(path.name for path in self.books_root.iterdir() if (path / "book.json").is_file())
