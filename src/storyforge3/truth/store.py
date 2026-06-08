from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from storyforge3.models import TruthData
from storyforge3.truth.database import TruthDatabase, TruthEntry


class TruthStore:
    """JSON file storage for truth data."""

    def __init__(self, books_dir: str) -> None:
        self.books_dir = Path(books_dir)
        self.database = TruthDatabase(self.books_dir / "truth.db")

    def save(self, book_id: str, truth: TruthData) -> Path:
        path = self._path(book_id, truth.chapter_no)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(truth), ensure_ascii=False, indent=2), encoding="utf-8")
        self.save_to_database(book_id, truth.chapter_no, self._entries_from_truth(book_id, truth))
        return path

    def save_to_database(self, book_id: str, chapter_no: int, entries: list[TruthEntry]) -> None:
        self.database.delete_chapter(book_id, chapter_no)
        self.database.insert_entries(book_id, chapter_no, entries)

    def load(self, book_id: str, chapter_no: int) -> TruthData | None:
        path = self._path(book_id, chapter_no)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TruthData(
            chapter_no=int(data["chapter_no"]),
            source=str(data["source"]),
            fact_assertions=tuple(data.get("fact_assertions", ())),
            character_updates=tuple(data.get("character_updates", ())),
            relationship_updates=tuple(data.get("relationship_updates", ())),
            hook_updates=tuple(data.get("hook_updates", ())),
            irreversible_facts=tuple(data.get("irreversible_facts", ())),
            notes=tuple(data.get("notes", ())),
        )

    def load_latest(self, book_id: str) -> TruthData | None:
        truth_dir = self.books_dir / book_id / "truth"
        paths = sorted(truth_dir.glob("chapter-*.json"))
        if not paths:
            return None
        chapter_no = int(paths[-1].stem.split("-")[-1])
        return self.load(book_id, chapter_no)

    def detect_gaps(self, book_id: str, up_to_chapter: int) -> list[int]:
        return [chapter_no for chapter_no in range(1, up_to_chapter + 1) if self.load(book_id, chapter_no) is None]

    def _path(self, book_id: str, chapter_no: int) -> Path:
        return self.books_dir / book_id / "truth" / f"chapter-{chapter_no:04d}.json"

    @staticmethod
    def _entries_from_truth(book_id: str, truth: TruthData) -> list[TruthEntry]:
        entries: list[TruthEntry] = []
        entries.extend(TruthStore._text_entries(book_id, truth.chapter_no, "plot_point", truth.fact_assertions, 0.7))
        entries.extend(TruthStore._dict_entries(book_id, truth.chapter_no, "character_event", truth.character_updates, 0.65))
        entries.extend(TruthStore._dict_entries(book_id, truth.chapter_no, "relationship", truth.relationship_updates, 0.6))
        entries.extend(TruthStore._dict_entries(book_id, truth.chapter_no, "plot_point", truth.hook_updates, 0.6))
        entries.extend(TruthStore._text_entries(book_id, truth.chapter_no, "world_rule", truth.irreversible_facts, 0.9))
        entries.extend(TruthStore._text_entries(book_id, truth.chapter_no, "plot_point", truth.notes, 0.4))
        return entries

    @staticmethod
    def _text_entries(
        book_id: str,
        chapter_no: int,
        category: str,
        values: tuple[str, ...],
        importance: float,
    ) -> list[TruthEntry]:
        return [
            TruthEntry(None, book_id, chapter_no, category, str(value), importance, (), "")
            for value in values
            if str(value).strip()
        ]

    @staticmethod
    def _dict_entries(
        book_id: str,
        chapter_no: int,
        category: str,
        values: tuple[dict, ...],
        importance: float,
    ) -> list[TruthEntry]:
        entries: list[TruthEntry] = []
        for value in values:
            text = str(value.get("summary") or value.get("description") or value.get("content") or value)
            if text.strip():
                entries.append(TruthEntry(None, book_id, chapter_no, category, text, importance, (), ""))
        return entries
