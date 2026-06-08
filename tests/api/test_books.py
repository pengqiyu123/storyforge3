from __future__ import annotations


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
