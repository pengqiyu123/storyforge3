from __future__ import annotations

from pathlib import Path

from storyforge3.storage import BookStorage, StoragePaths


def test_storage_paths_resolve_book_files(tmp_path: Path) -> None:
    paths = StoragePaths(tmp_path / "books")
    assert paths.book_dir("book") == tmp_path / "books" / "book"
    assert paths.book_meta("book").name == "book.json"
    assert paths.world_config("book").name == "world.json"
    assert paths.characters("book").name == "characters.json"
    assert paths.relationships("book").name == "relationships.json"
    assert paths.volumes("book").name == "volumes.json"
    assert paths.chapter_file("book", 3).name == "0003.md"
    assert paths.truth_file("book", 3).name == "chapter-0003.json"
    assert paths.export_file("book", 3, "txt").name == "chapter-0003.txt"
    assert paths.chapter_states("book").name == "chapter_states.json"


def test_book_storage_json_missing_returns_none(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    assert storage.read_json(tmp_path / "missing.json") is None


def test_book_storage_write_json_creates_parent(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "nested" / "data.json"
    storage.write_json(path, {"ok": True})
    assert storage.read_json(path) == {"ok": True}


def test_book_storage_text_and_list_books(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    paths = StoragePaths(tmp_path)
    storage.write_text(paths.book_dir("a") / "context.md", "hello")
    storage.write_json(paths.book_meta("a"), {"book_id": "a"})
    storage.ensure_dir(paths.book_dir("empty"))
    assert storage.read_text(paths.book_dir("a") / "context.md") == "hello"
    assert storage.list_book_ids() == ["a"]
