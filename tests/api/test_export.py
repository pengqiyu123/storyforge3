from __future__ import annotations

from pathlib import Path


def test_export_book_returns_download_response(client, mock_export_service):
    resp = client.post("/api/books/export-api/export", json={"fmt": "md", "approved_only": False})
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith('attachment; filename="export-api.txt"')
    assert resp.text == "book md approved=False"
    assert mock_export_service.last_book == ("export-api", "md", False)


def test_download_export_returns_existing_file(client, config):
    path = Path(config.books_dir) / "export-api" / "exports" / "book.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("导出正文", encoding="utf-8")

    resp = client.get("/api/books/export-api/exports/book.txt")
    assert resp.status_code == 200
    assert resp.text == "导出正文"
    assert resp.headers["content-disposition"].startswith('attachment; filename="book.txt"')


def test_download_export_missing_returns_404(client):
    resp = client.get("/api/books/export-api/exports/missing.txt")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EXPORT_NOT_FOUND"


def test_delete_export_removes_single_file(client, config):
    export_dir = Path(config.books_dir) / "export-api" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "book.txt").write_text("导出正文", encoding="utf-8")
    (export_dir / "book.md").write_text("# 导出", encoding="utf-8")

    resp = client.delete("/api/books/export-api/exports/book.txt")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"deleted": "book.txt"}
    assert not (export_dir / "book.txt").exists()
    assert (export_dir / "book.md").exists()


def test_delete_export_missing_and_path_traversal_return_404(client, config):
    outside = Path(config.books_dir) / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("secret", encoding="utf-8")

    missing = client.delete("/api/books/export-api/exports/missing.txt")
    traversal = client.delete("/api/books/export-api/exports/..%2Fsecret.txt")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EXPORT_NOT_FOUND"
    assert traversal.status_code == 404
    assert traversal.json()["error"]["code"] == "EXPORT_NOT_FOUND"
    assert outside.exists()


def test_clear_exports_removes_all_non_tmp_files(client, config):
    export_dir = Path(config.books_dir) / "export-api" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "book.txt").write_text("导出正文", encoding="utf-8")
    (export_dir / "book.md").write_text("# 导出", encoding="utf-8")
    (export_dir / "partial.txt.tmp").write_text("partial", encoding="utf-8")

    resp = client.delete("/api/books/export-api/exports")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"deleted": ["book.md", "book.txt"], "count": 2}
    assert not (export_dir / "book.txt").exists()
    assert not (export_dir / "book.md").exists()
    assert (export_dir / "partial.txt.tmp").exists()


def test_clear_exports_is_empty_when_export_dir_missing(client):
    resp = client.delete("/api/books/export-api/exports")

    assert resp.status_code == 200
    assert resp.json()["data"] == {"deleted": [], "count": 0}
