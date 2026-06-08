from __future__ import annotations

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from storyforge3.api.sse import sse_manager

router = APIRouter(tags=["events"])


@router.get("/events")
async def sse_subscribe(
    book_id: str | None = Query(None),
    chapter_no: int | None = Query(None),
):
    """Subscribe to pipeline events, optionally filtered to one chapter."""

    async def event_generator():
        async for event in sse_manager.subscribe(book_id, chapter_no):
            yield {"event": "pipeline", "data": event}

    return EventSourceResponse(event_generator())
