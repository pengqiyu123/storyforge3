from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_audit_returns_result(async_client):
    response = await async_client.post("/api/books/chapter-api/chapters/1/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["passed"] is True
    assert body["data"]["warnings"] == ["节奏可继续加强"]


@pytest.mark.asyncio
async def test_audit_chapter_not_found(async_client, api_chapter_service):
    api_chapter_service.audit_not_found = True

    response = await async_client.post("/api/books/chapter-api/chapters/99/audit")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_normalize_validates_input(async_client):
    response = await async_client.post(
        "/api/books/chapter-api/chapters/1/normalize",
        json={"text": "短正文", "target_chars": 0},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_get_status_not_found(async_client):
    response = await async_client.get("/api/books/chapter-api/chapters/1/status")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_revise_invalid_mode(async_client):
    response = await async_client.post("/api/books/chapter-api/chapters/1/revise", json={"mode": "bad"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"
