from __future__ import annotations

from pathlib import Path

from storyforge3.models import ChapterStatus, TruthData
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.store import TruthStore


def test_create_book(client):
    resp = client.post(
        "/api/books",
        json={
            "title": "测试小说",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 50,
            "chapter_word_count": 2500,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["title"] == "测试小说"
    assert body["data"]["genre"] == "urban"
    assert body["data"]["book_id"]


def test_list_books_empty(client):
    resp = client.get("/api/books")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"] == []


def test_list_books_after_create(client):
    client.post(
        "/api/books",
        json={
            "title": "书A",
            "genre": "xuanhuan",
            "platform": "tomato",
            "target_chapters": 100,
            "chapter_word_count": 2000,
        },
    )
    resp = client.get("/api/books")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


def test_get_book(client):
    create = client.post(
        "/api/books",
        json={
            "title": "书B",
            "genre": "urban",
            "platform": "qidian",
            "target_chapters": 80,
            "chapter_word_count": 3000,
        },
    )
    book_id = create.json()["data"]["book_id"]
    resp = client.get(f"/api/books/{book_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "书B"


def test_get_book_not_found(client):
    resp = client.get("/api/books/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "BOOK_NOT_FOUND"


def test_update_book_status(client):
    create = client.post(
        "/api/books",
        json={
            "title": "书C",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 50,
            "chapter_word_count": 2500,
        },
    )
    book_id = create.json()["data"]["book_id"]
    resp = client.patch(f"/api/books/{book_id}/status", json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "active"


def test_archive_book_is_hidden_from_default_list_but_still_readable(client):
    create = client.post(
        "/api/books",
        json={
            "title": "归档书",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 50,
            "chapter_word_count": 2500,
        },
    )
    book_id = create.json()["data"]["book_id"]

    archived = client.patch(f"/api/books/{book_id}/status", json={"status": "archived"})
    default_list = client.get("/api/books")
    include_archived = client.get("/api/books?include_archived=true")
    detail = client.get(f"/api/books/{book_id}")

    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"
    assert book_id not in [item["book_id"] for item in default_list.json()["data"]]
    assert book_id in [item["book_id"] for item in include_archived.json()["data"]]
    assert detail.status_code == 200


def test_update_status_book_not_found(client):
    resp = client.patch("/api/books/nonexistent/status", json={"status": "active"})
    assert resp.status_code == 404


def test_delete_preview_delete_and_restore_book(client, config):
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_lifecycle_book(storage, store, paths, "book-a", status="archived", state_statuses={1: "exported"})

    preview = client.get("/api/books/book-a/delete-preview")
    deleted = client.delete("/api/books/book-a")
    after_delete = client.get("/api/books/book-a")
    backup_id = deleted.json()["data"]["backup_id"]
    restored = client.post(f"/api/books/_trash/{backup_id}/restore")

    assert preview.status_code == 200
    assert "book.json" in preview.json()["data"]["files"]
    assert "chapters/0001.md" in preview.json()["data"]["files"]
    assert deleted.status_code == 200
    assert deleted.json()["data"]["truth_db_rows"] == 1
    assert after_delete.status_code == 404
    assert restored.status_code == 200
    assert restored.json()["data"]["book_id"] == "book-a"
    assert client.get("/api/books/book-a").status_code == 200


def test_delete_active_book_with_unfinished_chapter_is_rejected(client, config):
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)
    store = TruthStore(str(paths.books_root))
    _seed_lifecycle_book(storage, store, paths, "book-a", status="active", state_statuses={1: "drafted"})

    response = client.delete("/api/books/book-a")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BOOK_DELETE_NOT_ALLOWED"
    assert paths.book_meta("book-a").exists()


def test_restore_rejects_unsafe_backup_id(client):
    response = client.post("/api/books/_trash/..%2Fbook-a_20260616_010203/restore")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


def test_create_book_validation(client):
    resp = client.post("/api/books", json={"title": "缺字段"})
    assert resp.status_code == 422


def test_reconcile_book_reports_ghost_chapters(client, config):
    root = Path(config.books_dir) / "book"
    _write_book_artifact(root, "chapters", "0001.md", "第1章正文")
    _write_book_artifact(root, "plans", "0001.json", "{}")
    _write_book_artifact(root, "truth", "chapter-0001.json", "{}")
    _write_book_artifact(root, "exports", "chapter-0001.txt", "第1章导出")
    _advance_state(Path(config.books_dir), "book", 1, ChapterStatus.EXPORTED)

    _write_book_artifact(root, "chapters", "0002.md", "第2章正文")
    _write_book_artifact(root, "plans", "0002.json", "{}")
    _write_book_artifact(root, "truth", "chapter-0002.json", "{}")
    _advance_state(Path(config.books_dir), "book", 2, ChapterStatus.APPROVED)

    _write_book_artifact(root, "truth", "chapter-0003.json", "{}")
    _write_book_artifact(root, "exports", "chapter-0003.txt", "第3章导出")

    resp = client.get("/api/books/book/reconcile")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["book_id"] == "book"
    assert data["inconsistent_count"] == 1
    assert data["valid_chapter_count"] == 2
    assert data["highest_contiguous_chapter"] == 2
    assert data["next_writable_chapter_no"] == 3
    assert data["has_blocking_inconsistency"] is True
    by_chapter = {item["chapter_no"]: item for item in data["chapters"]}
    assert by_chapter[1]["status"] == "consistent"
    assert by_chapter[1]["validity"] == "valid"
    assert by_chapter[2]["status"] == "consistent"
    assert by_chapter[2]["validity"] == "valid"
    assert by_chapter[3]["status"] == "inconsistent"
    assert by_chapter[3]["validity"] == "orphan"
    assert by_chapter[3]["inconsistent_reasons"] == [
        "export_without_state",
        "export_without_text",
        "truth_without_state",
    ]


def _write_book_artifact(root: Path, subdir: str, name: str, content: str) -> None:
    path = root / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _advance_state(root: Path, book_id: str, chapter_no: int, status: ChapterStatus) -> None:
    machine = ChapterStateMachine(root / book_id / "state" / "chapter_states.json")
    for next_status in (
        ChapterStatus.PLANNED,
        ChapterStatus.DRAFTED,
        ChapterStatus.AUDITED,
        ChapterStatus.APPROVED,
        ChapterStatus.TRUTH_COMMITTED,
        ChapterStatus.EXPORTED,
    ):
        machine.advance(book_id, chapter_no, next_status)
        if next_status == status:
            return


def _seed_lifecycle_book(
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
