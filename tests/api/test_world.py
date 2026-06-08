from __future__ import annotations


def _create_book(client) -> str:
    resp = client.post(
        "/api/books",
        json={
            "title": "世界测试",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 30,
            "chapter_word_count": 2000,
        },
    )
    return resp.json()["data"]["book_id"]


def test_build_and_get_world(client):
    book_id = _create_book(client)
    resp = client.post(
        f"/api/books/{book_id}/world",
        json={
            "genre": "urban",
            "seed_brief": "都市背景，异能觉醒，存在感系统",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["setting"] == "现代都市里的异常检测中心"
    assert body["data"]["rules"] == ["存在感越低越难被普通人注意", "异常检测会放大存在痕迹"]

    fetched = client.get(f"/api/books/{book_id}/world")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["power_system"] == "存在感调节"


def test_get_world_not_found(client):
    resp = client.get("/api/books/nonexistent/world")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "BOOK_NOT_FOUND"


def test_update_world(client):
    book_id = _create_book(client)
    resp = client.put(
        f"/api/books/{book_id}/world",
        json={
            "setting": "更新后的现代都市",
            "power_system": "低存在感与异常检测",
            "core_conflict": "隐藏身份与主动调查",
            "rules": ["规则A", "规则B"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["setting"] == "更新后的现代都市"
    assert resp.json()["data"]["rules"] == ["规则A", "规则B"]
