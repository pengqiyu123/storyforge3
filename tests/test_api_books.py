from __future__ import annotations

import pytest

from tests.conftest_api import create_api_book


@pytest.mark.asyncio
async def test_create_book_returns_id(async_client):
    response = await async_client.post(
        "/api/books",
        json={
            "title": "测试小说",
            "genre": "urban",
            "platform": "tomato",
            "target_chapters": 50,
            "chapter_word_count": 2500,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["book_id"]
    assert body["data"]["title"] == "测试小说"


@pytest.mark.asyncio
async def test_list_books_returns_array(async_client):
    await create_api_book(async_client, title="书A")

    response = await async_client.get("/api/books")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["data"], list)
    assert body["data"][0]["title"] == "书A"


@pytest.mark.asyncio
async def test_get_book_not_found(async_client):
    response = await async_client.get("/api/books/nonexistent")

    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "BOOK_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_book_status(async_client):
    book_id = await create_api_book(async_client, title="书B")

    response = await async_client.patch(f"/api/books/{book_id}/status", json={"status": "active"})

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"
