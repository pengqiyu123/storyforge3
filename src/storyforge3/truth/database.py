from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class TruthEntry:
    id: int | None
    book_id: str
    chapter_no: int
    category: str
    content: str
    importance: float = 0.5
    related_chapters: tuple[int, ...] = ()
    created_at: str = ""


class TruthDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def insert_entries(self, book_id: str, chapter_no: int, entries: list[TruthEntry]) -> None:
        if not entries:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO truth_entries
                    (book_id, chapter_no, category, content, importance, chapter_ids, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        book_id,
                        chapter_no,
                        entry.category,
                        entry.content,
                        self._clamp_importance(entry.importance),
                        self._chapter_ids(entry.related_chapters),
                        entry.created_at or now,
                    )
                    for entry in entries
                    if entry.content.strip()
                ],
            )

    def query_relevant(
        self,
        book_id: str,
        query_context: str,
        *,
        limit: int = 20,
        min_importance: float = 0.3,
    ) -> list[TruthEntry]:
        keywords = self._keywords(query_context)[:500]
        candidates = self._query_candidates(book_id, min_importance, keywords)
        latest_chapter = self._latest_chapter(book_id)
        ranked = sorted(
            candidates,
            key=lambda entry: self._score(entry, latest_chapter),
            reverse=True,
        )
        return ranked[:limit]

    def query_by_chapter(self, book_id: str, chapter_no: int) -> list[TruthEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, book_id, chapter_no, category, content, importance, chapter_ids, created_at
                FROM truth_entries
                WHERE book_id = ? AND chapter_no = ?
                ORDER BY id ASC
                """,
                (book_id, chapter_no),
            ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def query_by_book(self, book_id: str) -> list[TruthEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, book_id, chapter_no, category, content, importance, chapter_ids, created_at
                FROM truth_entries
                WHERE book_id = ?
                ORDER BY chapter_no ASC, id ASC
                """,
                (book_id,),
            ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def query_recent(self, book_id: str, last_n_chapters: int = 5) -> list[TruthEntry]:
        with self._connect() as conn:
            max_chapter = conn.execute(
                "SELECT MAX(chapter_no) FROM truth_entries WHERE book_id = ?",
                (book_id,),
            ).fetchone()[0]
        if max_chapter is None:
            return []
        start = max(1, int(max_chapter) - last_n_chapters + 1)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, book_id, chapter_no, category, content, importance, chapter_ids, created_at
                FROM truth_entries
                WHERE book_id = ? AND chapter_no >= ?
                ORDER BY chapter_no ASC, id ASC
                """,
                (book_id, start),
            ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def query_high_importance(self, book_id: str, *, limit: int = 20, min_importance: float = 0.8) -> list[TruthEntry]:
        latest_chapter = self._latest_chapter(book_id)
        candidates = self._query_candidates(book_id, min_importance, [])
        ranked = sorted(
            candidates,
            key=lambda entry: self._score(entry, latest_chapter),
            reverse=True,
        )
        return ranked[:limit]

    def delete_chapter(self, book_id: str, chapter_no: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM truth_entries WHERE book_id = ? AND chapter_no = ?",
                (book_id, chapter_no),
            )
            return int(cursor.rowcount or 0)

    def delete_book(self, book_id: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM truth_entries WHERE book_id = ?",
                (book_id,),
            )
            return int(cursor.rowcount or 0)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS truth_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,
                    chapter_no INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    chapter_ids TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_truth_book_chapter ON truth_entries(book_id, chapter_no)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_truth_book_category ON truth_entries(book_id, category)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _query_candidates(self, book_id: str, min_importance: float, keywords: list[str]) -> list[TruthEntry]:
        sql = """
            SELECT id, book_id, chapter_no, category, content, importance, chapter_ids, created_at
            FROM truth_entries
            WHERE book_id = ? AND importance >= ?
            """
        params: list[str | float] = [book_id, min_importance]
        if keywords:
            like_clauses = " OR ".join("content LIKE ?" for _ in keywords)
            sql = f"{sql} AND ({like_clauses})"
            params.extend(f"%{keyword}%" for keyword in keywords)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def _latest_chapter(self, book_id: str) -> int:
        with self._connect() as conn:
            value = conn.execute(
                "SELECT MAX(chapter_no) FROM truth_entries WHERE book_id = ?",
                (book_id,),
            ).fetchone()[0]
        return int(value or 0)

    @staticmethod
    def _score(entry: TruthEntry, latest_chapter: int) -> float:
        category_weight = {
            "character_event": 2.0,
            "plot_point": 1.7,
            "relationship": 1.5,
            "ability": 1.4,
            "world_rule": 1.0,
        }.get(entry.category, 1.0)
        recent_bonus = 0.1 if latest_chapter and entry.chapter_no >= max(1, latest_chapter - 4) else 0.0
        return (entry.importance + recent_bonus) * category_weight

    @staticmethod
    def _keywords(query_context: str) -> list[str]:
        chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", query_context)
        keywords: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            if value not in seen:
                seen.add(value)
                keywords.append(value)

        for run in chinese_runs:
            if 2 <= len(run) <= 8:
                add(run)
            for size in range(min(4, len(run)), 1, -1):
                for index in range(0, len(run) - size + 1):
                    add(run[index : index + size])
        return keywords

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> TruthEntry:
        return TruthEntry(
            id=int(row["id"]),
            book_id=str(row["book_id"]),
            chapter_no=int(row["chapter_no"]),
            category=str(row["category"]),
            content=str(row["content"]),
            importance=float(row["importance"]),
            related_chapters=TruthDatabase._parse_chapter_ids(str(row["chapter_ids"] or "")),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _chapter_ids(values: tuple[int, ...]) -> str:
        return ",".join(str(value) for value in values)

    @staticmethod
    def _parse_chapter_ids(value: str) -> tuple[int, ...]:
        if not value:
            return ()
        return tuple(int(part) for part in value.split(",") if part.strip().isdigit())

    @staticmethod
    def _clamp_importance(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
