from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from storyforge3.models import BookConfig, BookMeta, BookStatus
from storyforge3.storage import BookStorage, StoragePaths


PINYIN_INITIALS = {
    "我": "w",
    "是": "s",
    "路": "l",
    "人": "r",
    "甲": "j",
    "测": "c",
    "试": "s",
    "书": "s",
}


class BookService:
    def __init__(self, storage: BookStorage, paths: StoragePaths) -> None:
        self.storage = storage
        self.paths = paths

    async def create(self, config: BookConfig) -> BookMeta:
        now = datetime.now(timezone.utc).isoformat()
        meta = BookMeta(
            book_id=self._make_book_id(config.title),
            title=config.title,
            genre=config.genre,
            platform=config.platform,
            status=BookStatus.INCUBATING,
            target_chapters=config.target_chapters,
            chapter_word_count=config.chapter_word_count,
            language=config.language,
            fanfic_mode=config.fanfic_mode,
            created_at=now,
            updated_at=now,
        )
        self._init_dirs(meta.book_id)
        self.storage.write_json(self.paths.book_meta(meta.book_id), self._dump_meta(meta))
        self.storage.write_text(self.paths.context(meta.book_id), "")
        return meta

    async def get(self, book_id: str) -> BookMeta | None:
        data = self.storage.read_json(self.paths.book_meta(book_id))
        return self._load_meta(data) if data else None

    async def list_books(self) -> list[BookMeta]:
        books = [await self.get(book_id) for book_id in self.storage.list_book_ids()]
        return [book for book in books if book is not None]

    async def update_status(self, book_id: str, status: str) -> BookMeta:
        meta = await self.get(book_id)
        if meta is None:
            raise FileNotFoundError(f"book not found: {book_id}")
        new_status = BookStatus(status)
        updated = BookMeta(**{**asdict(meta), "status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()})
        self.storage.write_json(self.paths.book_meta(book_id), self._dump_meta(updated))
        return updated

    def _init_dirs(self, book_id: str) -> None:
        for name in ("chapters", "truth", "exports", "state"):
            self.storage.ensure_dir(self.paths.book_dir(book_id) / name)

    @staticmethod
    def _make_book_id(title: str) -> str:
        initials = "".join(PINYIN_INITIALS.get(char, char.lower()) for char in title if char.strip())
        safe = "".join(char for char in initials if char.isalnum()) or "book"
        return f"{safe}_{datetime.now(timezone.utc):%Y%m%d}"

    @staticmethod
    def _dump_meta(meta: BookMeta) -> dict:
        data = asdict(meta)
        data["status"] = meta.status.value
        return data

    @staticmethod
    def _load_meta(data: dict) -> BookMeta:
        return BookMeta(**{**data, "status": BookStatus(data["status"])})
