from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from storyforge3.models import BookConfig, BookStatus
from storyforge3.services.book_service import BookService
from storyforge3.storage import BookStorage, StoragePaths


def run(coro):
    return asyncio.run(coro)


def make_service(tmp_path: Path) -> BookService:
    paths = StoragePaths(tmp_path / "books")
    return BookService(BookStorage(paths.books_root), paths)


def test_book_service_create_get_and_dirs(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    meta = run(service.create(BookConfig("我是路人甲", "urban", "tomato", 200, 2500)))
    assert meta.title == "我是路人甲"
    assert meta.status == BookStatus.INCUBATING
    assert meta.book_id.startswith("wslrj_")
    assert run(service.get(meta.book_id)) == meta
    root = tmp_path / "books" / meta.book_id
    assert (root / "chapters").is_dir()
    assert (root / "truth").is_dir()
    assert (root / "exports").is_dir()
    assert (root / "state").is_dir()


def test_book_service_list_and_update_status(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    meta = run(service.create(BookConfig("测试书", "urban", "tomato", 10, 2000)))
    updated = run(service.update_status(meta.book_id, "active"))
    assert updated.status == BookStatus.ACTIVE
    assert [item.book_id for item in run(service.list_books())] == [meta.book_id]


def test_book_service_rejects_unknown_status(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    meta = run(service.create(BookConfig("测试书", "urban", "tomato", 10, 2000)))
    with pytest.raises(ValueError):
        run(service.update_status(meta.book_id, "unknown"))
