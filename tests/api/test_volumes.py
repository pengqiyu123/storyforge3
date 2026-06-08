from __future__ import annotations


def _create_book(client) -> str:
    resp = client.post(
        "/api/books",
        json={
            "title": "卷纲测试",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 12,
            "chapter_word_count": 2000,
        },
    )
    return resp.json()["data"]["book_id"]


def test_plan_list_and_get_volumes(client):
    book_id = _create_book(client)
    resp = client.post(f"/api/books/{book_id}/volumes", json={"volume_count": 2, "total_chapters": 12})
    assert resp.status_code == 200
    assert resp.json()["data"][0]["title"] == "存在感异常"
    assert resp.json()["data"][0]["key_scenes"] == ["检测中心初检", "走廊异常回响"]

    listed = client.get(f"/api/books/{book_id}/volumes")
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2

    one = client.get(f"/api/books/{book_id}/volumes/1")
    assert one.status_code == 200
    assert one.json()["data"]["volume_no"] == 1


def test_get_volume_not_found_returns_envelope(client):
    book_id = _create_book(client)
    resp = client.get(f"/api/books/{book_id}/volumes/9")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "BOOK_NOT_FOUND"


def test_update_volume(client):
    book_id = _create_book(client)
    resp = client.put(
        f"/api/books/{book_id}/volumes/1",
        json={
            "title": "更新卷名",
            "chapter_count": 8,
            "synopsis": "林默主动进入副楼。",
            "key_scenes": ["主动回访"],
            "rhythm_curve": ["rise"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "更新卷名"
    assert resp.json()["data"]["rhythm_curve"] == ["rise"]
