from __future__ import annotations

import asyncio
import json

from storyforge3.api.sse import PipelineEvent, SSEManager, sse_manager


def test_chapter_status_not_found(client):
    resp = client.get("/api/books/nonexistent/chapters/1/status")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CHAPTER_NOT_FOUND"


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

    events = asyncio.run(_collect_replayed_events(sse_manager, book_id, 1, 2))
    assert [event["type"] for event in events] == ["pipeline:start", "pipeline:complete"]


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
    assert status.json()["data"]["status"] == "exported"


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
