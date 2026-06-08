from __future__ import annotations

from storyforge3.truth.database import TruthDatabase, TruthEntry


class TruthRetriever:
    def __init__(self, database: TruthDatabase) -> None:
        self.database = database

    def retrieve_for_prompt(
        self,
        book_id: str,
        chapter_no: int,
        prompt_context: str,
        *,
        max_entries: int = 30,
        max_chars: int = 4000,
    ) -> str:
        entries = self._select_entries(book_id, chapter_no, prompt_context, max_entries=max_entries)
        lines: list[str] = []
        used_chars = 0
        for entry in entries:
            line = self._format_entry(entry)
            next_chars = used_chars + len(line) + (1 if lines else 0)
            if next_chars > max_chars:
                break
            lines.append(line)
            used_chars = next_chars
        return "\n".join(lines)

    def _select_entries(
        self,
        book_id: str,
        chapter_no: int,
        prompt_context: str,
        *,
        max_entries: int,
    ) -> list[TruthEntry]:
        selected: list[TruthEntry] = []
        seen: set[tuple[int, str, str]] = set()

        current = self.database.query_by_chapter(book_id, chapter_no)
        self._extend_unique(selected, seen, current)

        recent_start = max(1, chapter_no - 5)
        recent_relevant = [
            entry
            for entry in self.database.query_relevant(book_id, prompt_context, limit=max_entries * 4)
            if recent_start <= entry.chapter_no < chapter_no
        ]
        self._extend_unique(selected, seen, recent_relevant)

        historical_relevant = [
            entry
            for entry in self.database.query_relevant(book_id, prompt_context, limit=max_entries * 4, min_importance=0.8)
            if entry.chapter_no < recent_start or entry.chapter_no > chapter_no
        ]
        self._extend_unique(selected, seen, historical_relevant)

        has_historical_context = bool(recent_relevant or historical_relevant)
        high_importance = [
            entry
            for entry in self.database.query_high_importance(book_id, limit=max_entries * 4, min_importance=0.8)
            if entry.chapter_no < recent_start or entry.chapter_no > chapter_no
        ]
        if not has_historical_context:
            self._extend_unique(selected, seen, high_importance)
        return selected[:max_entries]

    @staticmethod
    def _extend_unique(
        selected: list[TruthEntry],
        seen: set[tuple[int, str, str]],
        entries: list[TruthEntry],
    ) -> None:
        for entry in entries:
            key = (entry.chapter_no, entry.category, entry.content)
            if key in seen:
                continue
            seen.add(key)
            selected.append(entry)

    @staticmethod
    def _format_entry(entry: TruthEntry) -> str:
        return f"[第{entry.chapter_no}章][{entry.category}][{entry.importance:.2f}] {entry.content}"
