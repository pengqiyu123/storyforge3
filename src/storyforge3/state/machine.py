from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from storyforge3.models import ChapterStatus


class InvalidTransitionError(RuntimeError):
    pass


TRANSITIONS = {
    ChapterStatus.EMPTY: {ChapterStatus.PLANNED},
    ChapterStatus.PLANNED: {ChapterStatus.DRAFTED, ChapterStatus.NEEDS_REVIEW},
    ChapterStatus.DRAFTED: {ChapterStatus.AUDITED, ChapterStatus.NEEDS_REVIEW},
    ChapterStatus.AUDITED: {ChapterStatus.APPROVED, ChapterStatus.NEEDS_REVISION, ChapterStatus.NEEDS_REVIEW},
    ChapterStatus.NEEDS_REVISION: {ChapterStatus.REVISED, ChapterStatus.NEEDS_REVIEW},
    ChapterStatus.REVISED: {ChapterStatus.AUDITED, ChapterStatus.NEEDS_REVIEW},
    ChapterStatus.APPROVED: {ChapterStatus.EXPORTED},
    ChapterStatus.EXPORTED: set(),
    ChapterStatus.NEEDS_REVIEW: {ChapterStatus.PLANNED, ChapterStatus.DRAFTED, ChapterStatus.EMPTY},
}


class ChapterStateMachine:
    def __init__(self, store_path: Path) -> None:
        self.store_path = Path(store_path)

    def current_status(self, book_id: str, chapter_no: int) -> ChapterStatus:
        data = self._load()
        key = self._key(book_id, chapter_no)
        return ChapterStatus(data.get(key, {}).get("status", ChapterStatus.EMPTY.value))

    def advance(self, book_id: str, chapter_no: int, to: ChapterStatus) -> None:
        current = self.current_status(book_id, chapter_no)
        if to not in TRANSITIONS[current]:
            raise InvalidTransitionError(f"invalid transition {current.value} -> {to.value}")
        data = self._load()
        key = self._key(book_id, chapter_no)
        record = data.setdefault(key, {"status": ChapterStatus.EMPTY.value, "history": []})
        record["status"] = to.value
        record["history"].append({"from": current.value, "to": to.value, "at": datetime.now(timezone.utc).isoformat()})
        self._save(data)

    def force_needs_review(self, book_id: str, chapter_no: int, reason: str) -> None:
        data = self._load()
        key = self._key(book_id, chapter_no)
        current = data.get(key, {}).get("status", ChapterStatus.EMPTY.value)
        record = data.setdefault(key, {"status": current, "history": []})
        record["status"] = ChapterStatus.NEEDS_REVIEW.value
        record["history"].append({"from": current, "to": "needs_review", "reason": reason, "at": datetime.now(timezone.utc).isoformat()})
        self._save(data)

    def history(self, book_id: str, chapter_no: int) -> list[dict]:
        return list(self._load().get(self._key(book_id, chapter_no), {}).get("history", []))

    def _load(self) -> dict:
        if not self.store_path.exists():
            return {}
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _key(book_id: str, chapter_no: int) -> str:
        return f"{book_id}:{chapter_no:04d}"
