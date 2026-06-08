from __future__ import annotations


def _create_book(client) -> str:
    resp = client.post(
        "/api/books",
        json={
            "title": "角色测试",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 30,
            "chapter_word_count": 2000,
        },
    )
    return resp.json()["data"]["book_id"]


def test_create_and_list_character(client):
    book_id = _create_book(client)
    resp = client.post(f"/api/books/{book_id}/characters", json={"spec": "主角林默，低存在感能力"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["name"] == "林默"
    assert body["data"]["role"] == "protagonist"
    assert body["data"]["abilities"] == ["存在感调节"]

    listed = client.get(f"/api/books/{book_id}/characters")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["name"] == "林默"


def test_create_character_batch_and_relationships(client):
    book_id = _create_book(client)
    resp = client.post(f"/api/books/{book_id}/characters/batch", json={"specs": ["周岚", "沈砚"]})
    assert resp.status_code == 200
    assert [item["name"] for item in resp.json()["data"]] == ["周岚", "沈砚"]

    relationships = client.get(f"/api/books/{book_id}/characters/relationships")
    assert relationships.status_code == 200
    assert relationships.json()["data"][0]["character_a"] == "林默"
    assert relationships.json()["data"][0]["character_b"] == "周岚"


def test_update_character(client):
    book_id = _create_book(client)
    client.post(f"/api/books/{book_id}/characters", json={"spec": "主角林默，低存在感能力"})
    resp = client.patch(
        f"/api/books/{book_id}/characters/林默",
        json={"updates": {"profile": "开始主动调查检测中心的少年"}},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["profile"] == "开始主动调查检测中心的少年"
