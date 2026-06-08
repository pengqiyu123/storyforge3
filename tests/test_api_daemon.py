from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_start_daemon_returns_started(async_client, api_daemon_service):
    response = await async_client.post(
        "/api/books/daemon-api/daemon/start",
        json={
            "max_chapters_per_run": 3,
            "max_consecutive_failures": 2,
            "chapter_interval_seconds": 0,
            "start_from_chapter": 4,
            "target_chapters": 6,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "started", "book_id": "daemon-api"}
    assert api_daemon_service.last_config.book_id == "daemon-api"
    assert api_daemon_service.last_config.max_chapters_per_run == 3
