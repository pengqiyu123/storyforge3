from __future__ import annotations


def test_start_daemon_returns_started_and_maps_config(client, mock_daemon_service):
    resp = client.post(
        "/api/books/daemon-api/daemon/start",
        json={
            "max_chapters_per_run": 3,
            "max_consecutive_failures": 2,
            "chapter_interval_seconds": 0,
            "start_from_chapter": 4,
            "target_chapters": 6,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"status": "started", "book_id": "daemon-api"}
    assert mock_daemon_service.last_config.book_id == "daemon-api"
    assert mock_daemon_service.last_config.max_chapters_per_run == 3
    assert mock_daemon_service.last_config.max_consecutive_failures == 2
    assert mock_daemon_service.last_config.chapter_interval_seconds == 0
    assert mock_daemon_service.last_config.start_from_chapter == 4
    assert mock_daemon_service.last_config.target_chapters == 6
