from __future__ import annotations

import asyncio
import hashlib
import json

from storyforge3.api.sse import PipelineEvent, SSEManager, make_chunk_event, make_progress_event, sse_manager
from storyforge3.api.routes.events import sse_subscribe
from storyforge3.models import ChapterResult, ChapterStatus


def test_chapter_status_empty_when_not_started(client):
    # Non-existent chapters return 200 + empty status (not 404) so the chapter list
    # does not log a console error per not-yet-started chapter.
    resp = client.get("/api/books/nonexistent/chapters/1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "empty"
    assert body["data"]["text"] == ""


def test_chapter_plan_and_draft_emit_sse_events(client, mock_chapter_service):
    book_id = "chapter-api-draft"
    plan = client.post(f"/api/books/{book_id}/chapters/1/plan")
    assert plan.status_code == 200
    assert plan.json()["data"]["goal"] == "推进主线"
    assert plan.json()["data"]["must_keep"] == ["林默谨慎"]

    draft = client.post(
        f"/api/books/{book_id}/chapters/1/draft",
        json={"goal": "进入副楼", "must_keep": ["保留提示音"], "must_avoid": ["解释设定"]},
    )
    assert draft.status_code == 200
    assert "林默停在副楼门口" in draft.json()["data"]["text"]
    assert mock_chapter_service.last_draft_intent.goal == "进入副楼"

    events = asyncio.run(_collect_replayed_events(sse_manager, book_id, 1, 4))
    assert [event["type"] for event in events] == ["pipeline:start", "llm:progress", "llm:chunk", "pipeline:complete"]
    assert events[1]["detail"] == {"completed": 1, "total": 2}
    assert events[2]["type"] == "llm:chunk"
    assert events[2]["detail"]["text"] == "林默停在副楼门口。"


def test_get_chapter_plan_returns_intent(client):
    resp = client.get("/api/books/chapter-api-draft/chapters/1/plan")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["goal"] == "推进主线"
    assert data["outline_node"] == "检测中心副楼出现异常回响"


def test_chapter_audit_before_draft_returns_404(client, mock_chapter_service):
    mock_chapter_service.raise_audit_not_found = True
    resp = client.post("/api/books/chapter-api/chapters/1/audit")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


def test_chapter_audit_llm_and_normalize(client):
    audit = client.post("/api/books/chapter-api/chapters/2/audit")
    assert audit.status_code == 200
    assert audit.json()["data"]["passed"] is True
    assert audit.json()["data"]["warnings"] == ["节奏可继续加强"]
    rule_results = audit.json()["data"]["rule_results"]
    assert rule_results[0]["rule_id"] == "info_dump"
    assert rule_results[0]["severity"] == "WARNING"
    assert rule_results[0]["category"] == "STRUCTURE"
    assert rule_results[0]["detail"]["paragraph_indices"] == [1]
    assert rule_results[0]["detail"]["snippet"] == "这一段太长，需要拆分。"

    llm_audit = client.post("/api/books/chapter-api/chapters/2/llm-audit", json={"text": "测试正文"})
    assert llm_audit.status_code == 200
    assert llm_audit.json()["data"]["issues"][0]["dimension"] == "情节逻辑"

    normalized = client.post(
        "/api/books/chapter-api/chapters/2/normalize",
        json={"text": "短正文", "target_chars": 1200, "soft_ratio": 0.2},
    )
    assert normalized.status_code == 200
    assert normalized.json()["data"]["action"] == "expand"
    assert normalized.json()["data"]["final_chars"] == 1200


def test_chapter_revise_approve_export_run_and_status(client, mock_chapter_service):
    book_id = "chapter-api-run"
    revised = client.post(f"/api/books/{book_id}/chapters/3/revise", json={"mode": "polish"})
    assert revised.status_code == 200
    assert revised.json()["data"]["status"] == "revised"
    assert revised.json()["data"]["revision_diff"]["summary"]["changed_blocks"] == 1
    assert revised.json()["data"]["revision_diff"]["blocks"][0]["kind"] == "replace"
    assert mock_chapter_service.last_revision_mode == "polish"

    approved = client.post(f"/api/books/{book_id}/chapters/3/approve")
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "exported"

    exported = client.post(f"/api/books/{book_id}/chapters/3/export", json={"fmt": "md"})
    assert exported.status_code == 200
    assert exported.json()["data"]["path"].endswith("chapter-0003.md")
    assert mock_chapter_service.last_export_format == "md"

    run = client.post(f"/api/books/{book_id}/chapters/3/run")
    assert run.status_code == 200
    assert run.json()["data"]["status"] == "exported"

    status = client.get(f"/api/books/{book_id}/chapters/3/status")
    assert status.status_code == 200
    status_data = status.json()["data"]
    assert status_data["status"] == "exported"
    assert status_data["text"] == "完整管线正文"
    assert status_data["actual_chars"] == 6
    assert status_data["content_hash"] == _fingerprint("完整管线正文")


def test_export_preview_supports_tomato_markdown_and_qidian(client, mock_chapter_service):
    mock_chapter_service.status_result = ChapterResult(
        "chapter-api-preview",
        5,
        ChapterStatus.DRAFTED,
        "异常回响",
        "# 标题\n\n**林默**站在副楼门口。\n\n提示音从走廊尽头传来。",
    )

    tomato = client.get("/api/books/chapter-api-preview/chapters/5/export-preview?fmt=tomato_txt")
    markdown = client.get("/api/books/chapter-api-preview/chapters/5/export-preview?fmt=markdown")
    qidian = client.get("/api/books/chapter-api-preview/chapters/5/export-preview?fmt=qidian_txt")

    assert tomato.status_code == 200
    tomato_data = tomato.json()["data"]
    assert tomato_data["format"] == "tomato_txt"
    assert tomato_data["preview_text"].splitlines()[0] == "第5章 异常回响"
    assert "**" not in tomato_data["preview_text"]
    assert "#" not in tomato_data["preview_text"]
    assert "word_count_out_of_range" in tomato_data["format_errors"]

    assert markdown.status_code == 200
    assert markdown.json()["data"]["preview_text"] == "## 第5章\n\n# 标题\n\n**林默**站在副楼门口。\n\n提示音从走廊尽头传来。"
    assert markdown.json()["data"]["format_errors"] == []

    assert qidian.status_code == 200
    assert qidian.json()["data"]["preview_text"] == "第5章\n\n# 标题\n\n**林默**站在副楼门口。\n\n提示音从走廊尽头传来。"
    assert qidian.json()["data"]["format_errors"] == []


def test_export_preview_rejects_invalid_format_and_missing_chapter(client):
    invalid = client.get("/api/books/chapter-api-preview/chapters/5/export-preview?fmt=docx")
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_PARAMETER"

    missing = client.get("/api/books/chapter-api-preview/chapters/99/export-preview?fmt=tomato_txt")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


def test_update_chapter_text_returns_needs_review_and_content_metadata(client, mock_chapter_service):
    resp = client.put(
        "/api/books/chapter-api-edit/chapters/3/text",
        json={"text": "林默保存了人工修改。", "expected_hash": "abcd1234"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "needs_review"
    assert data["text"] == "林默保存了人工修改。"
    assert data["actual_chars"] == 9
    assert data["content_hash"] == _fingerprint("林默保存了人工修改。")
    assert mock_chapter_service.last_update_text == (
        "chapter-api-edit",
        3,
        "林默保存了人工修改。",
        "abcd1234",
    )


def test_update_chapter_text_maps_missing_empty_and_conflict_errors(client, mock_chapter_service):
    mock_chapter_service.raise_update_not_found = True
    missing = client.put("/api/books/chapter-api-edit/chapters/9/text", json={"text": "人工修改。"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    mock_chapter_service.raise_update_not_found = False
    mock_chapter_service.raise_update_empty = True
    empty = client.put("/api/books/chapter-api-edit/chapters/9/text", json={"text": "人工修改。"})
    assert empty.status_code == 409
    assert empty.json()["error"]["code"] == "CHAPTER_EMPTY"
    assert empty.json()["error"]["message"] == "空章节请先使用 draft 管线生成正文"

    mock_chapter_service.raise_update_empty = False
    mock_chapter_service.raise_update_conflict = True
    conflict = client.put(
        "/api/books/chapter-api-edit/chapters/9/text",
        json={"text": "人工修改。", "expected_hash": "stale"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONTENT_CONFLICT"
    assert conflict.json()["error"]["message"] == "章节内容已被修改，请刷新后重试"


def test_export_preview_returns_tomato_format_and_errors(client, mock_chapter_service):
    mock_chapter_service.status_result = ChapterResult(
        "chapter-api-preview",
        4,
        ChapterStatus.DRAFTED,
        "第4章",
        "林默抬头。",
    )

    resp = client.get("/api/books/chapter-api-preview/chapters/4/export-preview?fmt=tomato_txt")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["format"] == "tomato_txt"
    assert data["preview_text"].startswith("第4章")
    assert not data["preview_text"].startswith("第4章 第4章")
    assert "word_count_out_of_range" in data["format_errors"]


def test_export_preview_returns_404_for_missing_chapter(client):
    resp = client.get("/api/books/chapter-api-preview/chapters/404/export-preview?fmt=markdown")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CHAPTER_NOT_FOUND"


def test_chapter_run_invalid_transition_returns_409_and_sse_error(client, mock_chapter_service):
    book_id = "chapter-api-transition"
    mock_chapter_service.raise_run_transition = True
    resp = client.post(f"/api/books/{book_id}/chapters/4/run")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_ERROR"

    events = asyncio.run(_collect_replayed_events(sse_manager, book_id, 4, 2))
    assert [event["type"] for event in events] == ["pipeline:start", "pipeline:error"]


def test_sse_endpoint_can_connect(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/events" in resp.json()["paths"]


def test_llm_sse_event_helpers_shape():
    chunk = make_chunk_event("book-a", 2, "林默")
    progress = make_progress_event("book-a", 2, 1, 3)

    assert chunk.type == "llm:chunk"
    assert chunk.stage == "draft"
    assert chunk.detail == {"text": "林默"}
    assert progress.type == "llm:progress"
    assert progress.message == "正在生成第 1/3 段"
    assert progress.detail == {"completed": 1, "total": 3}


def test_make_progress_event_serializes_exact_shape():
    progress = make_progress_event("book-stream", 7, 2, 5)

    assert progress.model_dump() == {
        "type": "llm:progress",
        "book_id": "book-stream",
        "chapter_no": 7,
        "stage": "draft",
        "message": "正在生成第 2/5 段",
        "detail": {"completed": 2, "total": 5},
    }


def test_events_endpoint_replays_llm_progress_on_draft(client):
    book_id = "chapter-api-events"
    chapter_no = 6

    draft = client.post(f"/api/books/{book_id}/chapters/{chapter_no}/draft")
    assert draft.status_code == 200

    progress = asyncio.run(_read_progress_sse_event(book_id, chapter_no))

    assert progress["type"] == "llm:progress"
    assert progress["book_id"] == book_id
    assert progress["chapter_no"] == chapter_no
    assert progress["stage"] == "draft"
    assert progress["detail"] == {"completed": 1, "total": 2}
    assert progress["message"] == "正在生成第 1/2 段"


def test_sse_manager_filters_by_book_and_chapter():
    async def scenario() -> None:
        manager = SSEManager()
        subscription = manager.subscribe("book-a", 1)
        first = asyncio.create_task(anext(subscription))
        await asyncio.sleep(0)
        await manager.publish(PipelineEvent(type="pipeline:start", book_id="book-b", chapter_no=1))
        assert first.done() is False
        await manager.publish(PipelineEvent(type="pipeline:start", book_id="book-a", chapter_no=1, stage="draft"))
        data = await asyncio.wait_for(first, timeout=0.5)
        assert json.loads(data)["stage"] == "draft"
        await subscription.aclose()

    asyncio.run(scenario())


async def _collect_replayed_events(manager: SSEManager, book_id: str, chapter_no: int, count: int) -> list[dict]:
    subscription = manager.subscribe(book_id, chapter_no)
    try:
        items = [await asyncio.wait_for(anext(subscription), timeout=0.5) for _ in range(count)]
        return [json.loads(item) for item in items]
    finally:
        await subscription.aclose()


async def _read_progress_sse_event(book_id: str, chapter_no: int) -> dict:
    response = await sse_subscribe(book_id=book_id, chapter_no=chapter_no)
    while True:
        event = await asyncio.wait_for(anext(response.body_iterator), timeout=0.5)
        # Events are unnamed (default) so the browser's EventSource.onmessage fires;
        # no "event" key is present on the wire-format dict.
        payload = json.loads(event["data"])
        if payload.get("type") == "llm:progress":
            return payload


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
