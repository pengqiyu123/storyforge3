from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from storyforge3.export.epub_format import write_epub_book
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.export.markdown import format_markdown_book, format_markdown_chapter
from storyforge3.export.qidian import format_qidian_book, format_qidian_chapter, with_utf8_bom
from storyforge3.models import ChapterStatus
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.storage import BookStorage, StoragePaths

SUPPORTED_EXPORT_FORMATS = {"tomato_txt", "tomato", "txt", "md", "epub", "qidian_txt"}


@dataclass(frozen=True)
class ChapterExportItem:
    chapter_no: int
    text: str


class ExportService:
    def __init__(self, storage: BookStorage, paths: StoragePaths) -> None:
        self.storage = storage
        self.paths = paths
        self.formatter = PlatformFormatter()

    async def export_chapter(self, book_id: str, chapter_no: int, fmt: str = "tomato_txt") -> Path:
        fmt = self._normalize_format(fmt)
        text = self.storage.read_text(self.paths.chapter_file(book_id, chapter_no))
        if text is None:
            raise FileNotFoundError(f"chapter not found: {book_id} {chapter_no}")
        if fmt in {"tomato_txt", "tomato", "txt"}:
            path = self.paths.export_file(book_id, chapter_no, fmt)
            self.storage.write_text(path, self.formatter.format_chapter(f"第{chapter_no}章", chapter_no, text))
            return path
        if fmt == "md":
            path = self.paths.export_file(book_id, chapter_no, fmt)
            self.storage.write_text(path, format_markdown_chapter(chapter_no, text))
            return path
        if fmt == "qidian_txt":
            path = self._chapter_qidian_path(book_id, chapter_no)
            self._write_bytes(path, with_utf8_bom(format_qidian_chapter(chapter_no, text)))
            return path
        if fmt == "epub":
            title = self._book_title(book_id)
            path = self.paths.export_file(book_id, chapter_no, fmt)
            return write_epub_book(path, book_id=book_id, title=title, chapters=[(chapter_no, text)])
        raise ValueError(f"unsupported export format: {fmt}")

    async def export_book(self, book_id: str, fmt: str = "tomato_txt", *, approved_only: bool = True) -> Path:
        fmt = self._normalize_format(fmt)
        if not self.paths.book_meta(book_id).is_file():
            raise FileNotFoundError(f"book not found: {book_id}")
        chapters = self._load_chapters(book_id, approved_only=approved_only)
        title = self._book_title(book_id)
        if fmt in {"tomato_txt", "tomato", "txt"}:
            path = self._book_txt_path(book_id, suffix="tomato")
            text = "\n\n".join(self.formatter.format_chapter(f"第{chapter_no}章", chapter_no, body) for chapter_no, body in chapters)
            self.storage.write_text(path, text)
            return path
        if fmt == "md":
            path = self.paths.book_dir(book_id) / "exports" / f"{book_id}.md"
            self.storage.write_text(path, format_markdown_book(title, chapters))
            return path
        if fmt == "qidian_txt":
            path = self._book_txt_path(book_id, suffix="qidian")
            self._write_bytes(path, with_utf8_bom(format_qidian_book(chapters)))
            return path
        if fmt == "epub":
            path = self.paths.book_dir(book_id) / "exports" / f"{book_id}.epub"
            return write_epub_book(path, book_id=book_id, title=title, chapters=chapters)
        raise ValueError(f"unsupported export format: {fmt}")

    @staticmethod
    def _normalize_format(fmt: str) -> str:
        normalized = fmt.strip().lower()
        if normalized not in SUPPORTED_EXPORT_FORMATS:
            raise ValueError(f"unsupported export format: {fmt}")
        return normalized

    def _book_title(self, book_id: str) -> str:
        data = self.storage.read_json(self.paths.book_meta(book_id)) or {}
        title = str(data.get("title") or "").strip()
        return title or book_id

    def _load_chapters(self, book_id: str, *, approved_only: bool) -> list[tuple[int, str]]:
        chapter_dir = self.paths.book_dir(book_id) / "chapters"
        if not chapter_dir.exists():
            return []
        machine = ChapterStateMachine(self.paths.chapter_states(book_id))
        chapters: list[tuple[int, str]] = []
        for path in sorted(chapter_dir.glob("*.md")):
            chapter_no = self._chapter_no_from_path(path)
            if chapter_no is None:
                continue
            if approved_only and machine.current_status(book_id, chapter_no) not in {ChapterStatus.TRUTH_COMMITTED, ChapterStatus.EXPORTED}:
                continue
            text = self.storage.read_text(path)
            if text is not None:
                chapters.append((chapter_no, text))
        return chapters

    @staticmethod
    def _chapter_no_from_path(path: Path) -> int | None:
        try:
            return int(path.stem.split("-")[0])
        except ValueError:
            return None

    def _chapter_qidian_path(self, book_id: str, chapter_no: int) -> Path:
        return self.paths.book_dir(book_id) / "exports" / f"chapter-{chapter_no:04d}-qidian.txt"

    def _book_txt_path(self, book_id: str, *, suffix: str) -> Path:
        return self.paths.book_dir(book_id) / "exports" / f"{book_id}-{suffix}.txt"

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
