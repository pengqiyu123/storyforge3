from __future__ import annotations

import hashlib
import json

import pytest

from storyforge3.models import AuditResult, ChapterResult, ChapterStatus, TruthData
from storyforge3.truth.store import TruthStore


@pytest.mark.asyncio
async def test_audit_returns_result(async_client):
    await async_client.post("/api/books/chapter-api/chapters/1/plan")
    await async_client.post("/api/books/chapter-api/chapters/1/draft")

    response = await async_client.post("/api/books/chapter-api/chapters/1/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["passed"] is True
    assert body["data"]["warnings"] == ["节奏可继续加强"]


@pytest.mark.asyncio
async def test_audit_chapter_not_found(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        99,
        ChapterStatus.DRAFTED,
        "第99章",
        "正文",
    )
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
    # Non-existent chapters return 200 + empty status (not 404) so the chapter list
    # does not log a console error per not-yet-started chapter.
    response = await async_client.get("/api/books/chapter-api/chapters/1/status")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "empty"
    assert response.json()["data"]["text"] == ""


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
    await async_client.post("/api/books/chapter-api/chapters/1/plan")
    await async_client.post("/api/books/chapter-api/chapters/1/draft")
    await async_client.post("/api/books/chapter-api/chapters/1/audit")

    response = await async_client.post("/api/books/chapter-api/chapters/1/revise", json={"mode": "bad"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PARAMETER"


@pytest.mark.asyncio
async def test_revise_response_includes_revision_diff(async_client):
    await async_client.post("/api/books/chapter-api/chapters/1/plan")
    await async_client.post("/api/books/chapter-api/chapters/1/draft")
    await async_client.post("/api/books/chapter-api/chapters/1/audit")

    response = await async_client.post("/api/books/chapter-api/chapters/1/revise", json={"mode": "polish"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["revision_diff"]["unit"] == "paragraph"
    assert data["revision_diff"]["summary"]["changed_blocks"] == 1
    assert data["revision_diff"]["blocks"][0]["kind"] == "replace"


@pytest.mark.asyncio
async def test_approve_with_blocking_audit_returns_action_not_allowed(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        7,
        ChapterStatus.AUDITED,
        "第7章",
        "正文",
        audit=AuditResult(7, False, ("below_min_word_count",), (), (), ()),
    )

    response = await async_client.post("/api/books/chapter-api/chapters/7/approve")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "ACTION_NOT_ALLOWED"
    assert body["error"]["current_status"] == "audited"
    assert body["error"]["required"] == ["approve"]
    assert api_chapter_service.approve_calls == 0


@pytest.mark.asyncio
async def test_export_before_truth_committed_returns_action_not_allowed(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        8,
        ChapterStatus.APPROVED,
        "第8章",
        "正文",
    )

    response = await async_client.post("/api/books/chapter-api/chapters/8/export", json={"fmt": "md"})

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "ACTION_NOT_ALLOWED"
    assert body["error"]["current_status"] == "approved"
    assert body["error"]["required"] == ["export"]
    assert api_chapter_service.export_calls == 0


@pytest.mark.asyncio
async def test_export_after_truth_committed_delegates_to_service(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        9,
        ChapterStatus.TRUTH_COMMITTED,
        "第9章",
        "正文",
    )

    response = await async_client.post("/api/books/chapter-api/chapters/9/export", json={"fmt": "md"})

    assert response.status_code == 200
    assert response.json()["data"]["path"].endswith("chapter-0009.md")
    assert api_chapter_service.export_calls == 1


@pytest.mark.asyncio
async def test_run_full_pipeline_respects_initial_gate(async_client, api_chapter_service):
    api_chapter_service.status_result = ChapterResult(
        "chapter-api",
        10,
        ChapterStatus.DRAFTED,
        "第10章",
        "正文",
    )

    response = await async_client.post("/api/books/chapter-api/chapters/10/run")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "ACTION_NOT_ALLOWED"
    assert body["error"]["current_status"] == "drafted"
    assert body["error"]["required"] == ["plan"]


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


@pytest.mark.asyncio
async def test_discard_preview_and_delete_are_scoped(async_client, api_paths, api_storage):
    book_id = "discard-api"
    api_storage.write_json(
        api_paths.book_meta(book_id),
        {
            "book_id": book_id,
            "title": "丢弃测试",
            "genre": "urban",
            "platform": "tomato",
            "status": "active",
            "target_chapters": 10,
            "chapter_word_count": 2500,
            "language": "zh",
            "current_chapter": 2,
            "created_at": "2026-06-15T00:00:00+00:00",
            "updated_at": "2026-06-15T00:00:00+00:00",
        },
    )
    api_storage.write_text(api_paths.chapter_file(book_id, 1), "第1章正文")
    api_storage.write_text(api_paths.chapter_file(book_id, 2), "第2章正文")
    api_storage.write_json(api_paths.plan_file(book_id, 2), {"chapter_no": 2})
    pipeline = api_paths.book_dir(book_id) / "runs" / "pipeline.jsonl"
    api_storage.write_text(
        pipeline,
        "\n".join(
            [
                json.dumps({"book_id": book_id, "chapter_no": 1, "task": "draft"}, ensure_ascii=False),
                json.dumps({"book_id": book_id, "chapter_no": 2, "task": "draft"}, ensure_ascii=False),
            ]
        )
        + "\n",
    )
    api_storage.write_json(api_paths.chapter_states(book_id), {f"{book_id}:0002": {"status": "drafted"}})
    store = TruthStore(str(api_paths.books_root))
    store.save(
        book_id,
        TruthData(
            chapter_no=2,
            source="runtime_native",
            fact_assertions=("第2章事实",),
            character_updates=(),
            relationship_updates=(),
            hook_updates=(),
            irreversible_facts=(),
            notes=(),
        ),
    )

    preview = await async_client.get(f"/api/books/{book_id}/chapters/2/discard-preview")

    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert preview_data["truth_db_rows"] == 1
    assert preview_data["pipeline_lines_removed"] == 1
    assert preview_data["state_removed"] is True
    assert "chapters/0002.md" in preview_data["deleted_files"]
    assert api_paths.chapter_file(book_id, 2).exists()

    response = await async_client.delete(f"/api/books/{book_id}/chapters/2")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["truth_db_rows"] == 1
    assert data["post_reconcile"]["next_writable_chapter_no"] == 2
    assert not api_paths.chapter_file(book_id, 2).exists()
    assert api_paths.chapter_file(book_id, 1).exists()
    assert store.database.query_by_chapter(book_id, 2) == []
    assert (api_paths.book_dir(book_id) / "_trash" / "ch0002" / "001" / "truth_db_rows.json").is_file()
    pipeline_text = pipeline.read_text(encoding="utf-8")
    assert '"chapter_no": 1' in pipeline_text
    assert '"chapter_no": 2' not in pipeline_text
