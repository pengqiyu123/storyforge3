from __future__ import annotations

from pathlib import Path


def test_list_snapshots_endpoint_returns_metadata(client, config):
    from storyforge3.snapshot import SnapshotManager

    root = Path(config.books_dir) / "lurenjia"
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "chapters" / "0001.md").write_text("第一章正文", encoding="utf-8")
    SnapshotManager(config.books_dir).create_snapshot("lurenjia", 1)

    response = client.get("/api/books/lurenjia/snapshots")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["chapter_no"] == 1
    assert data[0]["path"].endswith(".zip")


def test_restore_snapshot_endpoint_restores_files(client, config):
    from storyforge3.snapshot import SnapshotManager

    root = Path(config.books_dir) / "lurenjia"
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "chapters" / "0001.md").write_text("原始正文", encoding="utf-8")
    (root / "state" / "snapshot.json").write_text('{"ok":true}', encoding="utf-8")
    manager = SnapshotManager(config.books_dir)
    snapshot = manager.create_snapshot("lurenjia", 1)
    assert snapshot is not None
    (root / "chapters" / "0001.md").write_text("脏正文", encoding="utf-8")

    response = client.post(f"/api/books/lurenjia/snapshots/{snapshot.name}/restore")

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 2
    assert (root / "chapters" / "0001.md").read_text(encoding="utf-8") == "原始正文"


def test_restore_snapshot_endpoint_returns_404_for_missing_snapshot(client):
    response = client.post("/api/books/lurenjia/snapshots/missing.zip/restore")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
