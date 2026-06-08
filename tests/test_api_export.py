from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_export_book_not_found(async_client):
    response = await async_client.post("/api/books/missing-book/export", json={"fmt": "md"})

    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "BOOK_NOT_FOUND"
