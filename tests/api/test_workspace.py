from __future__ import annotations

import zipfile
from pathlib import Path


def write_api_book(root: Path) -> None:
    book_dir = root / "lurenjia"
    (book_dir / "chapters").mkdir(parents=True, exist_ok=True)
    (book_dir / "book.json").write_text('{"title":"我是路人甲"}', encoding="utf-8")
    (book_dir / "chapters" / "0001.md").write_text("当前正文", encoding="utf-8")


def test_validate_workspace_endpoint(client, config) -> None:
    write_api_book(Path(config.books_dir))

    response = client.get("/api/workspace/validate")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["valid"] is True
    assert data["book_count"] == 1
    assert data["books_dir"] == str(Path(config.books_dir))


def test_backup_workspace_endpoint_returns_zip(client, config) -> None:
    write_api_book(Path(config.books_dir))

    response = client.post("/api/workspace/backup")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.content.startswith(b"PK")


def test_restore_workspace_endpoint_handles_upload(client, config) -> None:
    books_dir = Path(config.books_dir)
    write_api_book(books_dir)
    incoming = books_dir.parent / "incoming.zip"
    with zipfile.ZipFile(incoming, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lurenjia/book.json", '{"title":"恢复版"}')
        archive.writestr("lurenjia/chapters/0001.md", "恢复正文")

    with incoming.open("rb") as handle:
        response = client.post(
            "/api/workspace/restore",
            files={"file": ("incoming.zip", handle, "application/zip")},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["success"] is True
    assert data["book_count"] == 1
    assert Path(data["backup_path"]).exists()
    assert (books_dir / "lurenjia" / "chapters" / "0001.md").read_text(encoding="utf-8") == "恢复正文"
