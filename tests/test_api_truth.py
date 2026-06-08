from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_latest_truth_empty(async_client):
    response = await async_client.get("/api/books/truth-api/truth/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"] is None


@pytest.mark.asyncio
async def test_extract_truth_success(async_client, api_truth_store):
    response = await async_client.post(
        "/api/books/truth-api/truth/extract",
        json={"chapter_no": 3, "text": "林默在检测中心走廊停下。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["fact_assertions"] == ["第3章 truth 已提取。"]
    assert api_truth_store.saved[0] == "truth-api"
    assert api_truth_store.saved[1].chapter_no == 3
