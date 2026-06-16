from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from storyforge3.models import TruthData
from storyforge3.services.book_discarder import BookDiscarder, BookDiscardSafetyError, RestoreConflictError
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


def test_book_discarder_preview_is_read_only_and_lists_whole_book(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_book(storage, store, paths, "book-a", status="archived", state_statuses={1: "exported"})

    preview = _discarder(storage, paths, store).preview("book-a")

    assert preview.book_id == "book-a"
    assert preview.file_count >= 7
    assert preview.size_bytes > 0
    assert preview.truth_db_rows == 1
    assert "book.json" in preview.files
    assert "chapters/0001.md" in preview.files
    assert "truth/chapter-0001.json" in preview.files
    assert "exports/chapter-0001.txt" in preview.files
    assert preview.backed_up_to.replace("\\", "/").endswith("_trash/book-a_20260616_010203")
    assert paths.book_meta("book-a").exists()


def test_book_discarder_deletes_after_backup_and_restores(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_book(storage, store, paths, "book-a", status="archived", state_statuses={1: "exported"})
    _seed_book(storage, store, paths, "book-b", status="active", state_statuses={1: "exported"})
    discarder = _discarder(storage, paths, store)

    result = discarder.discard("book-a")

    assert result.book_id == "book-a"
    assert result.backup_id == "book-a_20260616_010203"
    assert result.truth_db_rows == 1
    assert result.file_count >= 7
    assert not paths.book_dir("book-a").exists()
    assert (paths.books_root / "_trash" / result.backup_id / "book.json").exists()
    assert (paths.books_root / "_trash" / result.backup_id / "truth_db_rows.json").exists()
    assert store.database.query_by_chapter("book-a", 1) == []
    assert len(store.database.query_by_chapter("book-b", 1)) == 1

    restored = discarder.restore("book-a", result.backup_id)

    assert restored.book_id == "book-a"
    assert restored.status.value == "archived"
    assert paths.book_meta("book-a").exists()
    assert (paths.book_dir("book-a") / "chapters" / "0001.md").read_text(encoding="utf-8") == "第1章正文"
    assert len(store.database.query_by_chapter("book-a", 1)) == 1


def test_book_discarder_rejects_active_book_with_unfinished_chapter(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_book(storage, store, paths, "book-a", status="active", state_statuses={1: "drafted"})

    with pytest.raises(BookDiscardSafetyError):
        _discarder(storage, paths, store).discard("book-a")

    assert paths.book_meta("book-a").exists()


def test_book_discarder_rejects_unsafe_restore_backup_id(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    discarder = BookDiscarder(storage, paths)

    with pytest.raises(ValueError):
        discarder.restore("book-a", "../book-a_20260616_010203")


def test_book_discarder_rejects_restore_when_target_exists(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_book(storage, store, paths, "book-a", status="archived", state_statuses={1: "exported"})
    discarder = BookDiscarder(storage, paths, truth_store=store)
    result = discarder.discard("book-a")
    _seed_book(storage, store, paths, "book-a", status="incubating", state_statuses={})

    with pytest.raises(RestoreConflictError):
        discarder.restore("book-a", result.backup_id)


def _seed_book(
    storage: BookStorage,
    store: TruthStore,
    paths: StoragePaths,
    book_id: str,
    *,
    status: str,
    state_statuses: dict[int, str],
) -> None:
    storage.write_json(
        paths.book_meta(book_id),
        {
            "book_id": book_id,
            "title": "测试书",
            "genre": "urban",
            "platform": "tomato",
            "status": status,
            "target_chapters": 12,
            "chapter_word_count": 2500,
            "language": "zh",
            "current_chapter": max(state_statuses, default=0),
            "created_at": "2026-06-16T00:00:00+00:00",
            "updated_at": "2026-06-16T00:00:00+00:00",
        },
    )
    storage.write_text(paths.context(book_id), "上下文")
    storage.write_json(paths.world_config(book_id), {"setting": "世界"})
    storage.write_json(paths.characters(book_id), {"characters": []})
    storage.write_json(paths.volumes(book_id), {"volumes": []})
    storage.write_text(paths.chapter_file(book_id, 1), "第1章正文")
    storage.write_json(paths.plan_file(book_id, 1), {"chapter_no": 1})
    storage.write_text(paths.book_dir(book_id) / "exports" / "chapter-0001.txt", "第1章导出")
    storage.write_json(
        paths.chapter_states(book_id),
        {f"{book_id}:{chapter_no:04d}": {"status": chapter_status, "history": []} for chapter_no, chapter_status in state_statuses.items()},
    )
    store.save(
        book_id,
        TruthData(
            chapter_no=1,
            source="runtime_native",
            fact_assertions=("事实",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )


def _discarder(storage: BookStorage, paths: StoragePaths, store: TruthStore) -> BookDiscarder:
    return BookDiscarder(
        storage,
        paths,
        truth_store=store,
        now=lambda: datetime(2026, 6, 16, 1, 2, 3, tzinfo=timezone.utc),
    )
