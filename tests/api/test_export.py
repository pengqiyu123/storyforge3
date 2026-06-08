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
