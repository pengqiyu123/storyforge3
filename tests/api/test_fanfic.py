from __future__ import annotations


def test_create_book_accepts_fanfic_mode(client):
    resp = client.post(
        "/api/books",
        json={
            "title": "同人测试",
            "genre": "fanfic",
            "platform": "qidian",
            "target_chapters": 20,
            "chapter_word_count": 2200,
            "fanfic_mode": "canon",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["fanfic_mode"] == "canon"


def test_import_and_get_fanfic_canon(client):
    create = client.post(
        "/api/books",
        json={
            "title": "正典导入",
            "genre": "fanfic",
            "platform": "qidian",
            "target_chapters": 20,
            "chapter_word_count": 2200,
            "fanfic_mode": "canon",
        },
    )
    book_id = create.json()["data"]["book_id"]

    imported = client.post(
        f"/api/books/{book_id}/fanfic/import",
        json={"source_text": "林默说：先等等。", "source_name": "原作A", "mode": "canon"},
    )

    assert imported.status_code == 200
    assert imported.json()["data"]["book_id"] == book_id
    assert imported.json()["data"]["source_name"] == "原作A"
    assert imported.json()["data"]["mode"] == "canon"
    fetched = client.get(f"/api/books/{book_id}/fanfic/canon")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["book_id"] == book_id


def test_get_fanfic_canon_returns_404_when_absent(client):
    resp = client.get("/api/books/missing/fanfic/canon")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BOOK_NOT_FOUND"


def test_refresh_fanfic_canon(client):
    create = client.post(
        "/api/books",
        json={
            "title": "正典刷新",
            "genre": "fanfic",
            "platform": "qidian",
            "target_chapters": 20,
            "chapter_word_count": 2200,
            "fanfic_mode": "cp",
        },
    )
    book_id = create.json()["data"]["book_id"]
    client.post(f"/api/books/{book_id}/fanfic/import", json={"source_text": "旧素材", "source_name": "原作B", "mode": "cp"})

    refreshed = client.post(
        f"/api/books/{book_id}/fanfic/refresh",
        json={"source_text": "新素材", "source_name": "ignored", "mode": "canon"},
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["mode"] == "cp"
    assert refreshed.json()["data"]["source_name"] == "原作B"


def test_invalid_fanfic_mode_returns_422(client):
    resp = client.post(
        "/api/books/book/fanfic/import",
        json={"source_text": "原作", "source_name": "原作A", "mode": "bad"},
    )

    assert resp.status_code == 422
