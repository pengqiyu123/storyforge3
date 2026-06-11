from __future__ import annotations

import hashlib

import pytest

from storyforge3.models import ChapterResult, ChapterStatus


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
async def test_get_status_includes_text_hash_and_actual_chars(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        2,
        ChapterStatus.DRAFTED,
        "第2章",
        "林默保存正文。",
    )

    response = await async_client.get("/api/books/chapter-api/chapters/2/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["text"] == "林默保存正文。"
    assert data["actual_chars"] == 6
    assert data["content_hash"] == hashlib.sha256("林默保存正文。".encode("utf-8")).hexdigest()[:8]


@pytest.mark.asyncio
async def test_export_preview_tomato_txt_returns_preview_and_format_errors(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        2,
        ChapterStatus.DRAFTED,
        "副楼门口",
        "# 标题\n\n**林默**走进副楼。\n\n他停下脚步。",
    )

    response = await async_client.get("/api/books/chapter-api/chapters/2/export-preview?fmt=tomato_txt")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["chapter_no"] == 2
    assert data["format"] == "tomato_txt"
    assert data["preview_text"].splitlines()[0] == "第2章 副楼门口"
    assert "**" not in data["preview_text"]
    assert "#" not in data["preview_text"]
    assert "word_count_out_of_range" in data["format_errors"]
    assert data["char_count"] == 19


@pytest.mark.asyncio
async def test_export_preview_markdown_and_qidian(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        3,
        ChapterStatus.DRAFTED,
        "第3章",
        "林默站在门口。\n\n提示音再次响起。",
    )

    markdown = await async_client.get("/api/books/chapter-api/chapters/3/export-preview?fmt=markdown")
    qidian = await async_client.get("/api/books/chapter-api/chapters/3/export-preview?fmt=qidian_txt")

    assert markdown.status_code == 200
    assert markdown.json()["data"]["preview_text"] == "## 第3章\n\n林默站在门口。\n\n提示音再次响起。"
    assert markdown.json()["data"]["format_errors"] == []

    assert qidian.status_code == 200
    assert qidian.json()["data"]["preview_text"] == "第3章\n\n林默站在门口。\n\n提示音再次响起。"
    assert qidian.json()["data"]["format_errors"] == []


@pytest.mark.asyncio
async def test_export_preview_rejects_invalid_format(async_client):
    response = await async_client.get("/api/books/chapter-api/chapters/2/export-preview?fmt=docx")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_export_preview_returns_404_for_missing_chapter(async_client):
    response = await async_client.get("/api/books/chapter-api/chapters/88/export-preview?fmt=tomato_txt")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_text_endpoint(async_client, api_chapter_service):
    response = await async_client.put(
        "/api/books/chapter-api/chapters/2/text",
        json={"text": "林默手动改稿。", "expected_hash": "hash0001"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "needs_review"
    assert data["text"] == "林默手动改稿。"
    assert data["actual_chars"] == 6
    assert api_chapter_service.last_update_text == ("chapter-api", 2, "林默手动改稿。", "hash0001")


@pytest.mark.asyncio
async def test_update_text_endpoint_maps_conflict(async_client, api_chapter_service):
    api_chapter_service.update_conflict = True

    response = await async_client.put(
        "/api/books/chapter-api/chapters/2/text",
        json={"text": "林默手动改稿。", "expected_hash": "stale"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONTENT_CONFLICT"
    assert response.json()["error"]["message"] == "章节内容已被修改，请刷新后重试"


@pytest.mark.asyncio
async def test_revise_invalid_mode(async_client):
    response = await async_client.post("/api/books/chapter-api/chapters/1/revise", json={"mode": "bad"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_revise_response_includes_revision_diff(async_client):
    response = await async_client.post("/api/books/chapter-api/chapters/1/revise", json={"mode": "polish"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["revision_diff"]["unit"] == "paragraph"
    assert data["revision_diff"]["summary"]["changed_blocks"] == 1
    assert data["revision_diff"]["blocks"][0]["kind"] == "replace"


@pytest.mark.asyncio
async def test_export_preview_returns_formatted_text(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        2,
        ChapterStatus.DRAFTED,
        "第2章",
        "林默站在副楼门口。\n\n提示音从走廊深处响了一下。",
    )

    response = await async_client.get("/api/books/chapter-api/chapters/2/export-preview?fmt=markdown")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["format"] == "markdown"
    assert data["preview_text"].startswith("## 第2章")
    assert data["format_errors"] == []


@pytest.mark.asyncio
async def test_export_preview_rejects_epub_format(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        2,
        ChapterStatus.DRAFTED,
        "第2章",
        "林默站在副楼门口。",
    )

    response = await async_client.get("/api/books/chapter-api/chapters/2/export-preview?fmt=epub")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"
