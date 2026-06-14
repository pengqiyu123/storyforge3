from __future__ import annotations

from pathlib import Path

from storyforge3.models import ChapterStatus
from storyforge3.state.machine import ChapterStateMachine


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


def test_update_status_book_not_found(client):
    resp = client.patch("/api/books/nonexistent/status", json={"status": "active"})
    assert resp.status_code == 404


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
    by_chapter = {item["chapter_no"]: item for item in data["chapters"]}
    assert by_chapter[1]["status"] == "consistent"
    assert by_chapter[2]["status"] == "consistent"
    assert by_chapter[3]["status"] == "inconsistent"
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
